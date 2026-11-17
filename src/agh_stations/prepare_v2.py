"""Second dataset: every relevant building, its entrances, and candidates close to real demand.

Everything here is derived from OSM tags and stated assumptions. Each point stays
``requires_review`` until a person records a field decision in the audit sheet.
"""

import json
import platform
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from agh_stations.audit import digest, write_json, write_lf

CONNECTOR_NEIGHBOURS = 30


def retrying(fetch, attempts=5, first_wait_s=30):
    """Overpass is a shared service: back off when it reports that it is at capacity."""
    import osmnx as ox
    import requests

    for attempt in range(attempts):
        try:
            return fetch()
        except (requests.RequestException, ox._errors.ResponseStatusCodeError) as error:
            if attempt == attempts - 1:
                raise
            wait = first_wait_s * 2**attempt
            print(f"Overpass unavailable ({type(error).__name__}); retrying in {wait} s")
            time.sleep(wait)


def features(polygon, tags):
    """A query with no matches is a valid, empty answer rather than a failure."""
    import geopandas as gpd
    import osmnx as ox

    try:
        return retrying(lambda: ox.features_from_polygon(polygon, tags=tags))
    except ox._errors.InsufficientResponseError:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")


def text_value(row, key):
    value = row.get(key)
    return value if isinstance(value, str) else None


def parse_number(value):
    match = re.match(r"^\s*(\d+(?:[.,]\d+)?)", value) if isinstance(value, str) else None
    return float(match.group(1).replace(",", ".")) if match else None


def classify(row, footprint, rules):
    """Category from OSM function tags, or None when the building creates no modelled demand."""
    name = text_value(row, "name") or ""
    if footprint < rules["min_footprint_m2"] or any(
        pattern in name for pattern in rules["excluded_name_patterns"]
    ):
        return None
    building, amenity = text_value(row, "building"), text_value(row, "amenity")
    if building == "dormitory" or amenity == "dormitory":
        return "dorm"
    if building in {"university", "college"} or amenity in {"university", "college"}:
        return "teaching"
    if amenity in rules["other_amenity"] or text_value(row, "leisure") in rules["other_leisure"]:
        return "other"
    if building == "retail" and footprint >= rules["retail_min_footprint_m2"]:
        return "other"
    return None


def assumed_levels(row, category_median, rules):
    """Levels when OSM has none: a sports hall is one tall room, not a typical campus building."""
    default = rules["default_levels_by_leisure"].get(text_value(row, "leisure"))
    return (default, "function_default") if default else (category_median, "category_median")


def scenario_weights(demand, intensity, scenarios):
    """Trips per scenario: floor area times an intensity for the building's function.

    A category's share of demand is a result of how much of it exists on campus. Fixing that
    share in advance would give a few small buildings the weight of the whole category.
    """
    return {
        scenario: [
            round(intensity[item["category"]][scenario] * item["floor_area_m2"] / 1000, 6)
            for item in demand
        ]
        for scenario in scenarios
    }


def building_height(row, config):
    """Height with its origin, so the map can mark what is only approximate."""
    height = parse_number(row.get("height"))
    if height and height > 0:
        return height, "height"
    levels = parse_number(row.get("building:levels"))
    if levels and levels > 0:
        return levels * config["assumed_level_height_m"], "levels"
    return config["assumed_building_height_m"], "assumed"


def crosses_footprint_legitimately(tags):
    """Mapped passages, underpasses and bridges really do cross a building outline."""
    return (
        tags.get("tunnel") not in (None, "no")
        or tags.get("bridge") not in (None, "no")
        or tags.get("covered") == "yes"
    )


def choose_connector(start, polygon, own_index, node_tree, node_ids, node_xy, tree, canopies):
    """Nearest graph node whose straight connector does not pass through a solid building."""
    from shapely.geometry import LineString, Point

    count = min(CONNECTOR_NEIGHBOURS, len(node_ids))
    distances, indices = node_tree.query([start.x, start.y], k=count)
    interior = polygon.buffer(-0.3)
    for distance, index in zip(np.atleast_1d(distances), np.atleast_1d(indices), strict=True):
        line = LineString([start, Point(*node_xy[index])])
        blocked = any(
            int(other) != own_index and int(other) not in canopies
            for other in tree.query(line, predicate="intersects")
        )
        if not blocked and line.intersection(interior).length < 0.5:
            return node_ids[index], float(distance), True
    return node_ids[int(np.atleast_1d(indices)[0])], float(np.atleast_1d(distances)[0]), False


