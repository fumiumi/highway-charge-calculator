from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class SectionType(Enum):
    NORMAL = "普通区間"
    METROPOLITAN = "大都市近郊区間"
    SPECIAL = "海峡部等特別区間"
    SPECIAL_SYSTEM = "別料金体系"
    UNKNOWN = "未確認"


@dataclass
class RoadNode:
    id: str
    name: str
    node_type: str  # IC / JCT / TOPOLOGY (never invent an IC)
    latitude: float
    longitude: float
    aliases: list[str] = field(default_factory=list)


@dataclass
class RoadSegment:
    start_node: str
    end_node: str
    road_name: str
    distance_km: Decimal
    section_type: SectionType = SectionType.UNKNOWN
    id: str = ""
    osm_way_ids: list[int] = field(default_factory=list)
    osm_node_ids: list[int] = field(default_factory=list)
    highway: str = "motorway"
    osm_names: list[str] = field(default_factory=list)
    osm_route_relation_ids: list[int] = field(default_factory=list)
    toll_rule_source: str | None = None
    toll_rule_id: str | None = None
    source: str = "https://www.openstreetmap.org/copyright"


@dataclass(frozen=True)
class TollSectionRule:
    id: str
    road_name: str
    start: str
    end: str
    section_type: SectionType
    source: str
    title: str
    reviewed_on: str
    notes: str = ""
