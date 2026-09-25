from decimal import Decimal
import heapq
from .models import SectionType
from .names import node_matches, name_keys


class UnknownIC(ValueError):
    pass


class AmbiguousIC(ValueError):
    pass


class RouteNotFound(ValueError):
    pass


class RouteFinder:
    def __init__(self, graph, nodes, access_points=None):
        self.graph, self.nodes = graph, nodes
        self.access_points = access_points or {}

    def resolve(self, name):
        matches = [n for n in self.nodes.values() if n.node_type in {"IC", "JCT"} and node_matches(n, name)]
        if not matches:
            raise UnknownIC(f"Unknown IC/JCT: {name}")
        if len({n.node_type for n in matches}) > 1:
            raise AmbiguousIC(f"Specify IC or JCT explicitly: {name}")
        # Same name at distant locations must be explicitly disambiguated.
        from geographiclib.geodesic import Geodesic
        for node in matches[1:]:
            if Geodesic.WGS84.Inverse(matches[0].latitude, matches[0].longitude, node.latitude, node.longitude)["s12"] > 10000:
                raise AmbiguousIC(f"Distant namesakes: {name}; use a reviewed alias")
        return {n.id for n in matches}

    def find_route(self, start_ic: str, end_ic: str, *, mode="access", allow_special_system=False):
        starts, ends = self.resolve(start_ic), self.resolve(end_ic)
        if starts == ends:
            return []
        if mode == "access":
            starts = {p for n in starts for p in self.access_points.get(n, {}).get("entry", [])}
            ends = {p for n in ends for p in self.access_points.get(n, {}).get("exit", [])}
            if not starts or not ends:
                raise RouteNotFound("Entry/exit ramp could not be resolved; no mainline fallback")
        elif mode != "junction":
            raise ValueError("mode must be access or junction")
        # State includes incoming OSM way so no_/only_ turns remain enforceable.
        restrictions = {}
        for rule in self.graph.graph.get("turn_restrictions", []):
            restrictions.setdefault((str(rule["via_node"]), rule["from_way"]), []).append(rule)
        roots = {(n, -1, -1) for n in starts}
        queue = [(Decimal(0), state) for state in sorted(roots)]
        heapq.heapify(queue)
        best = {state: Decimal(0) for state in roots}
        prev = {}
        while queue:
            cost, state = heapq.heappop(queue)
            node, incoming, previous_node = state
            if cost != best[state]:
                continue
            if node in ends:
                route = []
                while state not in roots:
                    before, segment = prev[state]
                    route.append(segment)
                    state = before
                return list(reversed(route))
            if self.nodes[node].node_type == "ACCESS_BOUNDARY" and node not in starts:
                continue
            for _, target, _, attrs in self.graph.out_edges(node, keys=True, data=True):
                seg = attrs["segment"]
                if seg.section_type == SectionType.SPECIAL_SYSTEM and not allow_special_system:
                    continue
                outgoing = seg.osm_way_ids[0]
                rules = restrictions.get((node, incoming), [])
                forbidden = False
                for rule in rules:
                    matches_turn = outgoing == rule["to_way"]
                    if rule["from_way"] == rule["to_way"] and rule["restriction"] in {"no_u_turn", "only_u_turn"}:
                        matches_turn = matches_turn and previous_node == seg.osm_node_ids[1]
                    if (rule["restriction"].startswith("no_") and matches_turn) or (rule["restriction"].startswith("only_") and not matches_turn):
                        forbidden = True
                if forbidden:
                    continue
                target_state = (target, seg.osm_way_ids[-1], seg.osm_node_ids[-2])
                candidate = cost + seg.distance_km
                if candidate < best.get(target_state, Decimal("Infinity")):
                    best[target_state] = candidate
                    prev[target_state] = (state, seg)
                    heapq.heappush(queue, (candidate, target_state))

        raise RouteNotFound(f"No directed motorway route: {start_ic} -> {end_ic}")


def aggregate_distance_by_section(route):
    result = {t: Decimal(0) for t in SectionType}
    for segment in route:
        result[segment.section_type] += segment.distance_km
    return result


def find_route(start_ic: str, end_ic: str):
    from .storage import load_graph
    graph, nodes, access = load_graph("data/processed")
    return RouteFinder(graph, nodes, access).find_route(start_ic, end_ic)
