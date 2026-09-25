from collections import Counter
from decimal import Decimal


def validate_graph(graph, nodes, segments, data=None):
    errors, warnings = [], []
    for s in segments:
        if s.start_node not in nodes or s.end_node not in nodes:
            errors.append({"segment": s.id, "reason": "missing_endpoint"})
        if not s.distance_km.is_finite() or s.distance_km <= 0:
            errors.append({"segment": s.id, "reason": "non_positive_distance"})
        if s.distance_km > Decimal(50):
            warnings.append({"segment": s.id, "reason": "over_50km_review"})
        if s.highway not in {"motorway", "motorway_link"}:
            errors.append({"segment": s.id, "reason": "non_motorway"})
        if data:
            pairs = {(a,b) for wid in s.osm_way_ids for a,b in zip(data.ways[wid]["nodes"], data.ways[wid]["nodes"][1:])}
            for a,b in zip(s.osm_node_ids, s.osm_node_ids[1:]):
                if (a,b) not in pairs and (b,a) not in pairs:
                    errors.append({"segment": s.id, "reason": "invented_geometry_connection"})
        if s.road_name == "UNKNOWN":
            warnings.append({"segment": s.id, "reason": "unknown_road_name"})
    if errors:
        raise ValueError(f"Graph validation failed: {errors[:10]}")
    return {"errors": errors, "warnings": warnings, "nodes": len(nodes), "segments": len(segments),
            "named_ic_jct": len({n.name for n in nodes.values() if n.node_type in {"IC", "JCT"}}),
            "sections": dict(Counter(s.section_type.name for s in segments)),
            "roads": dict(Counter(s.road_name for s in segments))}
