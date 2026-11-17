"""Protocol helpers: statistics, weight variants, and a complete miniature study."""

import csv
import json
import socket

import numpy as np
import pytest

from agh_stations.model import Problem
from agh_stations.solvers import optimal, solve
from agh_stations.study import (
    choose_ga_parameters,
    choose_parameters,
    choose_restart,
    choose_stages,
    gate_sensitivity,
    group_metrics,
    holm,
    large_station_counts,
    list_sensitivity,
    method_pair_tests,
    mixture_variants,
    recommendation,
    robust_layouts,
    run,
    weight_variants,
    weighted_quantile,
)


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


def test_equal_split_within_category_removes_the_floor_area_assumption():
    raw = {
        "demand": [
            {"category": "dorm", "floor_area_m2": 900, "area_m2": 300},
            {"category": "dorm", "floor_area_m2": 100, "area_m2": 100},
            {"category": "other", "floor_area_m2": 200, "area_m2": 200},
        ],
        "scenarios": {"day": [9.0, 1.0, 2.0]},
        "fixed_category_totals_for_sensitivity": {"dorm": {"day": 1}, "other": {"day": 3}},
    }
    variants = weight_variants(raw)
    assert variants["równo w kategorii"]["day"] == [5.0, 5.0, 2.0]
    assert variants["bez pięter (tylko obrys budynku)"]["day"] == [3.0, 1.0, 2.0]
    assert variants["stałe udziały kategorii (poprzednia reguła)"]["day"] == [0.9, 0.1, 3.0]


def test_mixture_variants_count_one_time_of_day_twice():
    raw = {"scenarios": {"a": [1], "b": [1]}, "scenario_mixture": {"a": 1, "b": 1}}
    assert mixture_variants(raw)["mieszanina: b ×2"] == {"a": 1, "b": 2}
    assert mixture_variants({"scenarios": {"a": [1]}, "scenario_mixture": {"a": 1}}) == {}


def test_robust_layout_never_has_a_worse_worst_case_than_the_aggregate_layout():
    rng = np.random.default_rng(3)
    problem = Problem(
        [f"c{j}" for j in range(14)],
        [f"d{i}" for i in range(16)],
        rng.uniform(10, 900, size=(16, 14)),
        {"a": rng.uniform(0, 1, 16), "b": rng.uniform(0, 1, 16), "c": rng.uniform(0, 1, 16)},
        {"a": 1, "b": 1, "c": 1},
    )
    row = robust_layouts(problem, (3,))[0]
    assert row["proved_optimal"]
    assert (
        row["robust_layout_worst_regret_percent"]
        <= row["aggregate_layout_worst_regret_percent"] + 1e-2
    )
    assert row["robust_cost_on_aggregate_percent"] >= -1e-9


def random_problem(n=20, m=30, seed=5):
    rng = np.random.default_rng(seed)
    return Problem(
        [f"c{j}" for j in range(m)],
        [f"d{i}" for i in range(n)],
        rng.uniform(10, 900, size=(n, m)),
        {"s": np.ones(n)},
        {"s": 1},
    )


@pytest.mark.parametrize("method", ["ga", "ga_restart"])
@pytest.mark.parametrize("crossover", ["union", "greedy"])
@pytest.mark.parametrize("p", [1, 4, 29])
def test_ga_uses_the_whole_budget_and_keeps_every_layout_valid(method, crossover, p):
    problem = random_problem()
    result = solve(
        problem, method, p, budget=700, seed=3, population=10, crossover=crossover, restart_after=5
    )
    assert result.evaluations == 700
    assert len(set(result.selection)) == p
    assert result.objective >= optimal(problem, p).objective - 1e-9
    assert result.objective == pytest.approx(problem.objective(result.selection))


def test_ga_is_repeatable_and_rejects_invalid_settings():
    problem = random_problem()
    runs = [solve(problem, "ga", 4, budget=500, seed=9).selection for _ in range(2)]
    assert runs[0] == runs[1]
    for bad in ({"population": 1}, {"crossover": "other"}, {"mutation": 1.5}, {"restart_after": 0}):
        with pytest.raises(ValueError):
            solve(problem, "ga", 4, budget=500, **bad)


