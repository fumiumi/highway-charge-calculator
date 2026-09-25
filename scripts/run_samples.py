"""Run real-data examples and optionally verify the committed results exactly."""
import argparse
import json
from pathlib import Path
from decimal import Decimal
from src.main import route_result
from src.storage import write_json

CASES = [
    ("調布IC", "国立府中IC"),
    ("調布IC", "上野原IC"),
    ("調布IC", "相模原IC"),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data/processed"))
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    results=[route_result(args.data,a,b) for a,b in CASES]
    target=args.data / "sample_routes.json"
    if args.check:
        if results != json.loads(target.read_text()):
            raise ValueError("Sample output changed; review and regenerate")
    else:
        write_json(target,results)
    for result in results:
        print(f"入口IC: {result['入口IC']} / 出口IC: {result['出口IC']}")
        roads=[]
        for seg in result["採用経路"]:
            if not roads or roads[-1]!=seg["road_name"]:
                roads.append(seg["road_name"])
        print("採用経路: " + " → ".join(roads))
        print("通過IC/JCT: " + " → ".join(result["通過IC_JCT"]))
        print(f"総走行距離: {Decimal(result['総走行距離_km']):.3f} km")
        for key,value in result["料金区分別距離_km"].items():
            print(f"  {key}: {Decimal(value):.3f} km")
        print()


if __name__=="__main__":
    main()
