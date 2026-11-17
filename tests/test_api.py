"""The browser contract uses the same model, limits and real improvement trace."""

import os

import numpy as np
import pytest

pytest.importorskip("fastapi")
os.environ["AGH_DATASET"] = "agh-pilot"  # The contract is tested on the frozen, small snapshot.
from fastapi.testclient import TestClient  # noqa: E402

from agh_stations import api  # noqa: E402
from agh_stations.api import app, dataset, run_lock  # noqa: E402

client = TestClient(app)


def test_live_run_and_replay_match_the_model():
    payload = {"p": 4, "budget": 1000, "seed": 0, "scenario": "morning"}
    response = client.post("/api/run", json=payload)
    assert response.status_code == 200
    result = response.json()
    _, problem, manifest = dataset()
    assert result["problem_sha256"] == manifest["files_sha256"]["problem.json"]
    assert sum(result["demand_weights"]) == pytest.approx(1)
    for solution in result["methods"].values():
        assert solution["steps"][-1]["candidate_ids"] == solution["candidate_ids"]
        assert solution["evaluations"] <= payload["budget"]
        values = [step["mean_distance_m"] for step in solution["steps"]]
        assert all(a > b for a, b in zip(values, values[1:], strict=False))
        for step in solution["steps"]:
            indices = [problem.candidate_ids.index(name) for name in step["candidate_ids"]]
            assert len(indices) == len(set(indices)) == payload["p"]
            assert step["mean_distance_m"] == pytest.approx(problem.objective(indices, "morning"))
            assert step["coverage"] == pytest.approx(
                problem.metrics(indices, "morning")["coverage"]
            )
        assert solution["mean_distance_m"] >= result["exact"]["mean_distance_m"] - 1e-9
    repeated = client.post("/api/run", json=payload).json()
    assert repeated["methods"]["abc"]["steps"] == result["methods"]["abc"]["steps"]


@pytest.mark.parametrize(
    "payload",
    [
        {"p": 0},
        {"p": 31},
        {"p": 4.5},
        {"p": True},
        {"budget": 499},
        {"budget": 20001},
        {"seed": -1},
        {"scenario": "unknown"},
        {"unexpected": 1},
    ],
)
def test_invalid_or_excessive_requests_are_rejected(payload):
    assert client.post("/api/run", json=payload).status_code == 422


@pytest.mark.parametrize("p", [13, 20, 30])
def test_station_count_is_limited_only_by_the_candidate_list(p):
    response = client.post("/api/run", json={"p": p, "budget": 1000})
    assert response.status_code == 200
    result = response.json()
    assert len(result["methods"]["abc"]["candidate_ids"]) == p
    assert result["methods"]["abc"]["mean_distance_m"] >= result["exact"]["mean_distance_m"] - 1e-9
    routes = client.post(
        "/api/routes", json={"candidate_ids": result["methods"]["abc"]["candidate_ids"]}
    )
    assert routes.status_code == 200


def test_threshold_changes_coverage_but_not_the_walk():
    near = client.post("/api/run", json={"p": 4, "budget": 1000, "threshold_m": 100}).json()
    far = client.post("/api/run", json={"p": 4, "budget": 1000, "threshold_m": 900}).json()
    assert far["threshold_m"] == 900
    assert far["methods"]["abc"]["mean_distance_m"] == near["methods"]["abc"]["mean_distance_m"]
    assert far["methods"]["abc"]["coverage"] >= near["methods"]["abc"]["coverage"]
    assert client.post("/api/run", json={"threshold_m": 10}).status_code == 422


def test_analysis_accounts_for_all_demand_and_agrees_with_the_objective():
    _, problem, _ = dataset()
    selected = ["candidate-16", "candidate-18", "candidate-21", "candidate-22"]
    body = {"candidate_ids": selected, "scenario": "day", "threshold_m": 300}
    response = client.post("/api/analysis", json=body)
    assert response.status_code == 200
    result = response.json()
    indices = [problem.candidate_ids.index(name) for name in selected]
    whole = next(g for g in result["groups"] if g["group"] == "all")
    assert whole["mean_m"] == pytest.approx(problem.objective(indices, "day"))
    parts = [g for g in result["groups"] if g["group"] != "all"]
    assert sum(g["demand_share"] for g in parts) == pytest.approx(1)
    assert sum(g["buildings"] for g in parts) == len(problem.demand_ids)
    assert sum(s["demand_share"] for s in result["stations"]) == pytest.approx(1)
    assert {b["station"] for b in result["buildings"]} <= set(selected)
    for row in result["scenarios"]:
        assert row["mean_m"] == pytest.approx(problem.objective(indices, row["scenario"]))
        assert row["regret_percent"] >= -1e-9


