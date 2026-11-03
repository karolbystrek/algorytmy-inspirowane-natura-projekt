"""Entrance provenance, geometric routing and an offline end-to-end demonstrator."""

import csv
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

nx = pytest.importorskip("networkx")
pytest.importorskip("shapely")
pytest.importorskip("pyproj")

from agh_stations.demo import export_routes, run_demo  # noqa: E402
from agh_stations.demo_data import (  # noqa: E402
    access_blocked,
    make_problem,
    prepare_dataset,
    read_json,
    walking_graph,
)
from agh_stations.model import Problem  # noqa: E402
from agh_stations.solvers import exact  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/agh-entrance-demo.json"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    directory = tmp_path_factory.mktemp("entrance-dataset")
    problem_data, graph, manifest = prepare_dataset(CONFIG, directory)
    return problem_data, graph, manifest, directory


def test_real_entrances_and_all_pair_distances(prepared):
    data, graph, manifest, directory = prepared
    config = read_json(CONFIG)
    source = read_json(ROOT / config["source"])
    buildings = {b["id"]: b for b in source["buildings"]}
    assert len(data["demand"]) == 5
    assert len(data["candidates"]) == 10
    assert manifest["quality"]["field_confirmed_points"] == 0
    assert data["verification"]["field_review"] == "pending"
    assert data["verification"]["desk_review"] == "map_checked"
    for i, demand in enumerate(data["demand"]):
        assert demand["node_id"] in buildings[demand["building_id"]]["node_ids"]
        assert graph.nodes[demand["node_id"]]["tags"]["entrance"] == "main"
        assert demand["lon"] == graph.nodes[demand["node_id"]]["lon"]
        distances = nx.single_source_dijkstra_path_length(
            graph, demand["node_id"], weight="length_m"
        )
        for j, candidate in enumerate(data["candidates"]):
            assert data["distances_m"][i][j] == pytest.approx(distances[candidate["node_id"]])
    assert Problem.load(directory / "problem.json").distances.shape == (5, 10)


def test_routes_are_real_edges_and_agree_with_objective(prepared):
    data, graph, _, directory = prepared
    problem = Problem.load(directory / "problem.json")
    optimum = exact(problem, 3)
    assert optimum.evaluations == 120
    routes = export_routes(data, graph, optimum.selection)["features"]
    assert len(routes) == 5
    total = 0
    for demand, route in zip(data["demand"], routes, strict=True):
        props = route["properties"]
        assert props["node_ids"][0] == demand["node_id"]
        assert len(props["edges"]) == len(props["node_ids"]) - 1
        assert route["geometry"]["coordinates"][0] == [demand["lon"], demand["lat"]]
        for edge in props["edges"]:
            actual = graph[edge["u"]][edge["v"]][edge["key"]]
            assert edge["length_m"] == actual["length_m"]
        assert sum(e["length_m"] for e in props["edges"]) == pytest.approx(props["length_m"])
        total += props["length_m"]
    assert total / 5 == pytest.approx(optimum.objective)


def synthetic_source(building=None, node_tags=None, edge_tags=None):
    source = {
        "nodes": [
            {"id": "a", "lon": 19.9048, "lat": 50.068, "tags": node_tags or {}},
            {"id": "b", "lon": 19.9052, "lat": 50.068, "tags": {}},
        ],
        "edges": [
            {
                "u": "a",
                "v": "b",
                "key": 0,
                "length_m": 30,
                "osm_way_id": "1",
                "tags": edge_tags or {"highway": "footway"},
            }
        ],
        "buildings": [],
    }
    if building:
        source["buildings"] = [
            {
                "id": "way/2",
                "tags": {"building": building},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [19.90495, 50.06795],
                            [19.90505, 50.06795],
                            [19.90505, 50.06805],
                            [19.90495, 50.06805],
                            [19.90495, 50.06795],
                        ]
                    ],
                },
            }
        ]
    return source


