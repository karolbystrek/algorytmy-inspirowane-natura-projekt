"""Independent check that routes of the reported layouts follow real paths and avoid buildings.

Rebuilds each route with NetworkX, compares its length with the matrix used by the solvers and
tests every edge against solid building outlines. Needs the geo extra and a local OSM extract:

    uv run --extra geo python scripts/verify_routes.py --pbf malopolskie-latest.osm.pbf
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import LineString, Point, box
from shapely.prepared import prep

from agh_stations.audit import write_json
from agh_stations.model import Problem
from agh_stations.osm_extract import read_extract
from agh_stations.prepare_v2 import crosses_footprint_legitimately
from agh_stations.solvers import optimal

STATION_COUNTS = (3, 5, 6, 8, 10, 15, 20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", required=True)
    parser.add_argument("--dataset", default="data/processed/agh-v2")
    parser.add_argument("--config", default="configs/agh-v2.json")
    parser.add_argument("--reports", default="reports/v2-draft")
    args = parser.parse_args()
    dataset = Path(args.dataset)
    raw = json.loads((dataset / "problem.json").read_text(encoding="utf-8"))
    problem = Problem.load(dataset / "problem.json")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    boundary, crs = box(*config["bbox_wgs84"]), config["crs_metric"]
    metric, _ = ox.projection.project_geometry(boundary, to_crs=crs)
    routing, _ = ox.projection.project_geometry(
        metric.buffer(config["routing_buffer_m"]), crs=crs, to_crs="EPSG:4326"
    )
    extract = read_extract(args.pbf, boundary, routing)
    tags = {(str(u), str(v)): d for u, v, _, d in extract.graph.edges(keys=True, data=True)}
    barriers = {str(n): d["barrier"] for n, d in extract.graph.nodes(data=True) if "barrier" in d}
    buildings = extract.buildings.to_crs(crs)
    interior = prep(buildings[buildings["building"] != "roof"].geometry.union_all().buffer(-0.05))
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform

    graph, position = nx.DiGraph(), {}
    features = json.loads((dataset / "map.geojson").read_text(encoding="utf-8"))["features"]
    for feature in features:
        props = feature["properties"]
        if props["kind"] != "walk":
            continue
        position[props["u"]], position[props["v"]] = feature["geometry"]["coordinates"]
        known = graph.get_edge_data(props["u"], props["v"])
        if known is None or known["length"] > props["length_m"]:
            graph.add_edge(props["u"], props["v"], length=props["length_m"])

    layouts = {f"optimum p={p}": optimal(problem, p).selection for p in STATION_COUNTS}
    stations = Path(args.reports) / "recommended_stations.csv"
    if stations.exists():
        with stations.open(encoding="utf-8") as handle:
            identifiers = [row["id"] for row in csv.DictReader(handle)]
        layouts["etap 2 rekomendacji"] = tuple(
            problem.candidate_ids.index(identifier) for identifier in identifiers
        )

    lengths, passages, used_barriers = Counter(), Counter(), Counter()
    edges = crossing = mismatches = routes = unverified = 0
    connectors, detours = [], []
    for selection in layouts.values():
        chosen = list(selection)
        for i, demand in enumerate(raw["demand"]):
            j = chosen[int(problem.distances[i, chosen].argmin())]
            candidate = raw["candidates"][j]
            best = min(
                demand["access_points"],
                key=lambda a: (
                    a["access_m"]
                    + nx.dijkstra_path_length(
                        graph, a["node_id"], candidate["node_id"], weight="length"
                    )
                ),
            )
            path = nx.dijkstra_path(graph, best["node_id"], candidate["node_id"], weight="length")
            length = best["access_m"] + nx.path_weight(graph, path, weight="length")
            mismatches += abs(length - problem.distances[i, j]) > 0.01
            routes += 1
            connectors.append(best["access_m"])
            unverified += best["access_m"] > 0 and not best["connector_verified"]
            coordinates = [project(*position[node]) for node in path]
            for u, v, start, end in zip(path, path[1:], coordinates, coordinates[1:], strict=False):
                edges += 1
                edge = tags.get((u, v), {})
                lengths[str(edge.get("highway"))] += graph[u][v]["length"]
                if interior.intersects(LineString([start, end])):
                    if crosses_footprint_legitimately(edge):
                        passages[
                            edge.get("tunnel") or edge.get("covered") or edge.get("bridge")
                        ] += 1
                    else:
                        crossing += 1
            used_barriers.update(barriers[node] for node in path if node in barriers)
            straight = Point(project(best["lon"], best["lat"])).distance(
                Point(project(candidate["lon"], candidate["lat"]))
            )
            if straight > 50:
                detours.append(length / straight)
    total = sum(lengths.values())
    write_json(
        Path(args.reports) / "route_checks.json",
        {
            "layouts": list(layouts),
            "routes_checked": routes,
            "route_edges_checked": edges,
            "length_mismatches_vs_matrix": int(mismatches),
            "edges_crossing_solid_building_without_mapped_passage": crossing,
            "edges_in_mapped_passages": dict(passages),
            "length_share_percent_by_highway": {
                name: round(100 * value / total, 1) for name, value in lengths.most_common()
            },
            "barriers_on_routes": dict(used_barriers.most_common()),
            "connector_median_m": float(np.median(connectors)),
            "connector_max_m": float(max(connectors)),
            "connectors_used_without_verified_clearance": int(unverified),
            "detour_factor_median": float(np.median(detours)),
            "detour_factor_p90": float(np.quantile(detours, 0.9)),
            "detour_factor_max": float(max(detours)),
        },
    )


if __name__ == "__main__":
    main()
