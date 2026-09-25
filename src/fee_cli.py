"""CLI: vehicle + entry/exit IC -> distance breakdown and sample-model fee."""
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from .fee_calculator import (VehicleType, parse_vehicle, nonnegative_decimal,
                             calculate_route_fee, UnpricedSections, MODEL_ID, TARIFF_SOURCE)
from .models import SectionType
from .route_finder import RouteFinder, aggregate_distance_by_section
from .storage import load_graph


NOTICE = ("OSM形状距離に基づくサンプル式の概算です。公式営業距離・実際の請求額ではありません。"
          "ETC/時間帯割引、中央道の上限料金、路線別の特例は未反映です。")


def decimal_argument(value):
    try:
        return nonnegative_decimal(Decimal(value), "指定単価")
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError("単価は有限の0以上の数値で指定してください。") from exc


def add_fee_arguments(parser):
    parser.add_argument("--vehicle", help="LIGHT/REGULAR/MEDIUM/LARGE/EXTRA_LARGE、車種名、または1～5")
    parser.add_argument("--start", help="入口IC名")
    parser.add_argument("--end", help="出口IC名")
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument("--unknown-unit-price", type=decimal_argument, help="未確認区間の仮定単価（選択車種の税抜円/km）。区分はUNKNOWNのまま")
    parser.add_argument("--special-unit-price", type=decimal_argument, help="特別区間の仮定単価（選択車種の税抜円/km）")
    parser.add_argument("--json", action="store_true", help="JSON出力（対話入力なし）")


def quote_route(vehicle, start, end, directory, **prices):
    graph, nodes, access = load_graph(directory)
    finder = RouteFinder(graph, nodes, access)
    for name in (start, end):
        if any(nodes[n].node_type != "IC" for n in finder.resolve(name)):
            raise ValueError(f"入口・出口にはICを指定してください: {name}")
    route = finder.find_route(start, end)
    totals = aggregate_distance_by_section(route)
    report = {
        "status": "estimate", "model": MODEL_ID, "vehicle": vehicle.name, "vehicle_name": vehicle.value,
        "start_ic": start, "end_ic": end,
        "total_distance_km": str(sum(totals.values(), Decimal(0))),
        "distances_km": {s.name: str(totals[s]) for s in SectionType},
        "segment_ids": [s.id for s in route], "fee_yen": None,
        "notice": NOTICE, "tariff_source": TARIFF_SOURCE,
        "user_unit_prices_yen_per_km": {s: str(value) for s,value in
            (("UNKNOWN", prices.get("unknown_unit_price")), ("SPECIAL", prices.get("special_unit_price"))) if value is not None},
    }
    try:
        fee = calculate_route_fee(vehicle, route, **prices)
    except UnpricedSections as exc:
        report.update(status="unpriced", error=str(exc), unpriced_sections=[s.name for s in exc.sections])
        return report
    report.update(
        billed_distances_km={s.name: str(d) for s,d in fee.billed_distances_km.items()},
        total_billed_distance_km=str(fee.total_billed_distance_km),
        unit_prices_yen_per_km={s.name: str(p) for s,p in fee.unit_prices.items()},
        discount_factor=str(fee.discount_factor), variable_charge_yen=str(fee.variable_charge_yen),
        terminal_charge_yen=str(fee.terminal_charge_yen), tax_included_yen=str(fee.tax_included_yen),
        fee_yen=fee.fee_yen,
    )
    return report


def print_report(report):
    print(f"車種: {report['vehicle_name']}")
    print(f"入口IC: {report['start_ic']} / 出口IC: {report['end_ic']}")
    print(f"総走行距離: {Decimal(report['total_distance_km']):.3f} km")
    for section in SectionType:
        billed = report.get("billed_distances_km", {}).get(section.name)
        suffix = f"（計算用 {billed} km）" if billed is not None else ""
        print(f"  {section.value} ({section.name}): {Decimal(report['distances_km'][section.name]):.3f} km{suffix}")
    for section, rate in report["user_unit_prices_yen_per_km"].items():
        print(f"利用者指定の仮定単価: {section} = {rate} 円/km（税抜）")
    if report["fee_yen"] is None:
        print(f"料金計算不可: {report['error']}")
        print("未確認区間に仮定単価を使う場合は --unknown-unit-price 円/km を明示してください。")
    else:
        print(f"計算用距離: {report['total_billed_distance_km']} km")
        print(f"最終料金（概算・税込）: {report['fee_yen']:,}円")
    print(report["notice"])


def run_fee(args, parser):
    try:
        provided = [args.vehicle is not None, args.start is not None, args.end is not None]
        if not any(provided) and not args.json:
            print("車種を選択してください:")
            for index, vehicle in enumerate(VehicleType, 1):
                print(f"{index}: {vehicle.value}")
            args.vehicle = input("番号または車種名: ").strip()
            vehicle = parse_vehicle(args.vehicle)
            args.start = input("入口IC: ").strip()
            args.end = input("出口IC: ").strip()
        else:
            if not all(provided):
                raise ValueError("--vehicle、--start、--endをすべて指定してください。")
            vehicle = parse_vehicle(args.vehicle)
        if not args.start.strip() or not args.end.strip():
            raise ValueError("入口ICと出口ICを入力してください。")
        report = quote_route(vehicle, args.start.strip(), args.end.strip(), args.data,
                             unknown_unit_price=args.unknown_unit_price,
                             special_unit_price=args.special_unit_price)
    except (ValueError, OSError, EOFError) as exc:
        message = str(exc) or "入力が終了しました。"
        if args.json:
            print(json.dumps({"status": "error", "fee_yen": None, "error": message}, ensure_ascii=False))
            return 2
        parser.exit(2, f"エラー: {message}\n")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0 if report["fee_yen"] is not None else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_fee_arguments(parser)
    raise SystemExit(run_fee(parser.parse_args(), parser))


if __name__ == "__main__":
    main()
