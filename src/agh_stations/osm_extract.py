"""Read the study area from a dated OSM extract, as an alternative to the shared Overpass service.

The walking graph follows the same rules as OSMnx ``network_type="walk"`` with
``simplify=False`` and ``retain_all=True``, so both sources describe the same network.
"""

import re
from dataclasses import dataclass
from typing import Any

BIKE_AMENITIES = {"bicycle_parking", "bicycle_rental", "kick-scooter_parking"}
OBSTACLE_LEISURE = {"pitch", "track", "stadium", "swimming_pool"}
BUILDING_COLUMNS = ("building", "name", "amenity", "leisure", "height", "building:levels")
# Copied from osmnx._overpass._get_network_filter("walk"), OSMnx 2.1.
WALK_EXCLUSIONS = {
    "area": "yes",
    "access": "private",
    "highway": (
        "abandoned|bus_guideway|construction|cycleway|motor|no|planned|platform|proposed"
        "|raceway|razed|rest_area|services"
    ),
    "foot": "no",
    "service": "private",
    "sidewalk": "separate",
    "sidewalk:both": "separate",
    "sidewalk:left": "separate",
    "sidewalk:right": "separate",
}
BOUNDS_MARGIN_DEG = 0.01  # Coarse pre-check; buildings never extend further than this.


@dataclass
class Extract:
    graph: Any
    buildings: Any
    entrances: Any
    bike: Any
    obstacles: Any
    data_timestamp: str | None


def is_walkable(tags):
    """Overpass semantics: a missing key passes, and !~ is an unanchored regex search."""
    return "highway" in tags and not any(
        key in tags and re.search(pattern, tags[key]) for key, pattern in WALK_EXCLUSIONS.items()
    )


def _frame(rows, columns):
    import geopandas as gpd
    import pandas as pd

    index = pd.MultiIndex.from_tuples([r["key"] for r in rows], names=["element", "id"])
    data = {column: [r["tags"].get(column) for r in rows] for column in columns}
    return gpd.GeoDataFrame(
        data, geometry=[r["geometry"] for r in rows], crs="EPSG:4326", index=index
    )


def _in_bounds(lon, lat, bounds):
    return bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]


def read_extract(path, boundary, routing_boundary):
    """Everything the v2 builder needs from an .osm.pbf (or .osm XML) file."""
    import networkx as nx
    import osmium
    import osmnx as ox
    from shapely import wkb
    from shapely.geometry import Point
    from shapely.prepared import prep

    with_tags = osmium.filter.KeyFilter(
        "highway", "barrier", "access", "foot", "entrance", "amenity", "building", "natural",
        "leisure",
    )  # fmt: skip
    processor = (
        osmium.FileProcessor(str(path))
        .with_locations()
        .with_areas(osmium.filter.KeyFilter("building", "amenity", "natural", "leisure"))
        .with_filter(with_tags)
    )
    factory = osmium.geom.WKBFactory()
    routing_shape, boundary_shape = prep(routing_boundary), prep(boundary)
    routing_bounds = routing_boundary.bounds
    west, south, east, north = boundary.bounds
    near = (
        west - BOUNDS_MARGIN_DEG,
        south - BOUNDS_MARGIN_DEG,
        east + BOUNDS_MARGIN_DEG,
        north + BOUNDS_MARGIN_DEG,
    )
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    node_tags, inside = {}, {}
    buildings, entrances, bike, obstacles = [], [], [], []

    def in_routing_area(reference, location):
        if reference not in inside:
            lon, lat = location.lon, location.lat
            inside[reference] = _in_bounds(lon, lat, routing_bounds) and routing_shape.contains(
                Point(lon, lat)
            )
        return inside[reference]

    def add_way(way, tags):
        references = [(n.ref, n.location) for n in way.nodes if n.location.valid()]
        for (u, first), (v, second) in zip(references, references[1:], strict=False):
            if u == v or not (in_routing_area(u, first) and in_routing_area(v, second)):
                continue
            for reference, location in ((u, first), (v, second)):
                if reference not in graph:
                    graph.add_node(reference, x=location.lon, y=location.lat)
            length = float(ox.distance.great_circle(first.lat, first.lon, second.lat, second.lon))
            attributes = {"osmid": way.id, "length": length, **tags}
            graph.add_edge(u, v, **attributes)
            graph.add_edge(v, u, **attributes)

    def add_area(area, tags):
        building = "building" in tags
        bike_parking = tags.get("amenity") in BIKE_AMENITIES
        obstacle = tags.get("natural") == "water" or tags.get("leisure") in OBSTACLE_LEISURE
        if not (building or bike_parking or obstacle):
            return
        if not obstacle:  # Water can be huge, so only compact objects get the quick rejection.
            first = next(iter(area.outer_rings()), None)
            if first is None or not _in_bounds(first[0].lon, first[0].lat, near):
                return
        try:
            shape = wkb.loads(factory.create_multipolygon(area), hex=True)
        except RuntimeError:
            return  # Broken OSM geometry cannot be used by any later step.
        if not boundary_shape.intersects(shape):
            return
        if len(shape.geoms) == 1:
            shape = shape.geoms[0]
        kind = "way" if area.from_way() else "relation"
        row = {"key": (kind, area.orig_id()), "tags": tags, "geometry": shape}
        if building:
            buildings.append(row)
        if bike_parking:
            bike.append(row)
        if obstacle:
            obstacles.append(row)

    for item in processor:
        if item.is_node():
            if not item.location.valid():
                continue
            lon, lat = item.location.lon, item.location.lat
            if not _in_bounds(lon, lat, routing_bounds):
                continue
            tags = {t.k: t.v for t in item.tags}
            node_tags[item.id] = tags
            if boundary_shape.contains(Point(lon, lat)):
                row = {"key": ("node", item.id), "tags": tags, "geometry": Point(lon, lat)}
                if "entrance" in tags:
                    entrances.append(row)
                if tags.get("amenity") in BIKE_AMENITIES:
                    bike.append(row)
        elif item.is_way():
            if "highway" in item.tags:
                tags = {t.k: t.v for t in item.tags}
                if is_walkable(tags):
                    add_way(item, tags)
        elif item.is_area():
            add_area(item, {t.k: t.v for t in item.tags})
    for node, tags in node_tags.items():
        if node in graph:
            graph.nodes[node].update(
                {k: v for k, v in tags.items() if k in ("access", "foot", "barrier", "entrance")}
            )
    if not buildings or not len(graph):
        raise ValueError("The extract does not cover the study area")
    reader = osmium.io.Reader(str(path), osmium.osm.osm_entity_bits.NOTHING)
    timestamp = reader.header().get("osmosis_replication_timestamp") or None
    reader.close()
    return Extract(
        graph,
        _frame(buildings, BUILDING_COLUMNS),
        _frame(entrances, ("entrance",)) if entrances else _frame_empty(("entrance",)),
        _frame(bike, ("amenity",)) if bike else _frame_empty(("amenity",)),
        _frame(obstacles, ("natural", "leisure"))
        if obstacles
        else _frame_empty(("natural", "leisure")),
        timestamp,
    )


def _frame_empty(columns):
    import geopandas as gpd

    return gpd.GeoDataFrame({**{c: [] for c in columns}, "geometry": []}, crs="EPSG:4326")