def test_curve_is_monotone_and_marks_the_optimum():
    rows = client.post("/api/curve", json={"p_max": 6, "scenario": "morning"}).json()["rows"]
    assert [r["p"] for r in rows] == [1, 2, 3, 4, 5, 6]
    means = [r["mean_distance_m"] for r in rows]
    assert all(a >= b - 1e-9 for a, b in zip(means, means[1:], strict=False))
    assert rows[0]["gain_m"] is None and rows[1]["gain_m"] == pytest.approx(means[0] - means[1])


def test_series_repeats_seeds_and_never_beats_the_optimum():
    body = {"p": 3, "budget": 500, "seeds": 4}
    result = client.post("/api/series", json=body).json()
    assert len(result["methods"]["abc"]["values"]) == 4
    assert len(result["methods"]["greedy"]["values"]) == 1
    for summary in result["methods"].values():
        assert summary["best_m"] >= result["optimum_m"] - 1e-9
    assert client.post("/api/series", json={"seeds": 1}).status_code == 422


def test_robust_layout_is_a_valid_layout():
    result = client.post("/api/robust", json={"p": 3}).json()
    assert len(set(result["candidate_ids"])) == 3
    assert result["cost_on_aggregate_percent"] >= -1e-9


def test_dataset_states_the_smallest_budget_for_greedy():
    pools = client.get("/api/dataset").json()["pools"]
    assert pools["all"]["greedy_min_budget"][1] == 30 + 29
    assert len(pools["all"]["greedy_min_budget"]) == pools["all"]["count"]


def test_budget_too_small_for_greedy_is_explained_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(api, "greedy_construction_cost", lambda candidates, p: 900)
    response = client.post("/api/run", json={"p": 4, "budget": 500})
    assert response.status_code == 422
    assert "900" in response.json()["detail"]


def test_polish_names_survive_loading_regardless_of_the_system_locale():
    names = [point["name"] for point in client.get("/api/dataset").json()["demand"]]
    assert 'Hala TS "Wisła"' in names
    assert not any("Ĺ" in name or "Ă" in name for name in names)


def test_routes_lead_to_the_nearest_station_and_match_the_objective():
    _, problem, _ = dataset()
    selected = ["candidate-16", "candidate-18", "candidate-21", "candidate-22"]
    response = client.post("/api/routes", json={"candidate_ids": selected, "scenario": "day"})
    assert response.status_code == 200
    features = response.json()["features"]
    assert len(features) == len(problem.demand_ids)
    indices = [problem.candidate_ids.index(name) for name in selected]
    nearest = problem.nearest(indices)
    for i, feature in enumerate(features):
        assert feature["properties"]["candidate_id"] in selected
        assert feature["properties"]["distance_m"] == pytest.approx(nearest[i], abs=0.00051)
        assert len(feature["geometry"]["coordinates"]) >= 1


@pytest.mark.parametrize(
    "payload",
    [{"candidate_ids": []}, {"candidate_ids": ["candidate-99"]}, {"candidate_ids": "x"}],
)
def test_invalid_route_requests_are_rejected(payload):
    assert client.post("/api/routes", json=payload).status_code == 422


def test_map_exposes_a_building_height_and_its_origin():
    buildings = [
        f["properties"]
        for f in client.get("/api/map").json()["features"]
        if f["properties"]["kind"] == "building"
    ]
    assert buildings
    assert all(b["height_m"] > 0 and b["height_source"] for b in buildings)


def test_large_p_optimum_without_exact_and_busy_response():
    response = client.post("/api/run", json={"p": 12, "budget": 500})
    assert response.status_code == 200
    optimum = response.json()["exact"]["mean_distance_m"]
    assert response.json()["methods"]["abc"]["mean_distance_m"] >= optimum - 1e-9
    response = client.post("/api/run", json={"p": 12, "budget": 500, "include_exact": False})
    assert response.status_code == 200
    assert response.json()["exact"] is None
    assert np.isfinite(response.json()["methods"]["abc"]["mean_distance_m"])
    with run_lock:
        assert client.post("/api/run", json={}).status_code == 429


def test_dataset_and_offline_map_contract():
    assert client.get("/api/health").json()["status"] == "ok"
    data = client.get("/api/dataset").json()
    assert len(data["candidates"]) == 30
    assert len(data["demand"]) == 18
    response = client.get("/api/map")
    assert response.status_code == 200
    geometry = response.json()
    assert geometry["type"] == "FeatureCollection"
    assert {f["properties"]["kind"] for f in geometry["features"]} == {"walk", "building"}
    assert client.get("/api/unknown").status_code == 404
