"""The local-extract reader must apply the same rules as an Overpass walking network."""

import pytest

pytest.importorskip("osmium")
pytest.importorskip("osmnx")
from shapely.geometry import box  # noqa: E402

from agh_stations.osm_extract import is_walkable, read_extract  # noqa: E402

XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version='0.6' generator='test'>
<node id='1' version='1' lat='50.0650' lon='19.9050'/>
<node id='2' version='1' lat='50.0655' lon='19.9050'/>
<node id='3' version='1' lat='50.0660' lon='19.9050'><tag k='barrier' v='gate'/></node>
<node id='4' version='1' lat='50.0660' lon='19.9060'/>
<node id='5' version='1' lat='50.0680' lon='19.9500'/>
<node id='10' version='1' lat='50.0650' lon='19.9060'><tag k='entrance' v='main'/></node>
<node id='11' version='1' lat='50.0650' lon='19.9064'/>
<node id='12' version='1' lat='50.0654' lon='19.9064'/>
<node id='13' version='1' lat='50.0654' lon='19.9060'/>
<node id='20' version='1' lat='50.0640' lon='19.9040'>
<tag k='amenity' v='bicycle_parking'/></node>
<way id='100' version='1'><nd ref='1'/><nd ref='2'/><nd ref='3'/>
<tag k='highway' v='footway'/></way>
<way id='101' version='1'><nd ref='3'/><nd ref='4'/><tag k='highway' v='motorway'/></way>
<way id='102' version='1'><nd ref='2'/><nd ref='5'/><tag k='highway' v='path'/></way>
<way id='200' version='1'><nd ref='10'/><nd ref='11'/><nd ref='12'/><nd ref='13'/><nd ref='10'/>
<tag k='building' v='dormitory'/><tag k='name' v='Dom Studencki Żaczek'/>
<tag k='building:levels' v='5'/></way>
</osm>
"""
BOUNDARY = box(19.902, 50.063, 19.923, 50.073)


@pytest.fixture
def extract(tmp_path):
    path = tmp_path / "area.osm"
    path.write_text(XML, encoding="utf-8")
    return read_extract(path, BOUNDARY, BOUNDARY)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"highway": "footway"}, True),
        ({"highway": "residential"}, True),
        ({"highway": "motorway_link"}, False),
        ({"highway": "cycleway"}, False),
        ({"highway": "footway", "foot": "no"}, False),
        ({"highway": "service", "service": "private"}, False),
        ({"highway": "primary", "sidewalk": "separate"}, False),
        ({"building": "yes"}, False),
    ],
)
def test_walkability_follows_the_osmnx_filter(tags, expected):
    assert is_walkable(tags) is expected


def test_graph_is_bidirectional_and_trimmed_to_the_area(extract):
    graph = extract.graph
    assert set(graph.nodes) == {1, 2, 3}
    assert graph.number_of_edges() == 4
    assert graph.has_edge(1, 2) and graph.has_edge(2, 1)
    assert graph[1][2][0]["length"] == pytest.approx(55.6, abs=0.3)
    assert graph[1][2][0]["highway"] == "footway"
    assert graph.nodes[3]["barrier"] == "gate"
    assert graph.nodes[1]["x"] == pytest.approx(19.905)


def test_features_keep_identifiers_tags_and_polish_names(extract):
    building = extract.buildings.loc[("way", 200)]
    assert building["name"] == "Dom Studencki Żaczek"
    assert building["building:levels"] == "5"
    assert building.geometry.geom_type == "Polygon"
    assert list(extract.entrances["entrance"]) == ["main"]
    assert ("node", 20) in extract.bike.index
    assert extract.obstacles.empty


def test_extract_outside_the_area_is_refused(tmp_path):
    path = tmp_path / "area.osm"
    path.write_text(XML, encoding="utf-8")
    elsewhere = box(21.0, 52.2, 21.01, 52.21)
    with pytest.raises(ValueError, match="does not cover"):
        read_extract(path, elsewhere, elsewhere)
