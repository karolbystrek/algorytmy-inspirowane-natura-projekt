"""The browser contract uses the same model, limits and real improvement trace."""

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

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
        {"p": 13},
        {"p": 4.5},
        {"p": True},
        {"budget": 499},
        {"budget": 20001},
        {"seed": -1},
        {"scenario": "unknown"},
        {"unexpected": 1},
        {"p": 6, "include_exact": True},
    ],
)
def test_invalid_or_excessive_requests_are_rejected(payload):
    assert client.post("/api/run", json=payload).status_code == 422


def test_polish_names_survive_loading_regardless_of_the_system_locale():
    names = [point["name"] for point in client.get("/api/dataset").json()["demand"]]
    assert 'Hala TS "Wisła"' in names
    assert not any("Ĺ" in name or "Ă" in name for name in names)


def test_large_p_without_exact_and_busy_response():
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
