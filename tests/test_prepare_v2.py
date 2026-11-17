"""Tag rules of the v2 dataset, independent of any OSM service."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("osmnx")
from agh_stations.model import Problem  # noqa: E402
from agh_stations.prepare_v2 import (  # noqa: E402
    assumed_levels,
    building_height,
    classify,
    crosses_footprint_legitimately,
    parse_number,
    scenario_weights,
)
from agh_stations.routing import Router  # noqa: E402

RULES = {
    "min_footprint_m2": 150,
    "other_amenity": ["library"],
    "other_leisure": ["sports_hall"],
    "retail_min_footprint_m2": 400,
    "excluded_name_patterns": ["Szkoła Masażu"],
}
HEIGHTS = {"assumed_level_height_m": 3, "assumed_building_height_m": 9}
DATA = Path(__file__).resolve().parents[1] / "data/processed/agh-v2"


@pytest.mark.parametrize(
    ("row", "footprint", "expected"),
    [
        ({"building": "dormitory"}, 300, "dorm"),
        ({"building": "yes", "amenity": "dormitory"}, 300, "dorm"),
        ({"building": "university"}, 300, "teaching"),
        ({"building": "yes", "amenity": "library"}, 300, "other"),
        ({"building": "yes", "leisure": "sports_hall"}, 300, "other"),
        ({"building": "retail"}, 500, "other"),
        ({"building": "retail"}, 300, None),
        ({"building": "university"}, 100, None),
        ({"building": "apartments"}, 900, None),
        ({"building": "school"}, 900, None),
        ({"building": "college", "name": "Policealna Szkoła Masażu nr 2"}, 900, None),
    ],
)
def test_building_function_decides_the_demand_category(row, footprint, expected):
    assert classify(row, footprint, RULES) == expected


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"leisure": "sports_hall"}, (1, "function_default")),
        ({"amenity": "library"}, (3.0, "category_median")),
    ],
)
def test_levels_missing_in_osm_depend_on_the_building_function(row, expected):
    rules = {"default_levels_by_leisure": {"sports_hall": 1}}
    assert assumed_levels(row, 3.0, rules) == expected


def test_a_category_share_follows_how_much_of_it_exists():
    intensity = {"dorm": {"day": 10}, "other": {"day": 20}}
    few = [{"category": "dorm", "floor_area_m2": 9000}, {"category": "other", "floor_area_m2": 100}]
    many = [*few, {"category": "other", "floor_area_m2": 100}]
    assert scenario_weights(few, intensity, ["day"])["day"] == [90.0, 2.0]
    # A new building adds demand of its own and takes nothing away from the existing ones.
    assert scenario_weights(many, intensity, ["day"])["day"] == [90.0, 2.0, 2.0]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"height": "24.9"}, (24.9, "height")),
        ({"height": "12 m", "building:levels": "9"}, (12.0, "height")),
        ({"building:levels": "5"}, (15.0, "levels")),
        ({"building:levels": float("nan")}, (9, "assumed")),
        ({}, (9, "assumed")),
    ],
)
def test_height_records_where_it_came_from(row, expected):
    assert building_height(row, HEIGHTS) == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"tunnel": "building_passage"}, True),
        ({"tunnel": "yes", "layer": "-1"}, True),
        ({"covered": "yes"}, True),
        ({"bridge": "yes"}, True),
        ({"tunnel": "no"}, False),
        ({"highway": "steps"}, False),
    ],
)
def test_only_mapped_passages_may_cross_a_building(tags, expected):
    assert crosses_footprint_legitimately(tags) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("3,5", 3.5), ("7", 7.0), ("brak", None), (None, None), (float("nan"), None)],
)
def test_number_parsing_tolerates_osm_free_text(value, expected):
    assert parse_number(value) == expected


@pytest.mark.skipif(not (DATA / "manifest.json").exists(), reason="dataset v2 is not built")
def test_v2_snapshot_is_consistent_with_its_graph():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected
    raw = json.loads((DATA / "problem.json").read_text(encoding="utf-8"))
    problem = Problem.load(DATA / "problem.json")
    assert np.isfinite(problem.distances).all()
    assert all(c["status"] == "requires_review" for c in raw["candidates"])
    router = Router(DATA / "map.geojson", raw)
    rows = range(0, len(raw["demand"]), max(1, len(raw["demand"]) // 12))
    for i in rows:
        for j in range(0, len(raw["candidates"]), max(1, len(raw["candidates"]) // 12)):
            _, length = router.route(i, raw["candidates"][j]["id"])
            assert length == pytest.approx(problem.distances[i, j], abs=0.002)
