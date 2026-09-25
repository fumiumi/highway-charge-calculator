"""Integration checks against the committed real OSM-derived graph, no network."""
import json
from decimal import Decimal
from pathlib import Path
import pytest
from src.storage import load_graph
from src.route_finder import RouteFinder, aggregate_distance_by_section
from src.models import SectionType
from src.validation import validate_graph
from scripts.run_samples import CASES

DATA=Path(__file__).resolve().parents[1] / "data" / "processed"


@pytest.fixture(scope="module")
def dataset():
    return load_graph(DATA)


@pytest.mark.parametrize("start,end", CASES)
def test_real_route_search(dataset,start,end):
    graph,nodes,access=dataset
    result=RouteFinder(graph,nodes,access).find_route(start,end)
    assert result
    assert all(a.end_node==b.start_node for a,b in zip(result,result[1:]))
    assert all(s.highway in {"motorway","motorway_link"} for s in result)
    totals=aggregate_distance_by_section(result)
    assert sum(totals.values()) == sum((s.distance_km for s in result),Decimal(0))
    assert totals[SectionType.SPECIAL_SYSTEM]==0
    assert totals[SectionType.METROPOLITAN]>0


def test_real_boundary_crossing(dataset):
    graph,nodes,access=dataset
    route=RouteFinder(graph,nodes,access).find_route("調布IC","上野原IC")
    totals=aggregate_distance_by_section(route)
    assert totals[SectionType.NORMAL]>0
    assert totals[SectionType.METROPOLITAN]>0
    assert totals[SectionType.UNKNOWN]>0  # ramps + unresolved boundary must not disappear


def test_real_multi_road_route(dataset):
    graph,nodes,access=dataset
    route=RouteFinder(graph,nodes,access).find_route("調布IC","相模原IC")
    assert "中央自動車道" in {s.road_name for s in route}
    assert any("圏央" in s.road_name or "首都圏中央" in s.road_name for s in route)
    assert any(nodes[s.end_node].node_type=="JCT" for s in route)


def test_real_graph_quality_and_coverage(dataset):
    graph,nodes,_=dataset
    segments=[d["segment"] for *_,d in graph.edges(data=True)]
    report=validate_graph(graph,nodes,segments)
    assert not report["errors"]
    road_names="\n".join(s.road_name for s in segments)
    for road in ["東名", "新東名", "中央自動車道", "関越", "東北", "常磐", "館山", "東京外環", "首都圏中央"]:
        assert road in road_names
    for segment in segments:
        if segment.section_type != SectionType.UNKNOWN:
            assert segment.toll_rule_source.startswith("https://")
            assert segment.toll_rule_id
        assert segment.osm_way_ids and len(segment.osm_node_ids)>=2


def test_real_toll_conflict_remains_unknown(dataset):
    graph,_,_=dataset
    report=json.loads((DATA/"quality_report.json").read_text())
    conflicts={r["segment"] for r in report["toll_rules"] if r["status"]=="conflict_UNKNOWN"}
    assert conflicts  # Hachioji multiple exits do not define a single billing point.
    assert all(d["segment"].section_type==SectionType.UNKNOWN for *_,d in graph.edges(data=True) if d["segment"].id in conflicts)
