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
    population=100,
    crossover="union",
    mutation=0.4,
):
    n = len(problem.candidate_ids)
    if not isinstance(p, int) or not 1 <= p <= n:
        raise ValueError("p must be an integer in [1, candidate_count]")
    if not isinstance(budget, int) or budget < 1:
        raise ValueError("budget must be a positive integer")
    if method not in {"abc", "ga", "random", "greedy", "multistart"}:
        raise ValueError(f"Unknown method: {method}")
    if population < 2 or crossover not in {"union", "greedy"} or not 0 <= mutation <= 1:
        raise ValueError("population must be >= 2, crossover union/greedy, mutation in [0, 1]")
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
    elif method == "multistart":
        # Random restarts of best-improvement 1-swap: a plain local search that uses the budget.
        while evaluator.calls < budget:
            current = random_selection()
            value = evaluator.evaluate(current)
            while True:
                best_neighbour, best_value = None, value
                for removed in current:
                    for added in range(n):
                        if added in current:
                            continue
                        if evaluator.calls == budget:
                            return evaluator.result()
                        neighbour = tuple(sorted((set(current) - {removed}) | {added}))
                        candidate_value = evaluator.evaluate(neighbour)
                        if candidate_value < best_value:
                            best_neighbour, best_value = neighbour, candidate_value
                if best_neighbour is None:
                    break
                current, value = best_neighbour, best_value
                if evaluator.calls == budget:
                    return evaluator.result()
    elif method == "ga":
        # Steady-state GA on sets: every offspring replaces the worst member if it is better.
        size = min(population, budget)
        members = [random_selection() for _ in range(size)]
        scores = [evaluator.evaluate(member) for member in members]

        def tournament():
            first, second = rng.choice(size, size=2, replace=False)
            return members[first if scores[first] <= scores[second] else second]

        def mutated(selection):
            kept = set(selection)
            kept.remove(int(rng.choice(sorted(kept))))
            kept.add(int(rng.choice(sorted(set(range(n)) - set(selection)))))
            return tuple(sorted(kept))

        while evaluator.calls < budget:
            parent_a, parent_b = set(tournament()), set(tournament())
            shared, known = parent_a & parent_b, None
            if crossover == "union":
                differing = sorted(parent_a ^ parent_b)
                inherited = rng.choice(differing, size=p - len(shared), replace=False)
                child = tuple(sorted(shared | {int(j) for j in inherited}))
            else:  # Drop the least useful station of the parents' union until p remain.
                current = parent_a | parent_b
                while len(current) > p:
                    trials = {}
                    for removed in sorted(current - shared):
                        if evaluator.calls == budget:
                            return evaluator.result()
                        trials[removed] = evaluator.evaluate(tuple(sorted(current - {removed})))
                    dropped = min(trials, key=trials.get)
                    current, known = current - {dropped}, trials[dropped]
                child = tuple(sorted(current))
            # A copy of a current member would spend an evaluation without teaching anything.
            if child in members or rng.random() < mutation:
                child, known = mutated(child), None
            if known is None:
                if evaluator.calls == budget:
                    return evaluator.result()
                known = evaluator.evaluate(child)
            worst = int(np.argmax(scores))
            if known < scores[worst] and child not in members:
                members[worst], scores[worst] = child, known
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


def optimal(problem: Problem, p, scenario="aggregate", fixed=()):
    """Prove the p-median optimum with an integer program, for instances too big to enumerate.

    Variables: y_j (open candidate j) and x_ij (demand i served by j), with x_ij <= y_j.
    Stations in ``fixed`` must stay open, which models extending an existing layout.
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
    rows, columns, values, lower, upper = _assignment_constraints(n, m, p)
    matrix = coo_matrix((values, (rows, columns)), shape=(len(lower), m + n * m)).tocsr()
    floor = np.zeros(m + n * m)
    floor[list(fixed)] = 1
    outcome = milp(
        cost,
        constraints=LinearConstraint(matrix, lower, upper),
        integrality=np.concatenate([np.ones(m), np.zeros(n * m)]),
        bounds=Bounds(floor, 1),
        options={"mip_rel_gap": 0},
    )
    selection = _opened_stations(outcome, m, p)
    objective = problem.objective(selection, scenario)
    return Result(selection, objective, 0, perf_counter() - started, [(0, objective)])


def _assignment_constraints(n, m, p):
    """Open exactly p stations and serve every demand point once, from an open station."""
    rows, columns, values = [0] * m, list(range(m)), [1.0] * m
    lower, upper = [p], [p]
    row = 1
    for i in range(n):
        rows += [row] * m
        columns += [m + i * m + j for j in range(m)]
        values += [1.0] * m
        lower.append(1)
        upper.append(1)
        row += 1
    for i in range(n):
        for j in range(m):
            rows += [row, row]
            columns += [m + i * m + j, j]
            values += [1.0, -1.0]
            lower.append(-np.inf)
            upper.append(0)
            row += 1
    return rows, columns, values, lower, upper


def _opened_stations(outcome, m, p):
    if outcome.x is None or not (outcome.success or outcome.status == 1):
        raise RuntimeError(f"Integer program failed: {outcome.message}")
    selection = tuple(int(j) for j in np.flatnonzero(outcome.x[:m] > 0.5))
    if len(selection) != p:
        raise RuntimeError("Integer program returned an infeasible station count")
    return selection


def robust_optimal(problem: Problem, p, time_limit_s=60.0):
    """One layout minimizing the worst relative loss across the separate times of day.

    Each scenario's loss is measured against that scenario's own proved optimum. Stops at the
    time limit with the best layout found, and reports whether optimality was proved.
    """
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    n, m = problem.distances.shape
    best = {name: optimal(problem, p, name).objective for name in problem.scenarios}
    started = perf_counter()
    worst = m + n * m  # The last variable is the worst scenario's ratio to its own optimum.
    rows, columns, values, lower, upper = _assignment_constraints(n, m, p)
    row = len(lower)
    for name, optimum in best.items():
        per_pair = (problem.distances * problem.scenarios[name][:, None]).ravel() / optimum
        used = np.flatnonzero(per_pair)
        rows += [row] * (len(used) + 1)
        columns += [m + int(k) for k in used] + [worst]
        values += [float(per_pair[k]) for k in used] + [-1.0]
        lower.append(-np.inf)
        upper.append(0)
        row += 1
    matrix = coo_matrix((values, (rows, columns)), shape=(row, worst + 1)).tocsr()
    cost = np.zeros(worst + 1)
    cost[worst] = 1.0
    outcome = milp(
        cost,
        constraints=LinearConstraint(matrix, lower, upper),
        integrality=np.concatenate([np.ones(m), np.zeros(n * m + 1)]),
        bounds=Bounds(np.zeros(worst + 1), np.append(np.ones(worst), np.inf)),
        options={"time_limit": time_limit_s, "mip_rel_gap": 1e-4},
    )
    selection = _opened_stations(outcome, m, p)
    ratio = max(problem.objective(selection, name) / best[name] for name in best)
    return {
        "selection": selection,
        "worst_regret_percent": 100 * (ratio - 1),
        "proved": bool(outcome.success),
        "elapsed_s": perf_counter() - started,
    }