def prepare(config_path, output_dir, raw_dir="data/raw", refresh=False, pbf=None):
    import geopandas as gpd
    import networkx as nx
    import osmnx as ox
    from scipy.spatial import cKDTree
    from shapely import STRtree
    from shapely.geometry import LineString, Point, box, mapping
    from shapely.ops import nearest_points
    from shapely.prepared import prep

    config_path, output_dir, raw_dir = Path(config_path), Path(output_dir), Path(raw_dir)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.log_console = False
    ox.settings.cache_folder = str(raw_dir / "osmnx-cache")
    ox.settings.requests_timeout = 90
    ox.settings.http_user_agent = "agh-stations/0.2 (student research; small cached AOI)"
    ox.settings.useful_tags_node = sorted(
        set(ox.settings.useful_tags_node) | {"access", "foot", "barrier", "entrance"}
    )
    ox.settings.useful_tags_way = sorted(
        set(ox.settings.useful_tags_way)
        | {"access", "foot", "access:conditional", "foot:conditional", "indoor", "tunnel"}
    )
    crs = config["crs_metric"]
    boundary = box(*config["bbox_wgs84"])
    metric_boundary, _ = ox.projection.project_geometry(boundary, to_crs=crs)
    routing_boundary, _ = ox.projection.project_geometry(
        metric_boundary.buffer(config["routing_buffer_m"]), crs=crs, to_crs="EPSG:4326"
    )
    provenance = {"retrieved_at_utc": datetime.now(UTC).isoformat()}
    if pbf:
        from agh_stations.osm_extract import read_extract

        extract = read_extract(pbf, boundary, routing_boundary)
        graph, buildings = extract.graph, extract.buildings
        entrances, bike, obstacles = extract.entrances, extract.bike, extract.obstacles
        provenance |= {
            "extract_file": Path(pbf).name,
            "extract_sha256": digest(pbf),
            "osm_data_timestamp": extract.data_timestamp,
        }
    else:
        graph_path = raw_dir / f"{digest(config_path)[:12]}-walk.graphml"
        if graph_path.exists() and not refresh:
            graph = ox.load_graphml(graph_path)
        else:
            graph = retrying(
                lambda: ox.graph_from_polygon(
                    routing_boundary, network_type="walk", simplify=False, retain_all=True
                )
            )
            ox.save_graphml(graph, graph_path)
        buildings = features(boundary, {"building": True})
        entrances = features(boundary, {"entrance": True})
        bike = features(
            boundary,
            {"amenity": ["bicycle_parking", "bicycle_rental", "kick-scooter_parking"]},
        )
        obstacles = features(
            boundary,
            {"natural": ["water"], "leisure": ["pitch", "track", "stadium", "swimming_pool"]},
        )
        provenance["endpoint"] = ox.settings.overpass_url
    buildings = buildings[buildings.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    buildings["osm_id"] = [f"{kind}/{identifier}" for kind, identifier in buildings.index]
    buildings = buildings.sort_values("osm_id").reset_index(drop=True)

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

    # A mapped roof is a canopy: paths may run beneath it and stations may stand under it.
    metric_buildings = buildings.to_crs(crs)
    roof_rows = metric_buildings["building"] == "roof"
    canopies = {int(i) for i in np.flatnonzero(roof_rows.to_numpy())}
    solid_buildings = metric_buildings[~roof_rows]
    solid_interiors = prep(solid_buildings.geometry.union_all().buffer(-0.05))
    routing_rules = config["routing"]
    barrier_nodes = [
        n
        for n, tags in graph.nodes(data=True)
        if tags.get("barrier") in routing_rules["blocked_barriers"]
    ]
    graph.remove_nodes_from(barrier_nodes)
    metric_graph = ox.project_graph(graph, to_crs=crs)
    indoor_edges, interior_edges = [], []
    for u, v, key, data in graph.edges(keys=True, data=True):
        if (
            data.get("indoor") == "yes"
            or "access:conditional" in data
            or "foot:conditional" in data
        ):
            indoor_edges.append((u, v, key))
            continue
        if crosses_footprint_legitimately(data):
            continue
        ends = [(metric_graph.nodes[n]["x"], metric_graph.nodes[n]["y"]) for n in (u, v)]
        if solid_interiors.intersects(LineString(ends)):
            interior_edges.append((u, v, key))
    graph.remove_edges_from(indoor_edges + interior_edges)
    components = sorted(nx.strongly_connected_components(graph), key=len, reverse=True)
    if not components:
        raise ValueError("No walkable components found")
    graph = graph.subgraph(components[0]).copy()
    projected = ox.project_graph(graph, to_crs=crs)
    node_ids = sorted(projected.nodes)
    node_xy = np.asarray([(projected.nodes[n]["x"], projected.nodes[n]["y"]) for n in node_ids])
    node_tree = cKDTree(node_xy)

    metric_entrances = entrances[entrances.geom_type == "Point"].to_crs(crs)
    usable_entrances = metric_entrances[
        ~metric_entrances["entrance"].isin(config["demand"]["ignored_entrance_types"])
    ]
    geometries = list(metric_buildings.geometry)
    building_tree = STRtree(geometries)
    entrance_points = list(usable_entrances.geometry)
    entrance_tree = STRtree(entrance_points) if entrance_points else None
    to_wgs = gpd.GeoSeries(crs=crs)

    def wgs(point):
        converted = gpd.GeoSeries([point], crs=to_wgs.crs).to_crs("EPSG:4326").iloc[0]
        return float(converted.x), float(converted.y)

    selected, not_connected, heights = [], [], {}
    known_levels = {"dorm": [], "teaching": [], "other": []}
    for index, row in metric_buildings.iterrows():
        heights[row["osm_id"]] = building_height(row, config)
        footprint = float(row.geometry.area)
        category = classify(row, footprint, config["demand"])
        if category is None:
            continue
        levels = parse_number(row.get("building:levels"))
        if levels:
            known_levels[category].append(levels)
        selected.append((index, row, category, footprint, levels))

    demand = []
    for index, row, category, footprint, levels in selected:
        polygon = row.geometry
        near_entrances = []
        if entrance_tree is not None:
            hits = entrance_tree.query(polygon.buffer(1.5), predicate="intersects")
            near_entrances = [entrance_points[int(i)] for i in sorted(hits)]
        starts = near_entrances
        method = "osm_entrances"
        if not starts:
            method = "footprint_nearest_node"
            _, nearest_index = node_tree.query(
                [polygon.representative_point().x, polygon.representative_point().y]
            )
            node_point = Point(*node_xy[int(nearest_index)])
            starts = [nearest_points(polygon.boundary, node_point)[0]]
        access = []
        for start in starts:
            node, length, verified = choose_connector(
                start, polygon, index, node_tree, node_ids, node_xy, building_tree, canopies
            )
            lon, lat = wgs(start)
            access.append(
                {
                    "node_id": str(node),
                    "access_m": round(length, 3),
                    "lon": lon,
                    "lat": lat,
                    "connector_verified": verified,
                }
            )
        access = [a for a in access if a["access_m"] <= config["demand"]["max_connector_m"]]
        identifier = row["osm_id"]
        name = text_value(row, "name") or identifier
        if not access:
            not_connected.append({"id": identifier, "name": name})
            continue
        anchor = polygon.representative_point()
        lon, lat = wgs(anchor)
        fallback_levels, fallback_source = assumed_levels(
            row, float(np.median(known_levels[category] or [3.0])), config["demand"]
        )
        demand.append(
            {
                "id": identifier,
                "name": name,
                "category": category,
                "area_m2": round(footprint, 3),
                "levels": levels or fallback_levels,
                "levels_source": "osm" if levels else fallback_source,
                "floor_area_m2": round(footprint * (levels or fallback_levels), 3),
                "lon": lon,
                "lat": lat,
                "location_method": method,
                "access_points": access,
                "status": "requires_review",
            }
        )
    if not demand:
        raise ValueError("No demand points; review the demand rules")

    sources = sorted({a["node_id"] for d in demand for a in d["access_points"]})
    from_source = {
        source: nx.single_source_dijkstra_path_length(graph, int(source), weight="length")
        for source in sources
    }
    walk_to_demand = {}
    for paths in from_source.values():
        for node, length in paths.items():
            if length < walk_to_demand.get(node, float("inf")):
                walk_to_demand[node] = length

    rules = config["candidates"]
    frames = [solid_buildings.geometry.buffer(rules["building_clearance_m"])]
    if len(obstacles):
        solid = obstacles[obstacles.geom_type.isin(["Polygon", "MultiPolygon"])]
        frames.append(solid.to_crs(crs).geometry)
    obstacle_area = gpd.GeoSeries(np.concatenate([f.values for f in frames]), crs=crs).union_all()
    forbidden = set(rules["forbidden_only_highways"])

    def highway_types(node):
        types = set()
        for _, _, data in graph.edges(node, data=True):
            value = data.get("highway")
            types.update(value if isinstance(value, list) else [value])
        return types

    def eligible(node, index):
        point = Point(*node_xy[index])
        types = highway_types(node)
        return (
            metric_boundary.contains(point)
            and "barrier" not in graph.nodes[node]
            and walk_to_demand.get(node, float("inf")) <= rules["max_walk_to_demand_m"]
            and bool(types - forbidden)
            and not any(
                data.get("indoor") == "yes" or data.get("tunnel") not in (None, "no")
                for _, _, data in graph.edges(node, data=True)
            )
            and not obstacle_area.intersects(point)
        )

    allowed = [(node, i) for i, node in enumerate(node_ids) if eligible(node, i)]
    if not allowed:
        raise ValueError("No eligible candidates; review the candidate rules")
    allowed_xy = np.asarray([node_xy[i] for _, i in allowed])
    allowed_tree = cKDTree(allowed_xy)
    chosen, chosen_xy = [], []

    def add(position, source):
        xy = allowed_xy[position]
        if (
            chosen_xy
            and np.min(np.linalg.norm(np.asarray(chosen_xy) - xy, axis=1)) < (rules["spacing_m"])
        ):
            return
        chosen.append((allowed[position][0], source))
        chosen_xy.append(xy)

    # Places already equipped for parking bikes come first: they are the most plausible sites.
    if len(bike):
        metric_bike = bike.to_crs(crs).copy()
        metric_bike["osm_id"] = [f"{kind}/{identifier}" for kind, identifier in metric_bike.index]
        for _, row in metric_bike.sort_values("osm_id").iterrows():
            point = row.geometry.representative_point()
            distance, position = allowed_tree.query([point.x, point.y])
            if distance <= rules["bike_infrastructure_snap_m"]:
                add(int(position), f"osm_{row['amenity']}")
    order = sorted(
        range(len(allowed)), key=lambda i: (walk_to_demand[allowed[i][0]], allowed[i][0])
    )
    for position in order:
        add(position, "graph_node_near_demand")

    candidates = [
        {
            "id": f"candidate-{j:03d}",
            "node_id": str(node),
            "lon": float(graph.nodes[node]["x"]),
            "lat": float(graph.nodes[node]["y"]),
            "source": source,
            "status": "requires_review",
        }
        for j, (node, source) in enumerate(chosen)
    ]
    matrix = [
        [
            round(
                min(
                    a["access_m"] + from_source[a["node_id"]][int(c["node_id"])]
                    for a in d["access_points"]
                ),
                3,
            )
            for c in candidates
        ]
        for d in demand
    ]
    # OSM rarely says whether a gate is locked, so measure the worst case instead of guessing.
    unverified_gates = routing_rules["unverified_gates"]
    gate_nodes = {
        n for n, tags in graph.nodes(data=True) if tags.get("barrier") in unverified_gates
    }
    with_gates_closed = graph.copy()
    with_gates_closed.remove_nodes_from(gate_nodes)
    closed_paths = {
        source: nx.single_source_dijkstra_path_length(
            with_gates_closed, int(source), weight="length"
        )
        if int(source) in with_gates_closed
        else {}
        for source in sources
    }

    def closed_distance(item, candidate):
        options = [
            a["access_m"] + closed_paths[a["node_id"]][int(candidate["node_id"])]
            for a in item["access_points"]
            if int(candidate["node_id"]) in closed_paths[a["node_id"]]
        ]
        return round(min(options), 3) if options else None

    closed_matrix = [[closed_distance(d, c) for c in candidates] for d in demand]
    intensity = config["demand_intensity_per_1000m2"]
    scenarios = scenario_weights(demand, intensity, config["scenario_mixture"])
    mixture_total = sum(config["scenario_mixture"].values())
    share_of_demand = {category: 0.0 for category in sorted({d["category"] for d in demand})}
    for scenario, weights in scenarios.items():
        for item, weight in zip(demand, weights, strict=True):
            share_of_demand[item["category"]] += (
                config["scenario_mixture"][scenario] / mixture_total * weight / sum(weights)
            )
    problem = {
        "schema_version": 1,
        "dataset_id": config["name"],
        "candidates": candidates,
        "demand": demand,
        "distances_m": matrix,
        "distances_m_gates_closed": closed_matrix,
        "scenarios": scenarios,
        "scenario_mixture": config["scenario_mixture"],
        "demand_intensity_per_1000m2": intensity,
        "fixed_category_totals_for_sensitivity": config["fixed_category_totals_for_sensitivity"],
        "demand_is_assumed": True,
        "routing_note": "Distance = straight connector from entrance to graph + walking route.",
    }
    problem_path = output_dir / "problem.json"
    write_json(problem_path, problem)

    feature_list = []
    for _, row in buildings.iterrows():
        height, source = heights[row["osm_id"]]
        feature_list.append(
            {
                "type": "Feature",
                "geometry": mapping(row.geometry),
                "properties": {
                    "kind": "building",
                    "id": row["osm_id"],
                    "height_m": height,
                    "height_source": source,
                },
            }
        )
    for u, v, key, data in graph.edges(keys=True, data=True):
        feature_list.append(
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
    for kind, rows in (("candidate", candidates), ("demand", demand)):
        for item in rows:
            properties = {k: v for k, v in item.items() if k != "access_points"}
            feature_list.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [item["lon"], item["lat"]]},
                    "properties": {"kind": kind, **properties},
                }
            )
    map_path = output_dir / "map.geojson"
    write_lf(
        map_path,
        json.dumps(
            {"type": "FeatureCollection", "features": feature_list},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
    )

    def count(rows, key, value):
        return sum(row[key] == value for row in rows)

    write_json(
        output_dir / "manifest.json",
        {
            "dataset_id": config["name"],
            "schema_version": 1,
            "source": {
                **provenance,
                "attribution": "© OpenStreetMap contributors",
                "license": "https://opendatacommons.org/licenses/odbl/1-0/",
            },
            "config": config,
            "config_sha256": digest(config_path),
            "files_sha256": {p.name: digest(p) for p in (problem_path, map_path)},
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
                "component_sizes_before_largest_selection": [len(c) for c in components[:20]],
                "candidate_count": len(candidates),
                "reviewed_candidate_count": 0,
                "candidate_sources": {
                    source: count(candidates, "source", source)
                    for source in sorted({c["source"] for c in candidates})
                },
                "demand_count": len(demand),
                "demand_by_category": {
                    category: count(demand, "category", category) for category in share_of_demand
                },
                "demand_share_by_category": {
                    category: round(share, 4) for category, share in share_of_demand.items()
                },
                "demand_with_osm_entrances": count(demand, "location_method", "osm_entrances"),
                "demand_without_verified_connector": sum(
                    not any(a["connector_verified"] for a in d["access_points"]) for d in demand
                ),
                "max_connector_m": max(a["access_m"] for d in demand for a in d["access_points"]),
                "demand_buildings_not_connected": not_connected,
                "building_height_sources": {
                    source: sum(s == source for _, s in heights.values())
                    for source in ("height", "levels", "assumed")
                },
                "matrix_finite": bool(np.isfinite(matrix).all()),
                "blocked_barrier_nodes_removed": len(barrier_nodes),
                "indoor_or_conditional_edges_removed": len(indoor_edges),
                "edges_inside_solid_buildings_removed": len(interior_edges),
                "canopies_not_treated_as_obstacles": len(canopies),
                "unverified_gate_nodes_kept_open": len(gate_nodes),
                "pairs_unreachable_with_gates_closed": sum(
                    value is None for row in closed_matrix for value in row
                ),
            },
            "limitations": [
                "No point has been checked on site; every status is requires_review.",
                "Demand weights are assumptions: floor area times an intensity per function.",
                "Connector legs are straight lines from an entrance to the walking graph.",
                "Buildings without an OSM entrance use the point on the outline nearest the graph.",
                "Largest strongly connected component only; audit excluded components.",
                "OSM rarely says whether a gate is locked; gates stay open in the main matrix.",
            ],
        },
    )
    print(json.dumps({"candidates": len(candidates), "demand": len(demand)}, indent=2))
