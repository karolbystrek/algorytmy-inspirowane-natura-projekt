"""Budgeted discrete ABC, random search, greedy + swaps, and a tiny exact oracle."""

from dataclasses import dataclass
from itertools import combinations
from math import comb
from time import perf_counter

import numpy as np

from agh_stations.model import Problem


@dataclass
class Result:
    selection: tuple[int, ...]
    objective: float
    evaluations: int
    elapsed_s: float
    history: list[tuple[int, float]]


class Evaluator:
    def __init__(self, problem, p, budget, scenario, on_improvement=None):
        self.problem, self.p, self.budget, self.scenario = problem, p, budget, scenario
        self.calls = 0
        self.best = float("inf")
        self.selection = ()
        self.history = []
        self.started = perf_counter()
        self.on_improvement = on_improvement

    def evaluate(self, selection):
        if self.calls >= self.budget:
            raise RuntimeError("Evaluation budget exhausted")
        value = self.problem.objective(selection, self.scenario)
        self.calls += 1
        if len(selection) == self.p and value < self.best:
            self.best, self.selection = value, tuple(sorted(selection))
            self.history.append((self.calls, self.best))
            if self.on_improvement is not None:
                self.on_improvement(self.calls, self.best, self.selection)
        return value

    def result(self):
        if not self.selection:
            raise ValueError("Budget too small to produce a complete solution")
        return Result(
            self.selection, self.best, self.calls, perf_counter() - self.started, self.history
        )


def greedy_construction_cost(candidate_count, p):
    """Evaluations greedy spends before it has one complete layout."""
    return sum(candidate_count - k for k in range(p))


def solve(
    problem: Problem,
    method,
    p,
    budget=1000,
    seed=0,
    scenario="aggregate",
    foods=12,
    limit=30,
    on_improvement=None,
    peer_probability=0.5,
    onlooker="inverse",
):
    n = len(problem.candidate_ids)
    if not isinstance(p, int) or not 1 <= p <= n:
        raise ValueError("p must be an integer in [1, candidate_count]")
    if not isinstance(budget, int) or budget < 1:
        raise ValueError("budget must be a positive integer")
    if method not in {"abc", "random", "greedy"}:
        raise ValueError(f"Unknown method: {method}")
    if foods < 2 or limit < 1:
        raise ValueError("foods must be >= 2 and limit >= 1")
    if onlooker not in {"inverse", "rank", "none"} or not 0 <= peer_probability <= 1:
        raise ValueError("onlooker must be inverse/rank/none and peer_probability within [0, 1]")
    problem.weights(scenario)  # Validate before starting the clock.
    rng = np.random.default_rng(seed)
    evaluator = Evaluator(problem, p, budget, scenario, on_improvement)

    def random_selection():
        return tuple(sorted(int(i) for i in rng.choice(n, size=p, replace=False)))

    if p == n:
        evaluator.evaluate(tuple(range(n)))
    elif method == "random":
        for _ in range(budget):
            evaluator.evaluate(random_selection())
    elif method == "greedy":
        # Partial configurations count against the same cap but are never reported as incumbents.
        construction_cost = greedy_construction_cost(n, p)
        if budget < construction_cost:
            raise ValueError(
                f"Greedy construction requires at least {construction_cost} evaluations"
            )
        chosen = ()
        for _ in range(p):
            choices = [tuple(sorted((*chosen, j))) for j in range(n) if j not in chosen]
            chosen = min(choices, key=evaluator.evaluate)
        # Best-improvement 1-swap search; a partial final neighbourhood still updates the incumbent.
        while evaluator.calls < budget:
            old = evaluator.best
            current = evaluator.selection
            for removed in current:
                for added in range(n):
                    if added in current:
                        continue
                    if evaluator.calls == budget:
                        return evaluator.result()
                    neighbour = tuple(sorted((set(current) - {removed}) | {added}))
                    evaluator.evaluate(neighbour)
            if evaluator.best >= old:
                break
    else:
        source_count = min(foods, budget)
        sources = [random_selection() for _ in range(source_count)]
        values = [evaluator.evaluate(s) for s in sources]
        trials = [0] * source_count

        def attempt(index):
            peer_indices = [i for i in range(source_count) if i != index]
            peer = sources[int(rng.choice(peer_indices))] if peer_indices else sources[index]
            current = set(sources[index])
            difference = sorted(set(peer) - current)
            unused = sorted(set(range(n)) - current)
            guided = difference and rng.random() < peer_probability
            added = int(rng.choice(difference if guided else unused))
            removed = int(rng.choice(sorted(current)))
            neighbour = tuple(sorted((current - {removed}) | {added}))
            value = evaluator.evaluate(neighbour)
            if value < values[index]:
                sources[index], values[index], trials[index] = neighbour, value, 0
            else:
                trials[index] += 1

        while evaluator.calls < budget:
            # Employed phase: one attempt for each source.
            for i in range(source_count):
                if evaluator.calls == budget:
                    return evaluator.result()
                attempt(i)
            # Onlooker phase: fitness-proportional selection of promising sources.
            if onlooker != "none":
                if onlooker == "inverse":
                    fitness = 1 / (1 + np.asarray(values))
                else:  # Rank fitness does not depend on the scale of the objective.
                    fitness = np.empty(source_count)
                    fitness[np.argsort(-np.asarray(values))] = np.arange(1.0, source_count + 1)
                probabilities = fitness / fitness.sum()
                for _ in range(source_count):
                    if evaluator.calls == budget:
                        return evaluator.result()
                    attempt(int(rng.choice(source_count, p=probabilities)))
            # Scout phase: replace at most one abandoned source; keep the global best separately.
            i = int(np.argmax(trials))
            if trials[i] >= limit and evaluator.calls < budget:
                sources[i] = random_selection()
                values[i], trials[i] = evaluator.evaluate(sources[i]), 0
    return evaluator.result()