def test_ga_beats_random_search_with_the_same_budget():
    problem = random_problem(n=40, m=60)
    ga = [solve(problem, "ga", 8, 3000, s).objective for s in range(5)]
    random = [solve(problem, "random", 8, 3000, s).objective for s in range(5)]
    assert np.mean(ga) < np.mean(random)


def test_ga_parameters_are_chosen_by_lowest_average_gap():
    rows = [
        {"population": 20, "mutation": 0.1, "crossover": "union", "mean_gap_percent": 2.0},
        {"population": 50, "mutation": 0.4, "crossover": "greedy", "mean_gap_percent": 1.0},
    ]
    assert choose_ga_parameters(rows) == {"population": 50, "mutation": 0.4, "crossover": "greedy"}


def test_ga_and_abc_are_compared_two_sided_for_every_station_count():
    rows = [{"p": 3, "method": "abc", "mean_distance_m": v} for v in (1.0, 1.0, 2.0)] + [
        {"p": 3, "method": "ga", "mean_distance_m": v} for v in (3.0, 4.0, 5.0)
    ]
    test = method_pair_tests(rows, (3,), "ga", "abc", "GA vs ABC")[0]
    assert test["second_mean_m"] < test["first_mean_m"]
    assert 0 < test["holm_p_value"] <= 1


def test_restart_changes_the_search_only_after_stagnation():
    problem = random_problem(n=40, m=60)
    plain = solve(problem, "ga", 8, 3000, 4, population=20)
    never = solve(problem, "ga_restart", 8, 3000, 4, population=20, restart_after=10**6)
    often = solve(problem, "ga_restart", 8, 3000, 4, population=20, restart_after=10)
    assert never.history == plain.history
    assert often.history != plain.history
    assert len(set(often.selection)) == 8


def test_restart_threshold_is_chosen_by_lowest_average_gap():
    rows = [
        {"restart_after": 250, "mean_gap_percent": 0.5},
        {"restart_after": 250, "mean_gap_percent": 0.3},
        {"restart_after": 1000, "mean_gap_percent": 0.1},
        {"restart_after": 1000, "mean_gap_percent": 0.2},
    ]
    assert choose_restart(rows) == 1000


def test_multistart_spends_the_whole_budget_and_stays_feasible():
    problem = random_problem()
    result = solve(problem, "multistart", 4, budget=900, seed=2)
    assert result.evaluations == 900
    assert len(set(result.selection)) == 4
    assert result.objective >= optimal(problem, 4).objective - 1e-9


def test_fixed_stations_stay_open_and_cost_at_least_nothing():
    problem = random_problem()
    first = optimal(problem, 3)
    extended = optimal(problem, 6, fixed=first.selection)
    assert set(first.selection) <= set(extended.selection)
    assert extended.objective >= optimal(problem, 6).objective - 1e-9


def test_stages_follow_coverage_and_the_value_of_the_last_station():
    curve = [
        {"p": 1, "coverage": 0.2, "gain_vs_previous_m": None},
        {"p": 2, "coverage": 0.8, "gain_vs_previous_m": 50.0},
        {"p": 3, "coverage": 0.9, "gain_vs_previous_m": 6.0},
        {"p": 4, "coverage": 0.95, "gain_vs_previous_m": 1.0},
    ]
    assert choose_stages(curve) == (2, 3)


def test_recommendation_marks_stages_and_serves_all_demand():
    problem = random_problem()
    raw = {
        "candidates": [{"id": c} for c in problem.candidate_ids],
        "demand": [{"id": d} for d in problem.demand_ids],
    }
    summary, stations = recommendation(problem, raw, 2, 5)
    assert [row["p"] for row in summary] == [2, 5, 5]
    assert sum(s["stage"] == 1 for s in stations) == 2
    assert sum(s["demand_share"] for s in stations) == pytest.approx(1)
    assert summary[1]["mean_distance_m"] >= summary[2]["mean_distance_m"] - 1e-9