def test_canopy_keeps_existing_path_but_solid_building_blocks_it():
    roof_graph, _, _ = walking_graph(synthetic_source(building="roof"))
    solid_graph, _, excluded = walking_graph(synthetic_source(building="dormitory"))
    assert roof_graph.has_edge("a", "b")
    assert not solid_graph.has_edge("a", "b")
    assert excluded["building_interior"] == 1


@pytest.mark.parametrize(
    "tags",
    [
        {"highway": "footway", "foot": "no"},
        {"highway": "footway", "access": "private"},
        {"highway": "footway", "foot:conditional": "no @ (20:00-06:00)"},
        {"highway": "service"},
    ],
)
def test_disallowed_or_unresolved_edges_are_removed(tags):
    graph, _, _ = walking_graph(synthetic_source(edge_tags=tags))
    assert graph.number_of_edges() == 0


def test_gate_is_not_assumed_open_and_specific_foot_access_has_precedence():
    graph, _, _ = walking_graph(synthetic_source(node_tags={"barrier": "gate"}))
    assert len(graph) == 0
    assert not access_blocked({"access": "private", "foot": "yes"})
    assert access_blocked({"access": "yes", "foot": "private"})


def test_invalid_candidates_and_disconnections_fail_instead_of_dropping_points(prepared):
    _, graph, _, _ = prepared
    config = read_json(CONFIG)
    source = read_json(ROOT / config["source"])
    _, footprints, _ = walking_graph(source)
    bad = deepcopy(config)
    bad["candidates"][0]["node_id"] = config["demand"][0]["node_id"]
    with pytest.raises(ValueError, match="overlaps"):
        make_problem(source, bad, graph, footprints)
    disconnected = graph.copy()
    start = config["demand"][0]["node_id"]
    disconnected.remove_edges_from(list(disconnected.out_edges(start, keys=True)))
    with pytest.raises(ValueError, match="Unreachable"):
        make_problem(source, config, disconnected, footprints)
    bad = deepcopy(config)
    bad["verification"]["field_review"] = "confirmed"
    with pytest.raises(ValueError, match="cannot claim"):
        make_problem(source, bad, graph, footprints)


def test_one_command_flow_is_offline_and_exports_five_routes(tmp_path):
    pytest.importorskip("matplotlib")
    with patch("socket.create_connection", side_effect=AssertionError("Network is forbidden")):
        with patch(
            "requests.sessions.Session.request", side_effect=AssertionError("HTTP is forbidden")
        ):
            result = run_demo(CONFIG, tmp_path, runs=2, budget=120)
    verification = read_json(tmp_path / "verification.json")
    assert verification["counts"] == {
        "entrances": 5,
        "candidates": 10,
        "selected_stations": 3,
        "routes": 5,
    }
    assert "pending" in verification["field_review"]
    assert len(result["best_solutions"]["abc"]["selection"]) == 3
    assert result["summary"]["exact"]["best_m"] == pytest.approx(50.29069493496652)
    for method in ("abc", "greedy", "random"):
        assert result["summary"][method]["best_m"] >= result["summary"]["exact"]["best_m"] - 1e-9
    with (tmp_path / "field-review-template.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 15
    assert all(r["field_status"] == "pending" and r["field_checked_at"] == "" for r in rows)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    assert '<img src="http' not in html.lower()
    assert (tmp_path / "map.png").stat().st_size > 1000
    assert np.isfinite(result["summary"]["abc"]["mean_m"])
    from agh_stations.demo_data import write_json
    from agh_stations.report import render

    routes = read_json(tmp_path / "routes.geojson")
    routes["problem_sha256"] = "different-problem"
    write_json(tmp_path / "routes.geojson", routes)
    with pytest.raises(ValueError, match="Routes refer to a different"):
        render(tmp_path, tmp_path / "dataset")


def test_changed_source_hash_is_rejected(tmp_path):
    from agh_stations.demo_data import write_json

    config = read_json(CONFIG)
    config["source"] = str(ROOT / config["source"])
    config["source_sha256"] = "0" * 64
    write_json(tmp_path / "config.json", config)
    with pytest.raises(ValueError, match="Source snapshot differs"):
        prepare_dataset(tmp_path / "config.json", tmp_path / "dataset")
