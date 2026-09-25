#!/usr/bin/env python3
"""Download dated Geofabrik extracts atomically; verify provider MD5 + record SHA256."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


def digest(path, algorithm):
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(region, snapshot, directory, expected_sha256=None):
    filename = f"{region}-{snapshot}.osm.pbf"
    url = f"https://download.geofabrik.de/asia/japan/{filename}"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    with urlopen(url + ".md5", timeout=60) as response:
        expected = response.read().decode().split()[0]
    if len(expected) != 32:
        raise ValueError("Invalid provider checksum")
    if not target.exists() or digest(target, "md5") != expected:
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            with urlopen(url, timeout=120) as response, temporary.open("wb") as output:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(chunk)
            if digest(temporary, "md5") != expected:
                raise ValueError("Provider checksum mismatch")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    sha256 = digest(target, "sha256")
    if expected_sha256 and sha256 != expected_sha256:
        raise ValueError(f"Pinned SHA256 mismatch for {filename}")
    metadata_path = target.with_suffix(".manifest.json")
    previous = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    downloaded_at = previous.get("downloaded_at") if previous.get("sha256") == sha256 else None
    downloaded_at = downloaded_at or datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat()
    manifest = {"file": filename, "url": url, "downloaded_at": downloaded_at,
                "md5": expected, "sha256": sha256, "bytes": target.stat().st_size,
                "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors"}
    target.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=["kanto", "chubu"], default=["kanto"])
    parser.add_argument("--snapshot", default="260923", help="YYMMDD dated snapshot; latest changes over time")
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--manifest", type=Path, help="Verify against committed input SHA256 values")
    args = parser.parse_args()
    pins = {}
    if args.manifest:
        pins = {r["file"]: r["sha256"] for r in json.loads(args.manifest.read_text())["inputs"]}
    for region in args.regions:
        filename = f"{region}-{args.snapshot}.osm.pbf"
        if args.manifest and filename not in pins:
            parser.error(f"No checksum in manifest for {filename}")
        download(region, args.snapshot, args.output, pins.get(filename))
