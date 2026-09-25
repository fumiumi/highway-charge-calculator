from decimal import Decimal, localcontext, ROUND_UP
import pytest
from src.fee_calculator import (VehicleType, calculate_highway_fee, calculate_section_fee,
                               calculate_route_fee, UnpricedSections, parse_vehicle)
from src.models import SectionType, RoadSegment

D = Decimal
V = VehicleType
S = SectionType


@pytest.mark.parametrize('vehicle,expected', [(V.LIGHT,2330),(V.REGULAR,2870),(V.MEDIUM,3410),(V.LARGE,4630),(V.EXTRA_LARGE,7610)])
def test_vehicle_prices_at_100km(vehicle, expected):
    assert calculate_highway_fee(vehicle,D('100')) == expected


@pytest.mark.parametrize('distance,expected', [('0',0),('0.05',0),('0.15',170),('100',2870),('150',3890),('200',4900),('250',5850),('1000',20000)])
def test_supplied_sample_formula(distance, expected):
    assert calculate_highway_fee(V.REGULAR,D(distance)) == expected


def test_mixed_sections_share_discount_and_terminal_charge():
    fee = calculate_section_fee(V.REGULAR,{S.NORMAL:D(100),S.METROPOLITAN:D(100)})
    assert fee.discount_factor == D('.875')
    assert fee.variable_charge_yen == D('4735.5')
    assert fee.terminal_charge_yen == D(150)
    assert fee.fee_yen == 5370


@pytest.mark.parametrize('price,taxed,expected', [('8940','9999',10000),('8941','10000.1',10000),('8986','10049.6',10000),('9032','10100.2',10100)])
def test_above_10000_rounds_down_to_100(price,taxed,expected):
    fee = calculate_section_fee(V.REGULAR,{S.SPECIAL:D(1)},special_unit_price=D(price))
    assert fee.tax_included_yen == D(taxed)
    assert fee.fee_yen == expected


@pytest.mark.parametrize('bad', ['-1','NaN','sNaN','Infinity','-Infinity','1E99999'])
def test_invalid_distances(bad):
    with pytest.raises(ValueError):
        calculate_highway_fee(V.REGULAR,D(bad))


@pytest.mark.parametrize('section',[S.UNKNOWN,S.SPECIAL,S.SPECIAL_SYSTEM])
def test_unpriced_sections_are_not_silently_free(section):
    with pytest.raises(UnpricedSections) as error:
        calculate_section_fee(V.REGULAR,{S.NORMAL:D(10),section:D('.001')})
    assert section in error.value.sections


def test_explicit_unknown_rate_preserves_original_classification():
    route=[RoadSegment('a','b','TEST',D(10),S.UNKNOWN)]
    fee=calculate_route_fee(V.LIGHT,route,unknown_unit_price=D('19.68'))
    assert fee.fee_yen==380
    assert fee.distances_km[S.UNKNOWN]==10
    assert fee.distances_km[S.NORMAL]==0
    assert fee.user_unit_prices=={S.UNKNOWN:D('19.68')}
    assert route[0].section_type==S.UNKNOWN


def test_special_system_cannot_use_unknown_override():
    with pytest.raises(UnpricedSections):
        calculate_section_fee(V.REGULAR,{S.SPECIAL_SYSTEM:D(1)},unknown_unit_price=D(25),special_unit_price=D(30))


def test_distance_rounding_is_after_aggregation_and_independent_of_context():
    route=[RoadSegment('a','b','TEST',D('.04'),S.NORMAL),RoadSegment('b','c','TEST',D('.04'),S.NORMAL)]
    with localcontext() as ctx:
        ctx.prec=4
        ctx.rounding=ROUND_UP
        fee=calculate_route_fee(V.REGULAR,route)
        assert fee.total_billed_distance_km==D('.1')
        assert fee.fee_yen==170
        assert calculate_highway_fee(V.REGULAR,D('.05'))==0


def test_negative_segment_cannot_cancel_positive_segment():
    route=[RoadSegment('a','b','TEST',D(-1),S.NORMAL),RoadSegment('b','c','TEST',D(10),S.NORMAL)]
    with pytest.raises(ValueError):
        calculate_route_fee(V.REGULAR,route)


@pytest.mark.parametrize('bad',[D('-1'),D('NaN'),D('Infinity')])
def test_invalid_override_even_if_unused(bad):
    with pytest.raises(ValueError):
        calculate_section_fee(V.REGULAR,{S.NORMAL:D(10)},unknown_unit_price=bad)


@pytest.mark.parametrize('value', ['2','普通車','regular','REGULAR'])
def test_vehicle_aliases(value):
    assert parse_vehicle(value)==V.REGULAR


def test_mixed_fee_independent_of_travel_direction():
    route=[RoadSegment('a','b','TEST',D(130),S.NORMAL),RoadSegment('b','c','TEST',D(100),S.METROPOLITAN)]
    assert calculate_route_fee(V.REGULAR,route).fee_yen == calculate_route_fee(V.REGULAR,list(reversed(route))).fee_yen
