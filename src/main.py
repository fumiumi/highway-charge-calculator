import argparse
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import osmium
import sys
from .osm_loader import load_osm
from .graph_builder import build_graph
from .access_points import build_access_points
from .toll_sections import load_rules, apply_rules, mark_special_system
from .route_finder import RouteFinder, aggregate_distance_by_section
from .storage import save_graph, load_graph, write_json
from .validation import validate_graph


def generate(inputs, output, master, bbox=None):
    data = load_osm(inputs)
    if bbox:
        west, south, east, north = bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("Invalid bounding box")
        retained = {}
        for wid, way in data.ways.items():
            if all(west <= data.nodes[n]["longitude"] <= east and south <= data.nodes[n]["latitude"] <= north for n in way["nodes"]):
                retained[wid] = way
        data.warnings.append({"reason": "bbox_excluded_ways", "count": len(data.ways) - len(retained)})
        data.ways = retained
    print(f"Building {len(data.ways)} ways", file=sys.stderr, flush=True)
    graph, nodes, segments = build_graph(data)
    rules = load_rules(master)
    print("Applying sourced toll intervals", file=sys.stderr, flush=True)
    toll_report = apply_rules(graph, nodes, rules)
    mark_special_system(segments)
    access, access_warnings = build_access_points(graph, nodes)
    print("Validating graph", file=sys.stderr, flush=True)
    report = validate_graph(graph, nodes, segments, data)
    report["osm_warnings"] = data.warnings
    report["access_warnings"] = access_warnings
    report["toll_rules"] = toll_report
    report["access_resolved_nodes"] = len(access)
    manifests = []
    for path in inputs:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        with osmium.io.Reader(str(path)) as reader:
            timestamp = reader.header().get("osmosis_replication_timestamp")
        metadata_path = path.with_suffix(".manifest.json")
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        manifests.append({**metadata, "file": path.name, "sha256": h.hexdigest(), "osm_timestamp": timestamp})
    save_graph(output, nodes, segments, access, rules, graph.graph["turn_restrictions"])
    write_json(output / "quality_report.json", report)
    write_json(output / "manifest.json", {"schema_version": 2, "inputs": manifests, "bbox": bbox,
               "distance_method": "WGS84 ellipsoidal sum over every OSM node pair; not toll mileage",
               "attribution": "© OpenStreetMap contributors", "license": "ODbL-1.0"})
    print(json.dumps({k: report[k] for k in ("nodes", "segments", "named_ic_jct", "sections", "access_resolved_nodes")}, ensure_ascii=False))


def route_result(directory, start, end, mode="access"):
    graph, nodes, access = load_graph(directory)
    route = RouteFinder(graph, nodes, access).find_route(start, end, mode=mode)
    totals = aggregate_distance_by_section(route)
    named_path = []
    for node_id in ([route[0].start_node] if route else []) + [s.end_node for s in route]:
        node = nodes[node_id]
        if node.node_type in {"IC", "JCT"} and (not named_path or named_path[-1] != node.name):
            named_path.append(node.name)
    return {"入口IC": start, "出口IC": end, "endpoint_mode": mode, "通過IC_JCT": named_path,
            "採用経路": [{"from": nodes[s.start_node].name, "to": nodes[s.end_node].name,
                       "segment_id": s.id, "road_name": s.road_name, "distance_km": str(s.distance_km),
                       "section_type": s.section_type.name} for s in route],
            "総走行距離_km": str(sum(totals.values(), Decimal(0))),
            "料金区分別距離_km": {t.name: str(v) for t,v in totals.items()},
            "注意": "OSM形状距離。料金計算用の公式営業距離ではありません。UNKNOWNを含む場合は料金区分未確認。"}


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("inputs", nargs="+", type=Path)
    build.add_argument("--output", type=Path, default=Path("data/processed"))
    build.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    build.add_argument("--rules", type=Path, default=Path("data/master/toll_section_rules.json"))
    route = commands.add_parser("route")
    route.add_argument("start")
    route.add_argument("end")
    route.add_argument("--data", type=Path, default=Path("data/processed"))
    route.add_argument("--mode", choices=["access", "junction"], default="access")
    args = parser.parse_args()
    try:
        if args.command == "build":
            generate(args.inputs, args.output, args.rules, args.bbox)
        else:
            print(json.dumps(route_result(args.data, args.start, args.end, args.mode), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
