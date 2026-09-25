"""Resolve IC ramp ports from OSM links and named toll gates, never proximity alone."""
import networkx as nx
from .names import name_keys, node_matches


def build_access_points(graph, nodes):
    links = nx.Graph()
    mainline = set()
    ic_nodes = [n for n in nodes.values() if n.node_type == "IC"]
    for a, b, d in graph.edges(data=True):
        if d["segment"].highway == "motorway_link":
            links.add_edge(a, b)
        else:
            mainline.update((a, b))
    result = {}
    diagnostics = []
    for component in nx.connected_components(links):
        named = [nodes[n] for n in component if nodes[n].node_type == "IC"]
        gates = [nodes[n] for n in component if nodes[n].node_type == "TOLL_GATE"]
        for gate in gates:
            named.extend(n for n in ic_nodes if node_matches(n, gate.name))
        if not named:
            continue
        # The canonical IC names originate from OSM tags, including wikipedia titles.
        common = set.intersection(*(name_keys(n.name) for n in named))
        if not common:
            diagnostics.append({"reason": "ambiguous_ramp_component", "nodes": sorted(component), "names": sorted({n.name for n in named})})
            continue
        entries, exits = [], []
        for n in sorted(component - mainline):
            if nodes[n].node_type != "ACCESS_BOUNDARY":
                continue
            if graph.out_degree(n) > 0:
                entries.append(n)
            if graph.in_degree(n) > 0:
                exits.append(n)
        for n in named:
            item = result.setdefault(n.id, {"entry": [], "exit": [], "method": "OSM_link_component_and_named_toll_gate"})
            item["entry"] = sorted(set(item["entry"]) | set(entries))
            item["exit"] = sorted(set(item["exit"]) | set(exits))
    return result, diagnostics
