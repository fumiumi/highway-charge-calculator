"""Official interval master, separate from OSM extraction. Fail closed on ambiguity."""
import json
from dataclasses import asdict
import networkx as nx
from .models import TollSectionRule, SectionType
from .names import node_matches


def load_rules(path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    rules = []
    for row in rows:
        row["section_type"] = SectionType[row["section_type"]]
        if not row["source"].startswith("https://"):
            raise ValueError("A source URL is mandatory")
        rules.append(TollSectionRule(**row))
    return rules


def apply_rules(graph, nodes, rules):
    report = []
    proposals = {}
    for rule in rules:
        edges = [(a, b, k) for a, b, k, d in graph.edges(keys=True, data=True)
                 if d["segment"].road_name == rule.road_name and d["segment"].highway == "motorway"]
        corridor = graph.edge_subgraph(edges)
        starts = sorted(n for n in corridor if node_matches(nodes[n], rule.start))
        ends = sorted(n for n in corridor if node_matches(nodes[n], rule.end))
        selected = set()
        ambiguous = False
        for a, b in [(a, b) for a in starts for b in ends] + [(b, a) for a in starts for b in ends]:
            # Mainline interval must have exactly one simple directed edge path.
            paths = nx.all_simple_edge_paths(corridor, a, b)
            first = next(paths, None)
            if first is not None:
                if next(paths, None) is not None:
                    ambiguous = True
                selected.update(first)
        status = "applied" if selected and not ambiguous else "unresolved"
        if status == "applied":
            for edge in selected:
                proposals.setdefault(edge, []).append(rule)
        report.append({"rule_id": rule.id, "status": status, "edge_count": len(selected) if status == "applied" else 0,
                       "start_osm_nodes": starts, "end_osm_nodes": ends,
                       "boundary_method": "OSM motorway_junction; not official chargeable chainage"})
    for edge, candidates in proposals.items():
        seg = graph.edges[edge]["segment"]
        if len({r.section_type for r in candidates}) != 1:
            report.append({"segment": seg.id, "status": "conflict_UNKNOWN", "rules": [r.id for r in candidates]})
            continue
        rule = candidates[0]
        seg.section_type = rule.section_type
        seg.toll_rule_source, seg.toll_rule_id = rule.source, rule.id
    return report


def mark_special_system(segments):
    # Explicit operator identity in OSM name, not a guessed regional tariff.
    for seg in segments:
        if "首都高速" in seg.road_name:
            seg.section_type = SectionType.SPECIAL_SYSTEM
            seg.toll_rule_source = "https://www.shutoko.jp/tolls/"
            seg.toll_rule_id = "shutoko-separate-system"
