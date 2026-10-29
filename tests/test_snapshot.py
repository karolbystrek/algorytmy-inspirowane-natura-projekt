"""Recompute routing from the exported graph, without any OSM service calls."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from agh_stations.model import Problem

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/agh-pilot"


def test_snapshot_hashes_and_matrix():
    manifest = json.loads((DATA / "manifest.json").read_text())
    for name, expected in manifest["files_sha256"].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected
    p = Problem.load(DATA / "problem.json")
    assert p.distances.shape == (18, 30)
    assert np.isfinite(p.distances).all()
    assert p.weights().sum() == pytest.approx(1)


def test_matrix_matches_exported_walking_graph():
    nx = pytest.importorskip("networkx")
    features = json.loads((DATA / "map.geojson").read_text())["features"]
    raw_problem = json.loads((DATA / "problem.json").read_text())
    graph = nx.MultiDiGraph()
    for feature in features:
        props = feature["properties"]
        if props["kind"] == "walk":
            graph.add_edge(props["u"], props["v"], length=props["length_m"])
    for i, demand in enumerate(raw_problem["demand"]):
        paths = nx.single_source_dijkstra_path_length(graph, demand["node_id"], weight="length")
        for j, candidate in enumerate(raw_problem["candidates"]):
            assert raw_problem["distances_m"][i][j] == pytest.approx(
                paths[candidate["node_id"]], abs=0.00051
            )
