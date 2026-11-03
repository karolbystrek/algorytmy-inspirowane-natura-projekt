"""Build a small, auditable entrance-based problem from a frozen OSM extract."""

import hashlib
import json
from pathlib import Path

import numpy as np


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def access_blocked(tags):
    return tags.get("foot") in {"no", "private"} or (
        tags.get("access") in {"no", "private"}
        and tags.get("foot") not in {"yes", "designated", "permissive"}
    )


def walking_graph(source, crs="EPSG:2180"):
    import networkx as nx
    from pyproj import Transformer
    from shapely import transform, union_all
    from shapely.geometry import LineString, shape

    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    buildings = [
        transform(shape(b["geometry"]), project, interleaved=False) for b in source["buildings"]
    ]
    footprints = union_all(buildings)
    solid_buildings = [
        geometry
        for building, geometry in zip(source["buildings"], buildings, strict=True)
        if building["tags"].get("building") != "roof"
    ]
    # A tiny inward tolerance allows a doorway exactly on a footprint boundary.
    # A mapped roof is a canopy, not a solid ground-level obstacle: keep mapped footways beneath it.
    interiors = union_all(solid_buildings).buffer(-0.05)
    graph = nx.MultiDiGraph()
    excluded = {"node_access_or_barrier": 0, "edge_access_or_type": 0, "building_interior": 0}
    for node in source["nodes"]:
        tags = node["tags"]
        if (
            access_blocked(tags)
            or tags.get("barrier") not in {None, "no", "kerb", "bollard"}
            or "access:conditional" in tags
            or "foot:conditional" in tags
        ):
            excluded["node_access_or_barrier"] += 1
            continue
        x, y = project(node["lon"], node["lat"])
        graph.add_node(node["id"], **node, x=x, y=y)
    allowed = {"footway", "path", "pedestrian", "steps", "living_street", "cycleway"}
    for edge in source["edges"]:
        tags = edge["tags"]
        if (
            edge["u"] not in graph
            or edge["v"] not in graph
            or tags.get("highway") not in allowed
            or access_blocked(tags)
            or tags.get("indoor") == "yes"
            or "access:conditional" in tags
            or "foot:conditional" in tags
        ):
            excluded["edge_access_or_type"] += 1
            continue
        length = edge["length_m"]
        if not np.isfinite(length) or length < 0:
            raise ValueError("OSM edge length must be finite and non-negative")
        coords = [(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (edge["u"], edge["v"])]
        if LineString(coords).intersects(interiors):
            excluded["building_interior"] += 1
            continue
        graph.add_edge(
            edge["u"],
            edge["v"],
            key=edge["key"],
            **{k: v for k, v in edge.items() if k not in {"u", "v", "key"}},
        )
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return graph, footprints, excluded


def make_problem(source, config, graph, footprints):
    import networkx as nx
    from shapely.geometry import Point

    buildings = {b["id"]: b for b in source["buildings"]}
    if config["verification"]["field_review"] != "pending":
        raise ValueError("This map-only dataset cannot claim field confirmation")
    if len(config["demand"]) != 5 or len(config["candidates"]) != 10:
        raise ValueError("The demonstrator requires exactly 5 entrances and 10 candidates")
    for rows in (config["demand"], config["candidates"]):
        if len({row["id"] for row in rows}) != len(rows):
            raise ValueError("Duplicate point IDs")
        if len({row["node_id"] for row in rows}) != len(rows):
            raise ValueError("Duplicate graph nodes")

    def location(row):
        if row["node_id"] not in graph:
            raise ValueError(f"{row['id']} is absent from the filtered walking graph")
        node = graph.nodes[row["node_id"]]
        return {**row, "lon": node["lon"], "lat": node["lat"], "field_review": "pending"}

    demand = []
    for row in config["demand"]:
        item = location(row)
        building = buildings[row["building_id"]]
        if row["node_id"] not in building["node_ids"]:
            raise ValueError(f"{row['id']} is not a node on the referenced OSM building")
        entrance = graph.nodes[row["node_id"]]["tags"].get("entrance")
        if entrance not in {"main", "yes"}:
            raise ValueError(f"{row['id']} is not a mapped usable entrance")
        item.update(
            location_method="osm_entrance_node",
            entrance_tag=entrance,
            source_url=f"https://www.openstreetmap.org/node/{row['node_id']}",
            building_url=f"https://www.openstreetmap.org/{row['building_id']}",
        )
        demand.append(item)
    candidates = []
    protected = footprints.buffer(config["building_clearance_m"])
    entrance_nodes = {row["node_id"] for row in demand}
    for row in config["candidates"]:
        item = location(row)
        node = graph.nodes[row["node_id"]]
        point = Point(node["x"], node["y"])
        if row["node_id"] in entrance_nodes or protected.intersects(point):
            raise ValueError(f"{row['id']} overlaps an entrance or building clearance")
        if node["tags"].get("barrier") not in {None, "no"}:
            raise ValueError(f"{row['id']} is on a barrier")
        if not row.get("reason"):
            raise ValueError(f"{row['id']} needs an explicit location rationale")
        for other in candidates:
            other_node = graph.nodes[other["node_id"]]
            if (
                point.distance(Point(other_node["x"], other_node["y"]))
                < config["minimum_candidate_spacing_m"]
            ):
                raise ValueError("Candidates violate the configured spacing")
        item.update(
            status="map_checked_field_pending",
            source_url=f"https://www.openstreetmap.org/node/{row['node_id']}",
        )
        candidates.append(item)
    matrix = []
    for item in demand:
        lengths = nx.single_source_dijkstra_path_length(graph, item["node_id"], weight="length_m")
        try:
            matrix.append([lengths[c["node_id"]] for c in candidates])
        except KeyError as error:
            raise ValueError(f"Unreachable candidate from {item['id']}; audit the graph") from error
    return {
        "schema_version": 1,
        "dataset_id": config["dataset_id"],
        "demand": demand,
        "candidates": candidates,
        "distances_m": matrix,
        "scenarios": {"uniform": [d["weight"] for d in demand]},
        "scenario_mixture": {"uniform": 1},
        "demand_is_assumed": True,
        "verification": config["verification"],
        "routing_note": "Starts at OSM entrance nodes; no invented off-network connectors.",
    }


def prepare_dataset(config_path, output_dir):
    config_path, output_dir = Path(config_path), Path(output_dir)
    config = read_json(config_path)
    source_path = config_path.resolve().parent.parent / config["source"]
    if sha256(source_path) != config["source_sha256"]:
        raise ValueError("Source snapshot differs from the hash reviewed in the config")
    source = read_json(source_path)
    graph, footprints, excluded = walking_graph(source, config["crs_metric"])
    problem = make_problem(source, config, graph, footprints)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "problem.json", problem)
    features = [
        {
            "type": "Feature",
            "geometry": b["geometry"],
            "properties": {
                "kind": "building",
                "id": b["id"],
                "name": b["tags"].get("name", ""),
            },
        }
        for b in source["buildings"]
    ]
    for u, v, key, data in graph.edges(keys=True, data=True):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[graph.nodes[n]["lon"], graph.nodes[n]["lat"]] for n in (u, v)],
                },
                "properties": {
                    "kind": "walk",
                    "u": u,
                    "v": v,
                    "key": key,
                    "length_m": data["length_m"],
                    "osm_way_id": data["osm_way_id"],
                },
            }
        )
    for kind, rows in (("demand", problem["demand"]), ("candidate", problem["candidates"])):
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                    "properties": {"kind": kind, **row},
                }
            )
    write_json(output_dir / "map.geojson", {"type": "FeatureCollection", "features": features})
    manifest = {
        "schema_version": 1,
        "dataset_id": config["dataset_id"],
        "source_sha256": sha256(source_path),
        "config_sha256": sha256(config_path),
        "files_sha256": {
            name: sha256(output_dir / name) for name in ("problem.json", "map.geojson")
        },
        "source": {k: v for k, v in source.items() if k not in {"nodes", "edges", "buildings"}},
        "quality": {
            "entrances": 5,
            "candidates": 10,
            "nodes": len(graph),
            "edges": graph.number_of_edges(),
            "excluded": excluded,
            "all_pairs_reachable": True,
            "field_confirmed_points": 0,
        },
        "verification": config["verification"],
    }
    write_json(output_dir / "manifest.json", manifest)
    return problem, graph, manifest
