"""Protocol helpers: statistics, weight variants, and a complete miniature study."""

import csv
import json

import numpy as np
import pytest

from agh_stations.model import Problem
from agh_stations.solvers import optimal, solve
from agh_stations.study import choose_parameters, holm, run, weight_variants


def write_problem(path, n, m, seed):
    rng = np.random.default_rng(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_id": f"test-{seed}",
                "candidates": [
                    {"id": f"c{j}", "lat": 50.0, "lon": 19.0, "status": "requires_review"}
                    for j in range(m)
                ],
                "demand": [
                    {"id": f"d{i}", "category": "dorm" if i % 2 else "teaching", "area_m2": 100.0}
                    for i in range(n)
                ],
                "distances_m": rng.uniform(10, 900, size=(n, m)).round(3).tolist(),
                "scenarios": {
                    "morning": rng.integers(1, 5, n).tolist(),
                    "day": rng.integers(1, 5, n).tolist(),
                },
                "scenario_mixture": {"morning": 1, "day": 1},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_holm_matches_a_hand_calculated_example():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_parameters_are_chosen_by_lowest_average_gap():
    rows = [
        {"foods": 8, "limit_rule": "30", "mean_gap_percent": 2.0},
        {"foods": 8, "limit_rule": "30", "mean_gap_percent": 4.0},
        {"foods": 12, "limit_rule": "foods*p", "mean_gap_percent": 1.0},
        {"foods": 12, "limit_rule": "foods*p", "mean_gap_percent": 1.5},
    ]
    assert choose_parameters(rows) == (12, "foods*p")


def test_weight_variants_change_only_the_named_category():
    raw = {
        "demand": [{"category": "dorm"}, {"category": "teaching"}],
        "scenarios": {"morning": [4, 3]},
    }
    variants = weight_variants(raw)
    assert variants["jednolite"]["morning"] == [1.0, 1.0]
    assert variants["dorm +25%"]["morning"] == [5.0, 3]
    assert variants["teaching -25%"]["morning"] == [4, 2.25]


@pytest.mark.parametrize(
    "options",
    [
        {"onlooker": "rank"},
        {"onlooker": "none"},
        {"peer_probability": 0.0},
    ],
)
def test_abc_variants_stay_feasible_and_within_budget(options):
    problem = Problem(
        [f"c{j}" for j in range(8)],
        ["a", "b", "c"],
        np.arange(24).reshape(3, 8) + 1,
        {"s": [1, 2, 3]},
        {"s": 1},
    )
    result = solve(problem, "abc", 3, budget=80, seed=1, **options)
    assert result.evaluations == 80
    assert len(set(result.selection)) == 3
    assert result.objective >= optimal(problem, 3).objective - 1e-9


def test_abc_rejects_unknown_variants():
    problem = Problem(["a", "b"], ["x"], [[1, 2]], {"s": [1]}, {"s": 1})
    with pytest.raises(ValueError, match="onlooker"):
        solve(problem, "abc", 1, onlooker="other")


def test_complete_miniature_study_writes_consistent_artifacts(tmp_path):
    problem = write_problem(tmp_path / "final" / "problem.json", 12, 20, 1)
    development = write_problem(tmp_path / "dev" / "problem.json", 25, 40, 2)
    output = tmp_path / "out"
    run(problem, development, output, ps=(2, 3), budget=300, runs=3, tuning_runs=2, p_max=4)
    for name in (
        "abc_tuning.csv",
        "abc_ablation.csv",
        "runs.csv",
        "comparison.csv",
        "tests.csv",
        "stations_curve.csv",
        "scenarios.csv",
        "thresholds.csv",
        "weights.csv",
        "candidates_to_check.csv",
        "convergence.png",
        "stations_curve.png",
    ):
        assert (output / name).stat().st_size > 0, name
    with (output / "comparison.csv").open(encoding="utf-8") as handle:
        comparison = list(csv.DictReader(handle))
    assert {row["method"] for row in comparison} >= {"abc", "random"}
    assert all(float(row["best_m"]) >= float(row["optimum_m"]) - 1e-6 for row in comparison)
    metadata = json.loads((output / "study.json").read_text(encoding="utf-8"))
    assert metadata["draft"] is True
    with (output / "stations_curve.csv").open(encoding="utf-8") as handle:
        distances = [float(row["mean_distance_m"]) for row in csv.DictReader(handle)]
    assert all(a >= b - 1e-9 for a, b in zip(distances, distances[1:], strict=False))
