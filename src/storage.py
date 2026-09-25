import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import networkx as nx
from .models import RoadNode, RoadSegment, SectionType


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=lambda x: x.name if isinstance(x, SectionType) else str(x)) + "\n", encoding="utf-8")


def save_graph(directory, nodes, segments, access, rules, restrictions=()):
    directory = Path(directory)
    write_json(directory / "nodes.json", [asdict(n) for n in nodes.values()])
    write_json(directory / "road_segments.json", [asdict(s) for s in segments])
    write_json(directory / "access_points.json", dict(sorted(access.items())))
    write_json(directory / "turn_restrictions.json", list(restrictions))
    write_json(directory / "toll_section_rules.json", [asdict(r) for r in rules])


def load_graph(directory):
    directory = Path(directory)
    nodes = {r["id"]: RoadNode(**r) for r in json.loads((directory / "nodes.json").read_text())}
    graph = nx.MultiDiGraph()
    restriction_file = directory / "turn_restrictions.json"
    graph.graph["turn_restrictions"] = json.loads(restriction_file.read_text()) if restriction_file.exists() else []
    for n in nodes.values():
        graph.add_node(n.id, node=n)
    for row in json.loads((directory / "road_segments.json").read_text()):
        row["distance_km"] = Decimal(row["distance_km"])
        row["section_type"] = SectionType[row["section_type"]]
        s = RoadSegment(**row)
        if s.start_node not in nodes or s.end_node not in nodes or not s.distance_km.is_finite() or s.distance_km <= 0:
            raise ValueError(f"Invalid segment {s.id}")
        graph.add_edge(s.start_node, s.end_node, key=s.id, weight=s.distance_km, segment=s)
    access = json.loads((directory / "access_points.json").read_text())
    return graph, nodes, access
