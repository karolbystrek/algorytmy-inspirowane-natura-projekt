"""Real walking routes on the exported graph, so the map shows what the objective measures."""

import json
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra


def read_walk_edges(map_path):
    features = json.loads(Path(map_path).read_text(encoding="utf-8"))["features"]
    return [f for f in features if f["properties"]["kind"] == "walk"]


def walking_matrix(edges):
    """Sparse directed graph; parallel edges keep their shortest length, as routing would."""
    properties = [edge["properties"] for edge in edges]
    nodes = sorted({e["u"] for e in properties} | {e["v"] for e in properties})
    index = {node: i for i, node in enumerate(nodes)}
    best = {}
    for edge in properties:
        key = (index[edge["u"]], index[edge["v"]])
        best[key] = min(best.get(key, float("inf")), edge["length_m"])
    rows, columns = zip(*best, strict=True)
    graph = coo_matrix((list(best.values()), (rows, columns)), shape=(len(nodes), len(nodes)))
    return graph.tocsr(), nodes, index


def access_points(demand):
    """Entrances of a building, or the single graph node of a pilot demand point."""
    return demand.get("access_points") or [
        {"node_id": demand["node_id"], "access_m": 0.0, "lat": demand["lat"], "lon": demand["lon"]}
    ]


class Router:
    def __init__(self, map_path, raw_problem):
        edges = read_walk_edges(map_path)
        graph, nodes, self.index = walking_matrix(edges)
        self.nodes = nodes
        self.positions = {}
        for edge in edges:
            start, end = edge["geometry"]["coordinates"]
            self.positions[edge["properties"]["u"]] = start
            self.positions[edge["properties"]["v"]] = end
        self.demand = raw_problem["demand"]
        self.candidates = {c["id"]: c for c in raw_problem["candidates"]}
        sources = sorted({a["node_id"] for d in self.demand for a in access_points(d)})
        self.row = {node: i for i, node in enumerate(sources)}
        self.distances, self.predecessors = dijkstra(
            graph,
            directed=True,
            indices=[self.index[node] for node in sources],
            return_predecessors=True,
        )

    def route(self, demand_index, candidate_id):
        """Best entrance and the node sequence to the station; length includes the access leg."""
        target = self.index[self.candidates[candidate_id]["node_id"]]
        access = min(
            access_points(self.demand[demand_index]),
            key=lambda a: a["access_m"] + self.distances[self.row[a["node_id"]], target],
        )
        row = self.row[access["node_id"]]
        length = float(access["access_m"] + self.distances[row, target])
        if not np.isfinite(length):
            raise ValueError(f"No walking route to {candidate_id}")
        path, current = [], target
        while current >= 0:  # scipy marks the source with a negative predecessor.
            path.append(current)
            current = int(self.predecessors[row, current])
        coordinates = [self.positions[self.nodes[i]] for i in reversed(path)]
        if access["access_m"] > 0:
            coordinates.insert(0, [access["lon"], access["lat"]])
        return coordinates, length
