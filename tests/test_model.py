import json

import numpy as np
import pytest

from agh_stations.model import Problem
from agh_stations.solvers import exact, solve


@pytest.fixture
def problem():
    # Independently calculable: for p=1 the optimum is index 3, with cost 7.5 m.
    return Problem(
        ["a", "b", "c", "d"],
        ["left", "right"],
        [[0, 10, 20, 30], [30, 20, 10, 0]],
        {"morning": [1, 3]},
        {"morning": 1},
    )


def test_hand_calculated_objective_and_coverage(problem):
    assert problem.objective([3]) == pytest.approx(7.5)
    assert problem.metrics([3], threshold=15)["coverage"] == pytest.approx(0.75)
    assert problem.objective([0, 3]) == 0
    assert exact(problem, 1).selection == (3,)
    assert exact(problem, 1).evaluations == 4


def test_each_scenario_is_normalized_before_aggregation():
    p = Problem(
        ["a"],
        ["x", "y"],
        [[0], [100]],
        {"small": [1, 0], "large": [0, 1000]},
        {"small": 1, "large": 1},
    )
    assert p.objective([0]) == 50


@pytest.mark.parametrize("method", ["abc", "random", "greedy"])
def test_solver_feasibility_budget_and_exact_bound(problem, method):
    result = solve(problem, method, p=2, budget=100, seed=42, limit=1)
    assert len(result.selection) == len(set(result.selection)) == 2
    assert 1 <= result.evaluations <= 100
    assert result.objective >= exact(problem, 2).objective
    assert result.objective == problem.objective(result.selection)
    assert all(a[1] >= b[1] for a, b in zip(result.history, result.history[1:], strict=False))
    if method != "greedy":
        assert result.evaluations == 100


@pytest.mark.parametrize("budget", [1, 2, 13, 25])
def test_abc_stops_within_each_phase(problem, budget):
    result = solve(problem, "abc", p=1, budget=budget, foods=4, limit=1)
    assert result.evaluations == budget


def test_seed_reproducibility(problem):
    first = solve(problem, "abc", 1, seed=14, budget=50)
    second = solve(problem, "abc", 1, seed=14, budget=50)
    assert first.selection == second.selection
    assert first.history == second.history


def test_all_candidates_and_too_small_greedy_budget(problem):
    assert solve(problem, "abc", 4, budget=1).selection == (0, 1, 2, 3)
    with pytest.raises(ValueError, match="at least"):
        solve(problem, "greedy", 2, budget=6)
    with pytest.raises(ValueError, match="limit"):
        exact(problem, 2, max_combinations=5)


@pytest.mark.parametrize("bad", [[0, 0], [], [4], [-1], [0.5]])
def test_invalid_selections(problem, bad):
    with pytest.raises(ValueError):
        problem.objective(bad)


@pytest.mark.parametrize("distance", [float("inf"), float("nan"), -1])
def test_invalid_distances(distance):
    with pytest.raises(ValueError, match="finite"):
        Problem(["a"], ["d"], [[distance]], {"s": [1]}, {"s": 1})


def test_invalid_weights_and_ids():
    with pytest.raises(ValueError, match="weights"):
        Problem(["a"], ["d"], [[1]], {"s": [0]}, {"s": 1})
    with pytest.raises(ValueError, match="unique"):
        Problem(["a", "a"], ["d"], [[1, 2]], {"s": [1]}, {"s": 1})


def test_cli_artifacts(tmp_path):
    from argparse import Namespace

    from agh_stations.cli import benchmark

    path = tmp_path / "problem.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidates": [{"id": "a"}, {"id": "b"}],
                "demand": [{"id": "x"}],
                "distances_m": [[3, 8]],
                "scenarios": {"s": [1]},
                "scenario_mixture": {"s": 1},
            }
        )
    )
    benchmark(
        Namespace(
            problem=str(path),
            output=str(tmp_path),
            p=1,
            budget=10,
            runs=2,
            scenario="aggregate",
            threshold=250,
            foods=4,
            limit=2,
            exact=True,
        )
    )
    results = json.loads((tmp_path / "results.json").read_text())
    assert results["summary"]["exact"]["best_m"] == 3
    assert results["summary"]["abc"]["runs"] == 2
    assert results["summary"]["greedy"]["runs"] == 1
    assert np.isfinite(results["summary"]["abc"]["mean_m"])
