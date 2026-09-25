"""Decimal-based sample tariff model; independent of routing and official billing."""
from dataclasses import dataclass
from decimal import Decimal, DecimalException, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from enum import Enum
from .models import SectionType
from .route_finder import aggregate_distance_by_section


class VehicleType(Enum):
    LIGHT = "軽自動車"
    REGULAR = "普通車"
    MEDIUM = "中型車"
    LARGE = "大型車"
    EXTRA_LARGE = "特大車"


UNIT_PRICES = {
    VehicleType.LIGHT: Decimal("19.68"),
    VehicleType.REGULAR: Decimal("24.60"),
    VehicleType.MEDIUM: Decimal("29.52"),
    VehicleType.LARGE: Decimal("40.59"),
    VehicleType.EXTRA_LARGE: Decimal("67.65"),
}
METROPOLITAN_FACTOR = Decimal("1.20")
TERMINAL_CHARGE = Decimal("150")
DISCOUNT_FACTOR_100_TO_200 = Decimal("0.75")
DISCOUNT_FACTOR_OVER_200 = Decimal("0.70")
TAX_FACTOR = Decimal("1.10")
MODEL_ID = "sample-distance-tariff-v1"
TARIFF_SOURCE = "https://www.driveplaza.com/assets/pdf/etc/dis/etc_dis_kanetsu/kanetsu_feecalculation.pdf"


class UnpricedSections(ValueError):
    def __init__(self, sections):
        self.sections = tuple(sections)
        super().__init__("単価未確認または未対応の区間: " + "、".join(s.name for s in sections))


@dataclass(frozen=True)
class FeeBreakdown:
    vehicle_type: VehicleType
    distances_km: dict[SectionType, Decimal]
    billed_distances_km: dict[SectionType, Decimal]
    unit_prices: dict[SectionType, Decimal]
    user_unit_prices: dict[SectionType, Decimal]
    total_billed_distance_km: Decimal
    discount_factor: Decimal
    variable_charge_yen: Decimal
    terminal_charge_yen: Decimal
    tax_included_yen: Decimal
    fee_yen: int


def nonnegative_decimal(value: Decimal, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{label}は有限の0以上のDecimalで指定してください。")
    return value


def parse_vehicle(value: str) -> VehicleType:
    for number, vehicle in enumerate(VehicleType, 1):
        if value.strip().upper() in {vehicle.name, vehicle.value, str(number)}:
            return vehicle
    raise ValueError("車種はLIGHT/REGULAR/MEDIUM/LARGE/EXTRA_LARGE、車種名、または1～5で指定してください。")


def calculate_section_fee(vehicle_type, distances_km, *, unknown_unit_price=None, special_unit_price=None):
    """Aggregate first, round each section to 0.1 km, apply one weighted discount.

    UNKNOWN is never reclassified. Explicit prices are user assumptions. SPECIAL_SYSTEM
    cannot use this distance tariff. OSM distance results are estimates, not invoices.
    """
    if not isinstance(vehicle_type, VehicleType):
        raise ValueError("指定された車種は存在しません。")
    if any(not isinstance(section, SectionType) for section in distances_km):
        raise ValueError("料金区分はSectionTypeで指定してください。")
    distances = {s: nonnegative_decimal(distances_km.get(s, Decimal(0)), "走行距離") for s in SectionType}
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN
        rates = {SectionType.NORMAL: UNIT_PRICES[vehicle_type],
                 SectionType.METROPOLITAN: UNIT_PRICES[vehicle_type] * METROPOLITAN_FACTOR}
        overrides = {}
        for section, value in ((SectionType.UNKNOWN, unknown_unit_price), (SectionType.SPECIAL, special_unit_price)):
            if value is not None:
                rates[section] = nonnegative_decimal(value, "指定単価")
                overrides[section] = value
        # Check before rounding, so a small unknown segment cannot disappear silently.
        missing = [s for s in SectionType if distances[s] > 0 and s not in rates]
        if missing:
            raise UnpricedSections(missing)
        try:
            billed = {s: d.quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN) for s,d in distances.items()}
            total = sum(billed.values(), Decimal(0))
            if not total:
                return FeeBreakdown(vehicle_type, distances, billed, rates, overrides, total,
                                    Decimal(1), Decimal(0), Decimal(0), Decimal(0), 0)
            discounted_km = (min(total, Decimal(100))
                             + min(max(total - 100, Decimal(0)), Decimal(100)) * DISCOUNT_FACTOR_100_TO_200
                             + max(total - 200, Decimal(0)) * DISCOUNT_FACTOR_OVER_200)
            factor = discounted_km / total
            before_discount = sum((billed[s] * rates[s] for s in rates), Decimal(0))
            # Multiply before dividing to avoid rounding an intermediate repeating factor.
            variable = before_discount * discounted_km / total
            taxed = (variable + TERMINAL_CHARGE) * TAX_FACTOR
            if taxed <= Decimal(10000):
                fee = int(taxed.quantize(Decimal("1E1"), rounding=ROUND_HALF_UP))
            else:
                fee = int(taxed.quantize(Decimal("1E2"), rounding=ROUND_DOWN))
        except DecimalException as exc:
            raise ValueError("距離または単価が計算可能な範囲を超えています。") from exc
        return FeeBreakdown(vehicle_type, distances, billed, rates, overrides, total,
                            factor, variable, TERMINAL_CHARGE, taxed, fee)


def calculate_route_fee(vehicle_type, route, **kwargs):
    # Validate individual edges before aggregation: a negative edge must not cancel out.
    for segment in route:
        nonnegative_decimal(segment.distance_km, "区間距離")
        if not isinstance(segment.section_type, SectionType):
            raise ValueError("区間の料金区分が不正です。")
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN
        return calculate_section_fee(vehicle_type, aggregate_distance_by_section(route), **kwargs)


def calculate_highway_fee(vehicle_type: VehicleType, distance_km: Decimal) -> int:
    """Compatibility API for the supplied single NORMAL-section example."""
    return calculate_section_fee(vehicle_type, {SectionType.NORMAL: distance_km}).fee_yen
