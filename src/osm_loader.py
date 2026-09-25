"""Two-pass PBF/XML reader: retain only motorway geometry, never all region nodes."""
from dataclasses import dataclass, field
from pathlib import Path
import osmium
import sys
import re


@dataclass
class OSMData:
    nodes: dict = field(default_factory=dict)
    ways: dict = field(default_factory=dict)
    restrictions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    external_nodes: set = field(default_factory=set)


def load_osm(paths: list[Path]) -> OSMData:
    data = OSMData()
    # Keeping restriction-related ways out is conservative and avoids inventing turns.
    blocked = set()
    route_members = {}
    pending_restrictions = []

    class Ways(osmium.SimpleHandler):
        def way(self, w):
            tags = dict(w.tags)
            if tags.get("highway") not in {"motorway", "motorway_link"}:
                return
            access = next((tags[k] for k in ("motorcar", "motor_vehicle", "vehicle", "access") if k in tags), "yes")
            reason = None
            if access not in {"yes", "permissive", "designated"}:
                reason = "restricted_access"
            if any(k.split(":")[0] in {"access", "vehicle", "motor_vehicle", "motorcar", "oneway"} and ":conditional" in k for k in tags) or tags.get("oneway") in {"reversible", "alternating"}:
                reason = "conditional_or_reversible"
            if any(k in tags for k in ("motorcar:forward", "motorcar:backward", "motor_vehicle:forward", "motor_vehicle:backward", "access:forward", "access:backward")):
                reason = "directional_access"
            if reason:
                data.warnings.append({"way": w.id, "reason": reason})
                return
            item = {"id": w.id, "nodes": [n.ref for n in w.nodes], "tags": tags, "version": w.version}
            if w.id in data.ways and data.ways[w.id] != item:
                raise ValueError(f"Conflicting OSM way versions: {w.id}; use matching snapshots")
            data.ways[w.id] = item

        def relation(self, r):
            tags = dict(r.tags)
            if tags.get("type") == "route" and tags.get("route") == "road":
                name = tags.get("name:ja") or tags.get("name")
                if name:
                    name = re.sub(r"[ 　]*(?:上り|下り)$", "", name)
                    if not re.search(r"自動車道|高速道路|首都高速|高速$|expressway|motorway", name, re.IGNORECASE):
                        return
                    for m in r.members:
                        if m.type == "w":
                            route_members.setdefault(m.ref, set()).add((name, r.id))
            if tags.get("type") == "restriction":
                pending_restrictions.append({"id": r.id, "tags": tags,
                    "members": [(m.type, m.ref, m.role) for m in r.members]})

    for path in paths:
        print(f"Reading motorway ways: {path.name}", file=sys.stderr, flush=True)
        Ways().apply_file(str(path), filters=[osmium.filter.TagFilter(("highway", "motorway"), ("highway", "motorway_link")).enable_for(osmium.osm.WAY)])
    for row in pending_restrictions:
        tags = row["tags"]
        if set(tags.get("except", "").split(";")) & {"motorcar", "motor_vehicle", "vehicle"}:
            continue
        restriction = tags.get("restriction:motorcar") or tags.get("restriction:motor_vehicle") or tags.get("restriction")
        if not restriction and not any(k in tags for k in ("restriction:conditional", "restriction:motorcar:conditional", "restriction:motor_vehicle:conditional")):
            continue
        fr = [ref for typ, ref, role in row["members"] if typ == "w" and role == "from"]
        to = [ref for typ, ref, role in row["members"] if typ == "w" and role == "to"]
        via = [(typ, ref) for typ, ref, role in row["members"] if role == "via"]
        if not set(fr) & data.ways.keys():
            continue
        if len(fr) == len(to) == len(via) == 1 and via[0][0] == "n" and restriction and restriction.startswith(("no_", "only_")) and not any("conditional" in k for k in tags):
            data.restrictions.append({"id": row["id"], "from_way": fr[0], "to_way": to[0], "via_node": via[0][1], "restriction": restriction})
        else:
            blocked.update(fr)
    for wid, way in data.ways.items():
        candidates = route_members.get(wid, set())
        names = {name for name, _ in candidates}
        if len(names) == 1:
            way["route_name"] = next(iter(names))
            way["route_relation_ids"] = sorted(ident for _, ident in candidates)
        elif len(names) > 1:
            data.warnings.append({"way": wid, "reason": "ambiguous_route_names", "names": sorted(names)})
    for wid in sorted(blocked & data.ways.keys()):
        data.ways.pop(wid)
        data.warnings.append({"way": wid, "reason": "turn_restriction_conservative_exclusion"})
    required = {n for w in data.ways.values() for n in w["nodes"]}
    data.external_nodes.intersection_update(required)

    class Nodes(osmium.SimpleHandler):
        def way(self, w):
            if w.tags.get("highway") in {"trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential"}:
                data.external_nodes.update(n.ref for n in w.nodes if n.ref in required)

        def node(self, n):
            if n.id not in required:
                return
            item = {"latitude": n.location.lat, "longitude": n.location.lon, "tags": dict(n.tags)}
            if n.id in data.nodes and data.nodes[n.id] != item:
                raise ValueError(f"Conflicting OSM node versions: {n.id}")
            data.nodes[n.id] = item

    for path in paths:
        print(f"Reading selected geometry: {path.name}", file=sys.stderr, flush=True)
        Nodes().apply_file(str(path), filters=[osmium.filter.IdFilter(required).enable_for(osmium.osm.NODE), osmium.filter.KeyFilter("highway").enable_for(osmium.osm.WAY)])
    missing = required - data.nodes.keys()
    if missing:
        raise ValueError(f"Incomplete extract: {len(missing)} geometry nodes missing")
    if not data.ways:
        raise ValueError("No motorway ways found; no synthetic fallback")
    return data
