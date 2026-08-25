"""
Data Models - type-safe dataclasses shared across CONNECT_CTM.

NOTE on transformation overrides: these used to be hardcoded constants
(TRANSFORMATION_OVERRIDES / OVERRIDES / ALL_OVERRIDES) baked into the push
logic. They're redundant now — the Streamlit UI collects them from the user
per push. DEFAULT_TRANSFORMATION_OVERRIDES below is only the suggested
starting value for that UI field; it is NOT applied automatically anywhere
in this module. Callers must pass their own `transformation_overrides` dict
into the ctm_push functions.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════

class FlowType(str, Enum):
    DEMAND = "demand"
    SUPPLY = "supply"
    PRODUCTION = "production"
    CAPTIVE_USE = "captive use"


class SiteType(str, Enum):
    REGULAR = "regular"      # sector/cluster/site hierarchy
    BOTTOM_UP = "bottom_up"  # flat site pattern
    CUSTOM = "custom"        # ##new_cc_siteN## pattern


# ═══════════════════════════════════════════════════════════════════════
# Site Information
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SiteMetadata:
    """Metadata about a CTM site."""
    name: str
    site_type: SiteType
    sector: str
    cluster: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def __hash__(self):
        return hash((self.name, self.site_type))


# ═══════════════════════════════════════════════════════════════════════
# Scenario Data
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ScenarioRow:
    """Single row of scenario data."""
    scenario: str
    year: str
    flow_type: str
    plant_name: str
    sector: Optional[str] = None
    cluster: Optional[str] = None
    values: Dict[str, Optional[float]] = field(default_factory=dict)

    def get_value(self, column: str) -> Optional[float]:
        return self.values.get(column)

    def has_nonzero_values(self) -> bool:
        return any(v and v != 0 for v in self.values.values())


@dataclass
class ScenarioData:
    """Container for all scenario rows for a push run."""
    rows: List[ScenarioRow] = field(default_factory=list)
    reference_year: int = 2024

    def filter_by_scenario(self, scenario: str) -> List[ScenarioRow]:
        return [r for r in self.rows if r.scenario == scenario]

    def filter_by_plant(self, plant_name: str) -> List[ScenarioRow]:
        return [r for r in self.rows if r.plant_name == plant_name]

    def get_scenarios(self) -> List[str]:
        return sorted(set(r.scenario for r in self.rows))

    def get_plants(self) -> List[str]:
        return sorted(set(r.plant_name for r in self.rows))

    def get_years(self) -> List[str]:
        return sorted(set(r.year for r in self.rows))


# ═══════════════════════════════════════════════════════════════════════
# CTM Inputs & Push Results
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CTMInputs:
    """Container for CTM inputs about to be pushed."""
    inputs: Dict[str, str] = field(default_factory=dict)

    def add_input(self, key: str, value: str):
        self.inputs[key] = value

    def add_inputs(self, inputs_dict: Dict[str, str]):
        self.inputs.update(inputs_dict)

    def size(self) -> int:
        return len(self.inputs)

    def to_dict(self) -> Dict[str, str]:
        return self.inputs.copy()


@dataclass
class CTMPushResult:
    """Result of pushing one (scenario, year) to CTM."""
    scenario: str
    year: str
    success: bool
    session_id: Optional[str] = None
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# Bottom-up site classification
# ═══════════════════════════════════════════════════════════════════════

BOTTOM_UP_SITES = {
    'shell_pernis', 'bp', 'exxonmobil', 'gunvor', 'vpr_energy', 'zeeland_refinery',
    'tata_steel', 'arcelor_mittal', 'oci', 'yara', 'shell_moerdijk', 'dow', 'sabic',
    'air_products', 'air_products_merseyweg', 'air_liquide', 'air_liquide_boz',
    'biomcn', 'anqore', 'fibrant', 'lyondellbasell', 'chemelot_other',
    'albemarle', 'nobian_hengelo', 'nobian_delfzijl', 'nobian_botlek',
}


def is_bottom_up_site(site_name: str) -> bool:
    return site_name.lower() in BOTTOM_UP_SITES


# ═══════════════════════════════════════════════════════════════════════
# Transformation override default (UI suggestion only — see module docstring)
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_TRANSFORMATION_OVERRIDES: Dict[str, str] = {
    "air_liquide": "1",
    "air_liquide_boz": "1",
    "air_products": "1",
    "air_products_merseyweg": "1",
    "sabic": "1",

    'shell_pernis&&transformation': "0",
    'bp&&transformation': "0",
    'exxonmobil&&transformation': "0",

    'gunvor&&transformation': "0",
    'vpr_energy&&transformation' : "0",
    'zeeland_refinery&&transformation': "0",
    
    'shell_moerdijk&&transformation': "0",
    'dow&&transformation': "0",

    'other_chemicals&&chemelot&&cluster_site_other_chemicals_chemelot&&transformation': "0"
}
