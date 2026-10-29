"""Small OSM pilot builder. Automatic locations are explicitly unreviewed proxies."""

import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spread(nodes, count, positions):
    """Deterministic farthest-first sampling in projected metres."""
    remaining = sorted(nodes)
    selected = [remaining.pop(0)] if remaining else []
    while remaining and len(selected) < count:
        best = max(
            remaining,
            key=lambda n: min(
                (positions[n][0] - positions[s][0]) ** 2 + (positions[n][1] - positions[s][1]) ** 2
                for s in selected
            ),
        )
        selected.append(best)
        remaining.remove(best)
    return selected


def prepare(config_path, output_dir, raw_dir="data/raw", refresh=False):
    import geopandas as gpd
    import networkx as nx
    import osmnx as ox
    from shapely.geometry import Point, box, mapping

    config_path, output_dir, raw_dir = Path(config_path), Path(output_dir), Path(raw_dir)
    config = json.loads(config_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.log_console = True
    ox.settings.cache_folder = str(raw_dir / "osmnx-cache")
    ox.settings.requests_timeout = 60
    ox.settings.http_user_agent = "agh-stations/0.1 (student research; small cached AOI)"
    ox.settings.useful_tags_node = sorted(
        set(ox.settings.useful_tags_node) | {"access", "foot", "barrier", "entrance"}
    )
    ox.settings.useful_tags_way = sorted(
        set(ox.settings.useful_tags_way)
        | {"access", "foot", "access:conditional", "foot:conditional"}
    )
    boundary = box(*config["bbox_wgs84"])
    metric_boundary, _ = ox.projection.project_geometry(boundary, to_crs=config["crs_metric"])
    routing_boundary, _ = ox.projection.project_geometry(
        metric_boundary.buffer(config["routing_buffer_m"]),
        crs=config["crs_metric"],
        to_crs="EPSG:4326",
    )
    # A config hash prevents accidentally reusing the cache for a different AOI.
    cache_id = digest(config_path)[:12]
    graph_path = raw_dir / f"{cache_id}-walk.graphml"
    buildings_path = raw_dir / f"{cache_id}-buildings.geojson"
    source_path = raw_dir / f"{cache_id}-source.json"
    if not refresh and graph_path.exists() and buildings_path.exists() and source_path.exists():
        graph = ox.load_graphml(graph_path)
        buildings = gpd.read_file(buildings_path)
        source = json.loads(source_path.read_text())
    else:
        if graph_path.exists() and not refresh:
            graph = ox.load_graphml(graph_path)
        else:
            graph = ox.graph_from_polygon(
                routing_boundary, network_type="walk", simplify=False, retain_all=True
            )
            # Preserve a successful graph download if the subsequent features request fails.
            ox.save_graphml(graph, graph_path)
        buildings = ox.features_from_polygon(boundary, tags={"building": True})
        buildings = buildings[buildings.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
        buildings["osm_id"] = [f"{kind}/{oid}" for kind, oid in buildings.index]
        # Keep only portable scalar columns in the raw feature snapshot.
        cols = [c for c in ["osm_id", "name", "building", "amenity", "geometry"] if c in buildings]
        buildings = buildings[cols].reset_index(drop=True)
        buildings.to_file(buildings_path, driver="GeoJSON")
        source = {
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
            "endpoint": ox.settings.overpass_url,
            "snapshot_mode": "live cached responses; retrieved_at_utc is not a historical OSM date",
        }
        source_path.write_text(json.dumps(source, indent=2) + "\n")

    if "cached_response_inventory" not in source:
        source["cached_response_inventory"] = []
        for path in sorted((raw_dir / "osmnx-cache").glob("*.json")):
            response = json.loads(path.read_text())
            source["cached_response_inventory"].append(
                {
                    "cache_file": path.name,
                    "sha256": digest(path),
                    "timestamp_osm_base": response.get("osm3s", {}).get("timestamp_osm_base"),
                }
            )
        source_path.write_text(json.dumps(source, indent=2) + "\n")

    def blocked(tags):
        foot = tags.get("foot")
        return foot in {"no", "private"} or (
            tags.get("access") in {"no", "private"}
            and foot not in {"yes", "designated", "permissive"}
        )

    raw_nodes = len(graph)
    blocked_nodes = [n for n, tags in graph.nodes(data=True) if blocked(tags)]
    graph.remove_nodes_from(blocked_nodes)
    blocked_edges = [(u, v, k) for u, v, k, d in graph.edges(keys=True, data=True) if blocked(d)]
    graph.remove_edges_from(blocked_edges)
    component_sizes = sorted(
        (len(c) for c in nx.strongly_connected_components(graph)), reverse=True
    )
    if not component_sizes:
        raise ValueError("No walkable components found")
    graph = graph.subgraph(max(nx.strongly_connected_components(graph), key=len)).copy()
    projected = ox.project_graph(graph, to_crs=config["crs_metric"])
    positions = {n: (d["x"], d["y"]) for n, d in projected.nodes(data=True)}
    projected_buildings = buildings.to_crs(config["crs_metric"])
    obstacle = projected_buildings.geometry.union_all().buffer(
        config["candidate_building_clearance_m"]
    )
    eligible = [
        n
        for n, (x, y) in positions.items()
        if metric_boundary.contains(Point(x, y)) and not obstacle.intersects(Point(x, y))
    ]
    candidates = spread(eligible, config["candidate_count"], positions)
    if len(candidates) != config["candidate_count"]:
        raise ValueError("Insufficient candidate proxies; review AOI")
    demand_options = []
    position_nodes = list(positions)
    position_xy = np.asarray([positions[n] for n in position_nodes])
    for _, row in projected_buildings.iterrows():
        if row.geometry.area < 150:
            continue
        centroid = row.geometry.representative_point()
        offset_squared = ((position_xy - [centroid.x, centroid.y]) ** 2).sum(axis=1)
        node = position_nodes[int(np.argmin(offset_squared))]
        if not metric_boundary.contains(Point(*positions[node])):
            continue
        kind = str(row.get("building", ""))
        name = row.get("name")
        name = str(name) if isinstance(name, str) else str(row["osm_id"])
        category = (
            "dorm"
            if kind == "dormitory"
            else (
                "teaching"
                if kind in {"university", "college", "school"} or row.get("amenity") == "university"
                else "other"
            )
        )
        demand_options.append(
            {
                "id": str(row["osm_id"]),
                "node": node,
                "name": name,
                "category": category,
                "area_m2": float(row.geometry.area),
                "proxy_offset_m": round(Point(*positions[node]).distance(centroid), 3),
            }
        )
    # Take a mix of functions, then fill unused places; prioritize larger footprints per class.
    demand_options.sort(key=lambda d: (-d["area_m2"], d["id"]))
    demand, used_nodes = [], set()
    quota = max(1, config["demand_count"] // 3)
    for category in ("dorm", "teaching", "other", None):
        taken = 0
        for item in demand_options:
            if len(demand) == config["demand_count"]:
                break
            if item["node"] in used_nodes or (category and item["category"] != category):
                continue
            if category and taken == quota:
                break
            demand.append(item)
            used_nodes.add(item["node"])
            taken += 1
    if len(demand) != config["demand_count"]:
        raise ValueError("Insufficient distinct demand proxies")

    matrix = []
    for item in demand:
        distances = nx.single_source_dijkstra_path_length(graph, item["node"], weight="length")
        matrix.append([round(distances[n], 3) for n in candidates])
    weights_by_category = {"dorm": (4, 1, 4), "teaching": (3, 5, 1), "other": (1, 2, 3)}
    scenarios = {
        scenario: [weights_by_category[item["category"]][i] for item in demand]
        for i, scenario in enumerate(("morning", "day", "evening"))
    }

    def location(node):
        return {"node_id": str(node), "lon": graph.nodes[node]["x"], "lat": graph.nodes[node]["y"]}

    candidate_rows = [
        {"id": f"candidate-{i:02d}", **location(n), "status": "requires_review"}
        for i, n in enumerate(candidates)
    ]
    demand_rows = [
        {
            **{k: v for k, v in item.items() if k != "node"},
            **location(item["node"]),
            "location_method": "nearest_graph_node_to_building_representative_point",
        }
        for item in demand
    ]
    problem = {
        "schema_version": 1,
        "dataset_id": config["name"],
        "candidates": candidate_rows,
        "demand": demand_rows,
        "distances_m": matrix,
        "scenarios": scenarios,
        "scenario_mixture": config["scenario_mixture"],
        "demand_is_assumed": True,
        "routing_note": "Graph-node proxies; building-to-graph access paths are NOT modelled.",
    }
    problem_path = output_dir / "problem.json"
    problem_path.write_text(json.dumps(problem, ensure_ascii=False, indent=2) + "\n")
    features = []
    for _, row in buildings.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(row.geometry),
                "properties": {"kind": "building", "id": row["osm_id"]},
            }
        )
    for u, v, key, data in graph.edges(keys=True, data=True):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[graph.nodes[n]["x"], graph.nodes[n]["y"]] for n in (u, v)],
                },
                "properties": {
                    "kind": "walk",
                    "u": str(u),
                    "v": str(v),
                    "key": key,
                    "length_m": data["length"],
                },
            }
        )
    for kind, rows in (("candidate", candidate_rows), ("demand", demand_rows)):
        for item in rows:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [item["lon"], item["lat"]]},
                    "properties": {"kind": kind, **item},
                }
            )
    map_path = output_dir / "map.geojson"
    map_path.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    manifest = {
        "dataset_id": config["name"],
        "schema_version": 1,
        "source": {
            **source,
            "attribution": "© OpenStreetMap contributors",
            "license": "https://opendatacommons.org/licenses/odbl/1-0/",
        },
        "config": config,
        "config_sha256": digest(config_path),
        "files_sha256": {p.name: digest(p) for p in (problem_path, map_path)},
        "raw_sha256": {p.name: digest(p) for p in (graph_path, buildings_path, source_path)},
        "versions": {
            "python": platform.python_version(),
            "osmnx": ox.__version__,
            "networkx": nx.__version__,
            "numpy": np.__version__,
        },
        "quality": {
            "raw_graph_nodes": raw_nodes,
            "retained_graph_nodes": len(graph),
            "retained_graph_edges": graph.number_of_edges(),
            "buildings": len(buildings),
            "blocked_nodes_removed": len(blocked_nodes),
            "blocked_edges_removed": len(blocked_edges),
            "component_sizes_before_largest_selection": component_sizes,
            "candidate_count": len(candidates),
            "reviewed_candidate_count": 0,
            "demand_count": len(demand),
            "demand_options_before_sampling": len(demand_options),
            "max_proxy_offset_m": max(d["proxy_offset_m"] for d in demand),
            "barrier_nodes_requiring_review": sum(
                "barrier" in d for _, d in graph.nodes(data=True)
            ),
            "conditional_edges_requiring_review": sum(
                "access:conditional" in d or "foot:conditional" in d
                for _, _, d in graph.edges(data=True)
            ),
            "matrix_finite": bool(np.isfinite(matrix).all()),
        },
        "limitations": [
            "Largest strongly connected component only; audit excluded components.",
            "Demand locations are graph-node proxies, not verified building entrances.",
            "Demand weights are illustrative assumptions, not measured travel flows.",
            "Candidates exclude building buffers only; review land, space, water and barriers.",
            "Unknown gates and conditional restrictions are reported but not resolved.",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(manifest["quality"], indent=2))