def exact(problem: Problem, p, scenario="aggregate", max_combinations=200_000):
    n = len(problem.candidate_ids)
    if not isinstance(p, int) or not 1 <= p <= n:
        raise ValueError("Invalid p")
    count = comb(n, p)
    if count > max_combinations:
        raise ValueError(
            f"Exact enumeration would need {count} evaluations; limit {max_combinations}"
        )
    evaluator = Evaluator(problem, p, count, scenario)
    for selection in combinations(range(n), p):
        evaluator.evaluate(selection)
    return evaluator.result()


def optimal(problem: Problem, p, scenario="aggregate"):
    """Prove the p-median optimum with an integer program, for instances too big to enumerate.

    Variables: y_j (open candidate j) and x_ij (demand i served by j), with x_ij <= y_j.
    ``evaluations`` is 0 because the solver never calls the objective used by the heuristics.
    """
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    n, m = problem.distances.shape
    if not isinstance(p, int) or not 1 <= p <= m:
        raise ValueError("Invalid p")
    weights = problem.weights(scenario)
    started = perf_counter()
    cost = np.concatenate([np.zeros(m), (problem.distances * weights[:, None]).ravel()])
    rows, columns, values = [0] * m, list(range(m)), [1.0] * m
    lower, upper = [p], [p]
    row = 1
    for i in range(n):  # Every demand point is served exactly once.
        rows += [row] * m
        columns += [m + i * m + j for j in range(m)]
        values += [1.0] * m
        lower.append(1)
        upper.append(1)
        row += 1
    for i in range(n):  # Service is allowed only from an open station.
        for j in range(m):
            rows += [row, row]
            columns += [m + i * m + j, j]
            values += [1.0, -1.0]
            lower.append(-np.inf)
            upper.append(0)
            row += 1
    matrix = coo_matrix((values, (rows, columns)), shape=(row, m + n * m)).tocsr()
    outcome = milp(
        cost,
        constraints=LinearConstraint(matrix, lower, upper),
        integrality=np.concatenate([np.ones(m), np.zeros(n * m)]),
        bounds=Bounds(0, 1),
        options={"mip_rel_gap": 0},
    )
    if not outcome.success:
        raise RuntimeError(f"Integer program failed: {outcome.message}")
    selection = tuple(int(j) for j in np.flatnonzero(outcome.x[:m] > 0.5))
    if len(selection) != p:
        raise RuntimeError("Integer program returned an infeasible station count")
    objective = problem.objective(selection, scenario)
    return Result(selection, objective, 0, perf_counter() - started, [(0, objective)])
