"""Topology-preserving directed contraction. Lane ports are never merged by name."""
from decimal import Decimal
import re
from geographiclib.geodesic import Geodesic
import networkx as nx
from .models import RoadNode, RoadSegment


def road_name(tags):
    return tags.get("name:ja") or tags.get("name") or "UNKNOWN"


def build_graph(data):
    raw = nx.MultiDiGraph()
    for wid, way in sorted(data.ways.items()):
        tags = way["tags"]
        ids = way["nodes"]
        direction = tags.get("oneway", "yes" if tags["highway"] == "motorway" else "UNKNOWN")
        if direction not in {"yes", "1", "true", "no", "0", "false", "-1"}:
            data.warnings.append({"way": wid, "reason": "unknown_oneway"})
            continue
        for i, (a, b) in enumerate(zip(ids, ids[1:])):
            if a == b:
                continue
            na, nb = data.nodes[a], data.nodes[b]
            distance = Geodesic.WGS84.Inverse(na["latitude"], na["longitude"], nb["latitude"], nb["longitude"])["s12"]
            if distance <= 0:
                raise ValueError(f"Zero-length geometry in way {wid}")
            attrs = dict(road_name=way.get("route_name") or road_name(tags), highway=tags["highway"], way=wid,
                         osm_name=road_name(tags), relations=way.get("route_relation_ids", []),
                         distance=Decimal(str(distance)) / Decimal(1000))
            if direction != "-1":
                raw.add_edge(a, b, key=f"{wid}:{i}:f", **attrs)
            if direction in {"-1", "no", "0", "false"}:
                raw.add_edge(b, a, key=f"{wid}:{i}:r", **attrs)
    if raw.number_of_edges() == 0:
        raise ValueError("No usable directed motorway edges")
    named = {n for n in raw if data.nodes[n]["tags"].get("highway") == "motorway_junction"}
    gates = {n for n in raw if data.nodes[n]["tags"].get("barrier") == "toll_booth"}
    anchors = set(named) | gates | (data.external_nodes & set(raw)) | ({r["via_node"] for r in data.restrictions} & set(raw))
    for n in raw:
        if raw.in_degree(n) != 1 or raw.out_degree(n) != 1:
            anchors.add(n)
        else:
            a = next(iter(raw.in_edges(n, data=True)))[2]
            b = next(iter(raw.out_edges(n, data=True)))[2]
            if (a["road_name"], a["highway"]) != (b["road_name"], b["highway"]):
                anchors.add(n)
    # Anchor otherwise unlabelled directed cycles, preserving every edge.
    for component in nx.weakly_connected_components(raw):
        if not anchors.intersection(component):
            anchors.add(min(component))
    graph = nx.MultiDiGraph()
    graph.graph["turn_restrictions"] = data.restrictions
    nodes = {}
    for n in sorted(anchors):
        source = data.nodes[n]
        tags = source["tags"]
        name = tags.get("name:ja") or tags.get("name") or f"osm:{n}"
        raw_name = name
        wikipedia_title = tags.get("wikipedia", "").removeprefix("ja:")
        if n in named and tags.get("wikipedia", "").startswith("ja:") and wikipedia_title.endswith(("インターチェンジ", "ジャンクション")):
            name = wikipedia_title
        aliases = sorted({v for k, v in tags.items() if k.startswith("name:") or k in {"alt_name", "official_name", "short_name"}})
        aliases = sorted({s for v in aliases for s in v.split(";")} | {raw_name})
        typ = "JCT" if "ジャンクション" in name or "jct" in name.casefold() or "junction" in name.casefold() else "IC"
        if n not in named or name.startswith("osm:") or "サービスエリア" in name or "パーキングエリア" in name or re.search(r"(?:SA|PA)(?:[ 　]*[（(].*?[）)])?$", name, re.IGNORECASE):
            typ = "TOPOLOGY"
        if n in gates and typ == "TOPOLOGY":
            typ = "TOLL_GATE"
        if n in data.external_nodes and typ == "TOPOLOGY":
            typ = "ACCESS_BOUNDARY"
        node = RoadNode(str(n), name, typ, source["latitude"], source["longitude"], aliases)
        nodes[str(n)] = node
        graph.add_node(str(n), node=node)
    segments = []
    for start in sorted(anchors):
        for _, end, key, attr in sorted(raw.out_edges(start, keys=True, data=True), key=lambda e: (e[1], e[2])):
            path = [start, end]
            ways = [attr["way"]]
            osm_names = {attr["osm_name"]}
            relations = set(attr["relations"])
            distance = attr["distance"]
            while end not in anchors:
                _, nxt, _, nxtattr = next(iter(raw.out_edges(end, keys=True, data=True)))
                path.append(nxt)
                if ways[-1] != nxtattr["way"]:
                    ways.append(nxtattr["way"])
                osm_names.add(nxtattr["osm_name"])
                relations.update(nxtattr["relations"])
                distance += nxtattr["distance"]
                end = nxt
            seg = RoadSegment(str(start), str(end), attr["road_name"], distance,
                              id=f"segment:{len(segments)}", osm_way_ids=ways,
                              osm_node_ids=path, highway=attr["highway"],
                              osm_names=sorted(osm_names), osm_route_relation_ids=sorted(relations))
            segments.append(seg)
            graph.add_edge(str(start), str(end), key=seg.id, segment=seg, weight=distance)
    return graph, nodes, segments