def test_large_p_rows_show_when_greedy_does_not_fit_in_the_budget():
    rng = np.random.default_rng(4)
    problem = Problem(
        [f"c{j}" for j in range(30)],
        [f"d{i}" for i in range(20)],
        rng.uniform(10, 900, size=(20, 30)),
        {"s": np.ones(20)},
        {"s": 1},
    )
    rows = large_station_counts(problem, (8, 30), ((100, 2), (2000, 1)), 2, 8, "foods*p")
    assert {(r["p"], r["budget"]) for r in rows} == {(8, 100), (8, 2000)}
    tight, ample = rows
    assert tight["greedy_gap_percent"] is None and tight["greedy_ran_out_of_budget"]
    assert ample["greedy_gap_percent"] >= -1e-9


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


@pytest.mark.parametrize(
    ("values", "weights", "q", "expected"),
    [
        ([10, 20, 30], [1, 1, 1], 0.9, 30),
        ([10, 20, 30], [90, 5, 5], 0.9, 10),
        ([30, 10, 20], [1, 8, 1], 0.9, 20),
        ([5], [1], 0.9, 5),
    ],
)
def test_weighted_percentile_is_the_inverse_cumulative_demand(values, weights, q, expected):
    assert weighted_quantile(values, weights, q) == expected


def small_campus():
    raw = {
        "candidates": [
            {"id": "a", "source": "osm_bicycle_parking"},
            {"id": "b", "source": "graph_node_near_demand"},
            {"id": "c", "source": "osm_bicycle_parking"},
            {"id": "d", "source": "graph_node_near_demand"},
        ],
        "demand": [
            {"id": "x", "category": "dorm", "location_method": "osm_entrances"},
            {"id": "y", "category": "dorm", "location_method": "footprint_nearest_node"},
            {"id": "z", "category": "other", "location_method": "osm_entrances"},
        ],
        "distances_m": [[10, 500, 300, 40], [400, 20, 200, 90], [700, 650, 30, 80]],
        "distances_m_gates_closed": [
            [10, None, 300, 40],
            [None, None, None, None],
            [700, 900, 60, 80],
        ],
        "scenarios": {"day": [2.0, 1.0, 1.0]},
        "scenario_mixture": {"day": 1},
    }
    problem = Problem(
        [c["id"] for c in raw["candidates"]],
        [d["id"] for d in raw["demand"]],
        raw["distances_m"],
        {"day": np.asarray(raw["scenarios"]["day"])},
        {"day": 1},
    )
    return problem, raw


def test_group_metrics_report_every_category_and_the_whole():
    problem, raw = small_campus()
    rows = group_metrics(problem, raw, (2,))
    assert [r["group"] for r in rows] == ["wszystkie", "dorm", "other"]
    assert rows[0]["max_m"] >= rows[0]["weighted_p90_m"] >= 0
    assert rows[2]["buildings"] == 1


def test_shorter_point_lists_are_judged_on_the_complete_demand():
    problem, raw = small_campus()
    rows = list_sensitivity(problem, raw, (2,))
    assert {r["change"] for r in rows} == {"kandydaci", "popyt"}
    assert all(r["loss_percent"] >= -1e-9 for r in rows)
    parking = next(r for r in rows if r["variant"] == "tylko istniejące parkingi z OSM")
    assert parking["points"] == 2


def test_closed_gates_report_buildings_cut_off_from_every_station():
    problem, raw = small_campus()
    row = gate_sensitivity(problem, raw, (2,))[0]
    assert row["buildings_without_route"] == 1
    assert row["demand_without_route"] == pytest.approx(0.25)
    assert row["mean_closed_m"] >= row["mean_open_m"]
    assert gate_sensitivity(problem, {k: v for k, v in raw.items() if "gates" not in k}, (2,)) == []


def test_complete_miniature_study_writes_consistent_artifacts(tmp_path, monkeypatch):
    def refuse_network(*args, **kwargs):
        raise AssertionError("The study must run without any network access")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket, "create_connection", refuse_network)
    problem = write_problem(tmp_path / "final" / "problem.json", 12, 20, 1)
    development = write_problem(tmp_path / "dev" / "problem.json", 25, 40, 2)
    output = tmp_path / "out"
    run(problem, development, output, ps=(2, 3), budget=300, runs=3, tuning_runs=2, p_max=4)
    for name in (
        "abc_tuning.csv",
        "abc_ablation.csv",
        "ga_tuning.csv",
        "ga_tests.csv",
        "ga_restart_tuning.csv",
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
