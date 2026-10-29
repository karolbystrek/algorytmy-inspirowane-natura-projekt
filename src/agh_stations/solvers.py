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
    def __init__(self, problem, p, budget, scenario):
        self.problem, self.p, self.budget, self.scenario = problem, p, budget, scenario
        self.calls = 0
        self.best = float("inf")
        self.selection = ()
        self.history = []
        self.started = perf_counter()

    def evaluate(self, selection):
        if self.calls >= self.budget:
            raise RuntimeError("Evaluation budget exhausted")
        value = self.problem.objective(selection, self.scenario)
        self.calls += 1
        if len(selection) == self.p and value < self.best:
            self.best, self.selection = value, tuple(sorted(selection))
            self.history.append((self.calls, self.best))
        return value

    def result(self):
        if not self.selection:
            raise ValueError("Budget too small to produce a complete solution")
        return Result(
            self.selection, self.best, self.calls, perf_counter() - self.started, self.history
        )


def solve(
    problem: Problem, method, p, budget=1000, seed=0, scenario="aggregate", foods=12, limit=30
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
    problem.weights(scenario)  # Validate before starting the clock.
    rng = np.random.default_rng(seed)
    evaluator = Evaluator(problem, p, budget, scenario)

    def random_selection():
        return tuple(sorted(int(i) for i in rng.choice(n, size=p, replace=False)))

    if p == n:
        evaluator.evaluate(tuple(range(n)))
    elif method == "random":
        for _ in range(budget):
            evaluator.evaluate(random_selection())
    elif method == "greedy":
        # Partial configurations count against the same cap but are never reported as incumbents.
        construction_cost = sum(n - k for k in range(p))
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
            added = int(rng.choice(difference if difference and rng.random() < 0.5 else unused))
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
            fitness = 1 / (1 + np.asarray(values))
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
