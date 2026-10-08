"""
Column Mappers - translate DSH column names to CTM column names.
"""

from typing import Optional
from .ctm_constants import CTM_ENERGY_COLUMN_MAP, CTM_EMISSION_COLUMN_MAP


def normalize_string(s: str) -> str:
    """lowercase, spaces -> underscores, drop parens/dashes."""
    if not s:
        return ""
    return s.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")


# ── Energy ──────────────────────────────────────────────────────────────

def map_dsh_energy_to_ctm(dsh_col: str, flow_type: str) -> Optional[str]:
    """
    "Electricity" + "demand" -> "electricity_demand"
    Returns None if the column isn't recognized.
    """
    if dsh_col in CTM_ENERGY_COLUMN_MAP:
        return f"{CTM_ENERGY_COLUMN_MAP[dsh_col]}_{flow_type}"

    normalized = normalize_string(dsh_col)
    for dsh_name, ctm_base in CTM_ENERGY_COLUMN_MAP.items():
        if normalize_string(dsh_name) == normalized:
            return f"{ctm_base}_{flow_type}"

    return None


def get_all_energy_ctm_columns(with_flow_types: bool = True) -> list:
    columns = list(CTM_ENERGY_COLUMN_MAP.values())
    if not with_flow_types:
        return columns
    return [f"{c}_{suffix}" for c in columns for suffix in ("demand", "production")]


# ── Emissions ───────────────────────────────────────────────────────────

def map_dsh_emission_to_ctm(dsh_col: str) -> Optional[str]:
    """"CO2" -> "co2_emissions_production". Returns None if not recognized."""
    if dsh_col in CTM_EMISSION_COLUMN_MAP:
        return CTM_EMISSION_COLUMN_MAP[dsh_col]

    normalized = normalize_string(dsh_col)
    for dsh_name, ctm_col in CTM_EMISSION_COLUMN_MAP.items():
        if normalize_string(dsh_name) == normalized:
            return ctm_col

    return None


def get_all_emission_ctm_columns() -> list:
    return list(CTM_EMISSION_COLUMN_MAP.values())


# ── Bulk mapping (for entire rows) ─────────────────────────────────────

def map_energy_row(row_data: dict, energy_cols: list, flow_type: str) -> dict:
    """
    {"Electricity": 100, "Natural Gas": 50} + flow_type="demand"
      -> {"electricity_demand": "100", "natural_gas_demand": "50"}
    Skips None and zero values.
    """
    mapped = {}
    for dsh_col in energy_cols:
        value = row_data.get(dsh_col)
        if value is None or value == 0:
            continue
        ctm_col = map_dsh_energy_to_ctm(dsh_col, flow_type)
        if ctm_col:
            mapped[ctm_col] = str(value)
    return mapped


def map_emission_row(row_data: dict, emission_cols: list) -> dict:
    """
    {"CO2": 500, "Methane": 10} -> {"co2_emissions_production": "500", ...}
    Skips None and zero values.
    """
    mapped = {}
    for dsh_col in emission_cols:
        value = row_data.get(dsh_col)
        if value is None or value == 0:
            continue
        ctm_col = map_dsh_emission_to_ctm(dsh_col)
        if ctm_col:
            mapped[ctm_col] = str(value)
    return mapped


# ── Reverse maps (for validation/debugging) ─────────────────────────────

def reverse_energy_map() -> dict:
    return {v: k for k, v in CTM_ENERGY_COLUMN_MAP.items()}


def reverse_emission_map() -> dict:
    return {v: k for k, v in CTM_EMISSION_COLUMN_MAP.items()}
