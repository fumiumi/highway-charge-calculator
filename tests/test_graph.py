"""Synthetic coordinates test algorithms only; never shipped as real road data."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import networkx as nx
import pytest
from src.models import RoadNode, RoadSegment, SectionType, TollSectionRule
from src.osm_loader import OSMData, load_osm
from src.graph_builder import build_graph
from src.route_finder import RouteFinder, UnknownIC, RouteNotFound, aggregate_distance_by_section
from src.toll_sections import apply_rules
from src.storage import save_graph, load_graph
from src.validation import validate_graph
from src.access_points import build_access_points


def fixture_data():
    data = OSMData()
    for i, (lat, lon) in enumerate([(35,139), (35.01,139), (35.01,139.01), (35.02,139.01)], 1):
        data.nodes[i] = {"latitude": lat, "longitude": lon, "tags": {}}
    data.nodes[1]["tags"] = {"highway": "motorway_junction", "name": "試験入口インターチェンジ", "name:en": "Test Start IC"}
    data.nodes[4]["tags"] = {"highway": "motorway_junction", "name": "試験出口IC"}
    data.ways = {10: {"nodes": [1,2,3], "tags": {"highway": "motorway", "name": "TEST"}},
                 11: {"nodes": [3,4], "tags": {"highway": "motorway", "name": "TEST"}}}
    return data


def test_route_search():
    graph, nodes, segments = build_graph(fixture_data())
    route = RouteFinder(graph, nodes).find_route("試験入口IC", "試験出口IC", mode="junction")
    assert len(route) == 1
    assert route[0].osm_way_ids == [10,11]
    assert route[0].osm_node_ids == [1,2,3,4]
    assert RouteFinder(graph, nodes).resolve("Test Start IC") == {"1"}


def test_distance_is_positive():
    graph, nodes, segments = build_graph(fixture_data())
    from geographiclib.geodesic import Geodesic
    straight = Geodesic.WGS84.Inverse(35,139,35.02,139.01)["s12"] / 1000
    assert segments[0].distance_km > Decimal(str(straight))
    assert validate_graph(graph, nodes, segments, fixture_data())["errors"] == []


def test_known_metropolitan_section():
    graph, nodes, segments = build_graph(fixture_data())
    # Test official-rule mechanics with an explicitly synthetic rule, not fake real distances.
    rule = TollSectionRule("test", "TEST", "試験入口IC", "試験出口IC", SectionType.METROPOLITAN, "https://example.org/test", "TEST", "2026-09-25")
    assert apply_rules(graph,nodes,[rule])[0]["status"] == "applied"
    assert segments[0].section_type == SectionType.METROPOLITAN
    assert aggregate_distance_by_section(segments)[SectionType.METROPOLITAN] == segments[0].distance_km


def test_unknown_ic():
    graph,nodes,_ = build_graph(fixture_data())
    with pytest.raises(UnknownIC):
        RouteFinder(graph,nodes).find_route("不存在IC", "試験出口IC")


def test_no_reverse_or_access_fallback():
    graph,nodes,_ = build_graph(fixture_data())
    with pytest.raises(RouteNotFound):
        RouteFinder(graph,nodes).find_route("試験出口IC", "試験入口IC", mode="junction")
    with pytest.raises(RouteNotFound):
        RouteFinder(graph,nodes).find_route("試験入口IC", "試験出口IC")


def test_reverse_oneway():
    data = fixture_data()
    for w in data.ways.values():
        w["tags"]["oneway"] = "-1"
    graph,nodes,_ = build_graph(data)
    assert RouteFinder(graph,nodes).find_route("試験出口IC", "試験入口IC", mode="junction")[0].osm_node_ids == [4,3,2,1]


def test_unknown_ramp_direction_is_excluded():
    data = fixture_data()
    data.ways[10]["tags"]["highway"] = "motorway_link"
    _,_,segments = build_graph(data)
    assert all(10 not in s.osm_way_ids for s in segments)


def test_roundtrip_decimal(tmp_path):
    graph,nodes,segments = build_graph(fixture_data())
    save_graph(tmp_path, nodes, segments, {}, [])
    loaded,nodes2,_ = load_graph(tmp_path)
    assert loaded.edges["1","4","segment:0"]["segment"] == segments[0]
    assert nodes2 == nodes


def test_parallel_edge_identity():
    graph,nodes,segs = build_graph(fixture_data())
    cheap = replace(segs[0], id="cheap", distance_km=Decimal("0.2"), section_type=SectionType.SPECIAL)
    graph.add_edge("1","4",key="cheap",segment=cheap,weight=cheap.distance_km)
    result = RouteFinder(graph,nodes).find_route("試験入口IC","試験出口IC",mode="junction")
    assert result == [cheap]


def test_conflicting_rules_remain_unknown():
    graph,nodes,segs = build_graph(fixture_data())
    rule = TollSectionRule("a", "TEST", "試験入口IC", "試験出口IC", SectionType.NORMAL, "https://example.org", "TEST", "2026-09-25")
    report = apply_rules(graph,nodes,[rule,replace(rule,id="b",section_type=SectionType.SPECIAL)])
    assert segs[0].section_type == SectionType.UNKNOWN
    assert report[-1]["status"] == "conflict_UNKNOWN"


def test_unresolved_boundary_not_extended():
    graph,nodes,segs = build_graph(fixture_data())
    rule = TollSectionRule("a", "TEST", "不明IC", "試験出口IC", SectionType.NORMAL, "https://example.org", "TEST", "2026-09-25")
    assert apply_rules(graph,nodes,[rule])[0]["status"] == "unresolved"
    assert segs[0].section_type == SectionType.UNKNOWN


def test_xml_loader_filters_and_fails_closed(tmp_path):
    p = tmp_path / "test.osm"
    p.write_text('''<osm version="0.6">
    <node id="1" lat="35" lon="139"/><node id="2" lat="35.01" lon="139"/>
    <node id="3" lat="35.02" lon="139"/>
    <way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="motorway"/></way>
    <way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/></way>
    <way id="3"><nd ref="1"/><nd ref="3"/><tag k="highway" v="motorway"/><tag k="access" v="private"/></way>
    </osm>''')
    data = load_osm([p])
    assert list(data.ways) == [1]
    assert data.external_nodes == {2}
    assert data.warnings[0]["reason"] == "restricted_access"
    p.write_text('<osm version="0.6"><way id="1"><nd ref="999"/><nd ref="998"/><tag k="highway" v="motorway"/></way></osm>')
    with pytest.raises(ValueError, match="missing"):
        load_osm([p])


def test_special_system_default_exclusion():
    graph,nodes,segs = build_graph(fixture_data())
    segs[0].section_type = SectionType.SPECIAL_SYSTEM
    with pytest.raises(RouteNotFound):
        RouteFinder(graph,nodes).find_route("試験入口IC","試験出口IC",mode="junction")


def test_no_artificial_name_merge():
    data = fixture_data()
    data.nodes[9] = {**data.nodes[1], "longitude": 139.001}
    data.nodes[10] = {**data.nodes[4], "longitude": 139.011}
    data.ways[19] = {"nodes": [10,9], "tags": {"highway":"motorway", "name":"TEST"}}
    graph,nodes,_ = build_graph(data)
    assert not nx.has_path(graph,"1","9")
    assert not nx.has_path(graph,"10","4")


def test_access_ramps_and_general_road_boundary():
    data = fixture_data()
    # One connected ramp system with an observed general-road boundary at 5.
    data.nodes[5] = {"latitude": 35.001, "longitude": 138.999, "tags": {}}
    data.nodes[6] = {"latitude": 35.019, "longitude": 139.011, "tags": {}}
    data.external_nodes = {5,6}
    data.ways[20] = {"nodes": [5,1], "tags": {"highway":"motorway_link", "oneway":"no"}}
    data.ways[21] = {"nodes": [4,6], "tags": {"highway":"motorway_link", "oneway":"no"}}
    graph,nodes,segs = build_graph(data)
    access,_ = build_access_points(graph,nodes)
    route = RouteFinder(graph,nodes,access).find_route("試験入口IC", "試験出口IC")
    assert route[0].start_node == "5"
    assert route[-1].end_node == "6"
    assert sum((s.distance_km for s in route), Decimal(0)) == sum(aggregate_distance_by_section(route).values())


def test_unobserved_dead_end_is_not_an_entrance():
    data = fixture_data()
    data.nodes[5] = {"latitude":35.001,"longitude":139.001,"tags":{}}
    data.ways[20] = {"nodes":[5,1],"tags":{"highway":"motorway_link","oneway":"yes"}}
    graph,nodes,_ = build_graph(data)
    access,_ = build_access_points(graph,nodes)
    assert access["1"]["entry"] == []


def test_turn_restriction_is_loaded_and_enforced(tmp_path):
    p=tmp_path / "restriction.osm"
    p.write_text('''<osm version="0.6">
    <node id="1" lat="35" lon="139"/><node id="2" lat="35.01" lon="139"/><node id="3" lat="35.02" lon="139"/>
    <way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="motorway"/></way>
    <way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="motorway"/></way>
    <relation id="9"><member type="way" ref="1" role="from"/><member type="node" ref="2" role="via"/><member type="way" ref="2" role="to"/><tag k="type" v="restriction"/><tag k="restriction" v="no_straight_on"/></relation>
    </osm>''')
    data=load_osm([p])
    assert list(data.ways) == [1,2]
    assert data.restrictions[0]["restriction"] == "no_straight_on"
    data.nodes[1]["tags"]={"highway":"motorway_junction","name":"A IC"}
    data.nodes[3]["tags"]={"highway":"motorway_junction","name":"B IC"}
    graph,nodes,_=build_graph(data)
    with pytest.raises(RouteNotFound):
        RouteFinder(graph,nodes).find_route("A IC","B IC",mode="junction")
    graph.graph["turn_restrictions"]=[]
    assert RouteFinder(graph,nodes).find_route("A IC","B IC",mode="junction")


def test_same_ic_returns_empty_route():
    graph,nodes,_=build_graph(fixture_data())
    assert RouteFinder(graph,nodes).find_route("試験入口IC","試験入口インターチェンジ") == []


def test_unknown_section_is_preserved():
    _,_,segments=build_graph(fixture_data())
    result=aggregate_distance_by_section(segments)
    assert result[SectionType.UNKNOWN] > 0
    assert result[SectionType.NORMAL] == 0


def test_general_road_boundary_cannot_be_used_mid_route():
    graph,nodes,segs = build_graph(fixture_data())
    original = segs[0]
    graph.remove_edge("1","4",original.id)
    nodes["99"] = RoadNode("99","一般道接続","ACCESS_BOUNDARY",35,139)
    graph.add_node("99",node=nodes["99"])
    for a,b,ident in [("1","99","a"),("99","4","b")]:
        segment=replace(original,start_node=a,end_node=b,id=ident)
        graph.add_edge(a,b,key=ident,segment=segment,weight=segment.distance_km)
    with pytest.raises(RouteNotFound):
        RouteFinder(graph,nodes).find_route("試験入口IC","試験出口IC",mode="junction")


def test_cyclic_geometry_contraction_preserves_all_edges():
    data=fixture_data()
    for n in data.nodes.values():
        n["tags"]={}
    data.ways={10:{"nodes":[1,2,3,4,1],"tags":{"highway":"motorway","name":"TEST"}}}
    graph,nodes,segs=build_graph(data)
    assert len(segs)==1
    assert segs[0].start_node==segs[0].end_node
    assert segs[0].osm_node_ids==[1,2,3,4,1]


def test_ambiguous_toll_corridor_stays_unknown():
    graph,nodes,segs=build_graph(fixture_data())
    extra=replace(segs[0],id="alternate")
    graph.add_edge("1","4",key=extra.id,segment=extra,weight=extra.distance_km)
    rule=TollSectionRule("a","TEST","試験入口IC","試験出口IC",SectionType.NORMAL,"https://example.org","TEST","2026-09-25")
    assert apply_rules(graph,nodes,[rule])[0]["status"]=="unresolved"
    assert segs[0].section_type==extra.section_type==SectionType.UNKNOWN


def test_ic_and_jct_with_same_stem_are_not_equal():
    from src.names import node_matches
    from src.route_finder import AmbiguousIC
    ic=RoadNode("ic","八王子インターチェンジ","IC",35,139)
    jct=RoadNode("jct","八王子ジャンクション","JCT",35,139)
    assert node_matches(ic,"八王子IC")
    assert not node_matches(jct,"八王子IC")
    assert not node_matches(ic,"八王子JCT")
    assert node_matches(jct,"八王子JCT")
    finder=RouteFinder(nx.MultiDiGraph(), {"ic":ic,"jct":jct})
    with pytest.raises(AmbiguousIC):
        finder.resolve("八王子")


def test_same_way_no_u_turn_allows_straight_travel():
    data=fixture_data()
    data.ways={10:{"nodes":[1,2,3,4],"tags":{"highway":"motorway","name":"TEST","oneway":"no"}}}
    data.restrictions=[{"id":1,"from_way":10,"to_way":10,"via_node":2,"restriction":"no_u_turn"}]
    graph,nodes,_=build_graph(data)
    assert RouteFinder(graph,nodes).find_route("試験入口IC","試験出口IC",mode="junction")


def test_osm_route_relation_preserves_bridge_name(tmp_path):
    p=tmp_path / "route.osm"
    p.write_text('''<osm version="0.6">
    <node id="1" lat="35" lon="139"/><node id="2" lat="35.01" lon="139"/>
    <way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="motorway"/><tag k="name" v="試験橋"/></way>
    <relation id="2"><member type="way" ref="1" role=""/><tag k="type" v="route"/><tag k="route" v="road"/><tag k="name" v="試験自動車道上り"/></relation>
    </osm>''')
    data=load_osm([p])
    _,_,segs=build_graph(data)
    assert segs[0].road_name=="試験自動車道"
    assert segs[0].osm_names==["試験橋"]
    assert segs[0].osm_route_relation_ids==[2]
