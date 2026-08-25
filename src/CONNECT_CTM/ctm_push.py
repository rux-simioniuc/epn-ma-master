"""
CTM Push - reads DSH plant scenario data (plus optional cluster/sector demand
curves) and pushes it to CTM, grouped by (scenario, year) so all plants for
a given scenario/year land in a single CTM session.

Consolidates what used to be push_to_ctm.py + push_to_ctm_modules.py.
Column-mapping and CTM-key-building logic is NOT duplicated here — it reuses
mappers.py and ctm_keys.py, which is what those two files used to reimplement
independently.

Fixed while merging (see conversation for detail):
  - production/flexibility table loading used a single-element tuple-unpack
    on a function that returns a plain DataFrame — every load silently failed
    and was swallowed by a bare except. Fixed.
  - debug JSON dumps of pushed inputs were written to the current directory
    on every single push, unconditionally. Now opt-in via `session_path`.
  - `extra_inputs: Dict = {}` mutable default argument -> now None-safe.

Dropped as dead code (confirmed unreferenced anywhere in either source file):
  - push_to_ctm_session() — also deleted the session right after pushing,
    which would have destroyed the session ID before ETM coupling could use it.
  - push_plant_to_ctm() — superseded by push_aggregated_by_scenario_year().
  - construct_cluster_inputs() / construct_sector_inputs() — their replacement,
    build_sector_cluster_sites(), uses a different key pattern entirely.

Preserved as-is (not "fixed" — flagging so you can confirm it's intentional):
  regular sites always get a transformation flag (default "0"); bottom-up
  sites only get one if you explicitly pass an override for them.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import polars as pl

from .ctm_client import CTMClient
from .ctm_keys import (
    build_site_enabled_key, build_site_transformation_key, build_site_data_key,
    build_bottom_up_enabled_key, build_bottom_up_transformation_key, build_bottom_up_data_key,
    build_custom_site_enabled_key, build_custom_site_sector_key, build_custom_site_cluster_key,
    build_custom_site_latitude_key, build_custom_site_longitude_key, build_custom_site_data_key,
    get_valid_keys_for_site, get_valid_keys_for_bottom_up_site, get_valid_keys_for_custom_site,
)
from .mappers import map_dsh_energy_to_ctm, map_dsh_emission_to_ctm
from .string_utils import fix_string
from .curves_utils import get_final_cluster_sector_curves
from .read_DSH_files import (
    read_all_scenario_sheets, read_production_table,
    read_production_table_curves, read_plant_details,
)
from .constants import SCENARIO_YEARS, REFERENCE_YEAR, EMISSION_COLS_ORDER, UTILITY_COLS_ORDER, ALL_SCENARIOS


# ═══════════════════════════════════════════════════════════════════════
# Hardcoded, push-time-only CTM inputs (site-specific coordinates/flags —
# not transformation overrides, which now come from the UI, see models.py)
# ═══════════════════════════════════════════════════════════════════════

def get_custom_ctm_inputs() -> Dict[str, str]:
    """Hardcoded plant-specific CTM inputs applied to every push."""
    return {
        "tata_steel&&waste_gas_to_chp_first": "1",
        "shell_pernis&&waste_gas_to_chp_first": "1",
        "##new_cc_site17##&&latitude": "53.30315087671532",
        "##new_cc_site17##&&longitude": "6.986967610715365",
        "##new_cc_site9##&&latitude": "53.30315087671532",
        "##new_cc_site9##&&longitude": "6.986967610715365",
    }


# ═══════════════════════════════════════════════════════════════════════
# Part 1: Per-row input builders (regular / bottom-up / custom site)
# ═══════════════════════════════════════════════════════════════════════

def _map_energy_row(row_data: dict, energy_cols: List[str], flow_type: str) -> Dict[str, str]:
    """{'Electricity': 100, ...} -> {'electricity_demand': '100', ...}. Skips peak/None/0."""
    mapped = {}
    for col in energy_cols:
        if 'peak' in col:
            continue
        val = row_data.get(col)
        if val is None or val == 0:
            continue
        ctm_col = map_dsh_energy_to_ctm(col, flow_type)
        if ctm_col:
            mapped[ctm_col] = str(val)
    return mapped


def _map_emission_row(row_data: dict, emission_cols: List[str]) -> Dict[str, str]:
    """Production-only. {'CO2': 500, ...} -> {'co2_emissions_production': '500', ...}."""
    mapped = {}
    for col in emission_cols:
        val = row_data.get(col)
        if val is None or val == 0:
            continue
        ctm_col = map_dsh_emission_to_ctm(col)
        if ctm_col:
            mapped[ctm_col] = str(val)
    return mapped


def construct_site_inputs(
    sector: str,
    cluster: str,
    site: str,
    row_data: dict,
    emission_cols: List[str],
    energy_cols: List[str],
    flow_type: str,
    logs: list,
    transformation: Optional[str] = None,
) -> Dict[str, str]:
    """Build CTM inputs for a regular (sector/cluster/site) site."""
    sector = fix_string(sector)
    cluster = fix_string(cluster)

    inputs = {build_site_enabled_key(sector, cluster, site): "1"}

    ALWAYS_TRANSFORMATION_SECTORS = {'methanol', 'ammonia', 'waste'}
    inferred = "1" if sector.lower() in ALWAYS_TRANSFORMATION_SECTORS else "0"
    inputs[build_site_transformation_key(sector, cluster, site)] = transformation or inferred

    for ctm_col, val in _map_energy_row(row_data, energy_cols, flow_type).items():
        inputs[build_site_data_key(sector, cluster, site, ctm_col)] = val

    if flow_type == "production":
        for ctm_col, val in _map_emission_row(row_data, emission_cols).items():
            inputs[build_site_data_key(sector, cluster, site, ctm_col)] = val

    valid_keys = get_valid_keys_for_site(sector, cluster, site)
    return validate_and_filter_inputs(inputs, valid_keys, logs)


def construct_bottom_up_inputs(
    sector: str,
    cluster: str,
    site: str,
    row_data: dict,
    emission_cols: List[str],
    energy_cols: List[str],
    flow_type: str,
    logs: list,
    transformation: Optional[str] = None,
) -> Dict[str, str]:
    """
    Build CTM inputs for a bottom-up (flat) site.

    NOTE: unlike construct_site_inputs, no transformation key is set at all
    unless `transformation` is explicitly passed — preserved from the
    original behavior, not something I changed. Confirm this is intentional.
    """
    sector = fix_string(sector)
    cluster = fix_string(cluster)

    inputs = {build_bottom_up_enabled_key(site): "1"}

    if transformation:
        inputs[build_bottom_up_transformation_key(site)] = transformation

    for ctm_col, val in _map_energy_row(row_data, energy_cols, flow_type).items():
        inputs[build_bottom_up_data_key(site, ctm_col)] = val

    if flow_type == "production":
        for ctm_col, val in _map_emission_row(row_data, emission_cols).items():
            inputs[build_bottom_up_data_key(site, ctm_col)] = val

    valid_keys = get_valid_keys_for_bottom_up_site(site)
    return validate_and_filter_inputs(inputs, valid_keys, logs)


def construct_custom_site_inputs(
    sector: str,
    cluster: str,
    custom_site: str,
    row_data: dict,
    emission_cols: List[str],
    energy_cols: List[str],
    flow_type: str,
    logs: list,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Dict[str, str]:
    """Build CTM inputs for a new (##new_cc_siteN##) site."""
    sector = fix_string(sector)
    cluster = fix_string(cluster)

    inputs = {build_custom_site_enabled_key(custom_site): "1"}

    if sector:
        inputs[build_custom_site_sector_key(custom_site)] = sector
    if cluster:
        inputs[build_custom_site_cluster_key(custom_site)] = cluster
    if latitude is not None:
        inputs[build_custom_site_latitude_key(custom_site)] = str(latitude)
    if longitude is not None:
        inputs[build_custom_site_longitude_key(custom_site)] = str(longitude)

    for ctm_col, val in _map_energy_row(row_data, energy_cols, flow_type).items():
        inputs[build_custom_site_data_key(custom_site, ctm_col)] = val

    if flow_type == "production":
        for ctm_col, val in _map_emission_row(row_data, emission_cols).items():
            inputs[build_custom_site_data_key(custom_site, ctm_col)] = val

    valid_keys = get_valid_keys_for_custom_site(custom_site)
    return validate_and_filter_inputs(inputs, valid_keys, logs)


def validate_and_filter_inputs(inputs: Dict[str, str], valid_keys: set, logs: list) -> Dict[str, str]:
    """Filter inputs to only valid CTM keys, logging anything dropped."""
    filtered = {}
    invalid = []
    for key, value in inputs.items():
        if key in valid_keys:
            filtered[key] = value
        else:
            invalid.append(key)

    if invalid:
        preview = ', '.join(invalid[:3])
        logs.append(f"    [INVALID] Filtered {len(invalid)} keys: {preview}{'...' if len(invalid) > 3 else ''}")

    return filtered


# ═══════════════════════════════════════════════════════════════════════
# Part 2: Load all plants' scenario data, grouped by (scenario, year)
# ═══════════════════════════════════════════════════════════════════════

def load_all_plants_scenario_data(
    plants_workbook_dir: str | list,
    mapping_df: pl.DataFrame,
    emission_cols: List[str],
    energy_cols: List[str],
    reference_year: int = REFERENCE_YEAR,
    aggregate_flow_types: bool = True,
) -> Tuple[Dict, Dict, List, List]:
    """
    Load all plants' scenario data and group rows by (scenario, year).

    `plants_workbook_dir` accepts either a directory path (str) — reads every
    .xlsx in it — or a list of (filename, bytes)/UploadedFile items, for the
    Streamlit upload flow.

    Returns:
        (all_scenario_data, scenario_year_groups, logs, errors)

        all_scenario_data: {
            plant_id: {"name", "df", "mapping_row", "latitude", "longitude",
                       optionally "production_df", "flexibility_df"}
        }
        scenario_year_groups: {(scenario, year): [(plant_id, row_data), ...]}
    """
    logs = []
    errors = []
    all_scenario_data = {}

    if isinstance(plants_workbook_dir, str):
        workbook_dir = Path(plants_workbook_dir)
        workbooks = [(wb_path, None) for wb_path in workbook_dir.glob("*.xlsx")]
        logs.append(f"Found {len(workbooks)} workbooks in {workbook_dir}")
    elif isinstance(plants_workbook_dir, list):
        workbooks = []
        for item in plants_workbook_dir:
            if isinstance(item, tuple):
                filename, file_bytes = item
            else:
                filename = item.name
                file_bytes = item
            workbooks.append((filename, file_bytes))
        logs.append(f"Found {len(workbooks)} Excel files in list")
    else:
        errors.append(f"Invalid plants_workbook_dir type: {type(plants_workbook_dir)}")
        return all_scenario_data, {}, logs, errors

    for wb_source, file_bytes in workbooks:
        plant_name = (
            Path(wb_source).stem if isinstance(wb_source, str)
            else str(wb_source).split('/')[-1].split('.xlsx')[0]
        )
        wb_path = None
        try:
            plant_match = mapping_df.filter(pl.col("DSH plant name") == plant_name)
            if plant_match.is_empty():
                logs.append(f"[WARN] {plant_name} not in mapping")
                continue

            plant_id = plant_match.row(0, named=True)["DSH plant id"]

            if isinstance(plants_workbook_dir, str):
                wb_path = wb_source
            else:
                file_content = file_bytes.read() if hasattr(file_bytes, 'read') else file_bytes
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    tmp.write(file_content)
                    tmp.flush()
                    wb_path = tmp.name

            scenario_df = read_all_scenario_sheets(
                workbook_path=str(wb_path),
                emission_cols=emission_cols,
                energy_cols=energy_cols,
                reference_year=reference_year,
                aggregate_flow_types=aggregate_flow_types,
            )

            plant_details = read_plant_details(str(wb_path))

            if not scenario_df.is_empty():
                all_scenario_data[plant_id] = {
                    "name": plant_name,
                    "df": scenario_df,
                    "mapping_row": plant_match.row(0, named=True),
                    "latitude": plant_details.get("Latitude"),
                    "longitude": plant_details.get("Longitude"),
                }
                logs.append(f"OK {plant_name}: {len(scenario_df)} rows")

                # Production table (optional — FIXED: was unpacking a single
                # DataFrame as a 1-tuple, which always raised and was silently
                # swallowed below. read_production_table returns one DataFrame.)
                try:
                    production_df = read_production_table(workbook_path=str(wb_path))
                    if not production_df.is_empty():
                        all_scenario_data[plant_id]["production_df"] = production_df
                except Exception as e:
                    logs.append(f"  [WARN] No production table for {plant_name}: {e}")

                # Flexibility table (optional, same fix applied)
                # TODO this plant-name check is TEMPORARY
                if plant_name == 'Air Liquide Pernis':
                    try:
                        flexibility_df = read_production_table(workbook_path=str(wb_path), sheet_name='Flexibility')
                        if not flexibility_df.is_empty():
                            flexibility_df = flexibility_df.filter(pl.col('Year').is_not_null())
                            all_scenario_data[plant_id]["flexibility_df"] = flexibility_df
                            logs.append(f"  -> Flexibility table: {len(flexibility_df)} rows")
                    except Exception as e:
                        logs.append(f"  [WARN] No flexibility table for {plant_name}: {e}")

            if not isinstance(plants_workbook_dir, str) and wb_path:
                Path(wb_path).unlink(missing_ok=True)

        except Exception as e:
            errors.append(f"{plant_name}: {e}")
            logs.append(f"[ERROR] {errors[-1]}")

    scenario_year_groups: Dict[Tuple[str, str], list] = {}
    for plant_id, plant_data in all_scenario_data.items():
        for row in plant_data["df"].to_dicts():
            key = (row["Scenario"], str(row["Year"]))
            scenario_year_groups.setdefault(key, []).append((plant_id, row))

    logs.append(f"Grouped into {len(scenario_year_groups)} scenario-year combos")
    return all_scenario_data, scenario_year_groups, logs, errors


# ═══════════════════════════════════════════════════════════════════════
# Part 3: Group -> per-plant inputs (regular / bottom-up / new sites)
# ═══════════════════════════════════════════════════════════════════════

def build_ctm_inputs_from_plants(
    plants_in_group: List[Tuple[str, dict]],
    all_scenario_data: Dict,
    emission_cols: List[str],
    energy_cols: List[str],
    flow_type: str,
    transformation_overrides: Optional[dict] = None,
) -> Tuple[Dict, List]:
    """Map one flow-type's worth of plant rows to CTM inputs, keyed by mapping type."""
    logs = []
    inputs = {}

    for plant_id, row_data in plants_in_group:
        plant_info = all_scenario_data[plant_id]
        mapping_row = plant_info["mapping_row"]
        plant_name = plant_info["name"]

        is_bottom_up = mapping_row["Bottom-up"]
        is_new = mapping_row["New site"]
        ctm_sector = mapping_row["Sector"]
        ctm_cluster = mapping_row["Cluster"]
        ctm_api_name = mapping_row["API input name"]

        try:
            if is_bottom_up:
                site_name = ctm_api_name.split("&&")[0]
                transformation = (transformation_overrides or {}).get(ctm_api_name)
                plant_inputs = construct_bottom_up_inputs(
                    sector=ctm_sector, cluster=ctm_cluster, site=site_name,
                    row_data=row_data, emission_cols=emission_cols, energy_cols=energy_cols,
                    flow_type=flow_type, logs=logs, transformation=transformation,
                )
                inputs.update(plant_inputs)

            elif is_new:
                latitude = str(plant_info.get("latitude"))
                longitude = str(plant_info.get("longitude"))
                custom_site = ctm_api_name.split("&&")[0]
                plant_inputs = construct_custom_site_inputs(
                    sector=ctm_sector, cluster=ctm_cluster, custom_site=custom_site,
                    row_data=row_data, emission_cols=emission_cols, energy_cols=energy_cols,
                    flow_type=flow_type, logs=logs, latitude=latitude, longitude=longitude,
                )
                inputs.update(plant_inputs)

            else:
                parts = ctm_api_name.split("&&")
                if len(parts) >= 3:
                    sector, cluster, site = parts[0], parts[1], parts[2]
                    transformation = (transformation_overrides or {}).get(ctm_api_name)
                    plant_inputs = construct_site_inputs(
                        sector=sector, cluster=cluster, site=site,
                        row_data=row_data, emission_cols=emission_cols, energy_cols=energy_cols,
                        flow_type=flow_type, logs=logs, transformation=transformation,
                    )
                    inputs.update(plant_inputs)

        except Exception as e:
            logs.append(f"[ERROR] {plant_name}: {e}")

    return inputs, logs


# ═══════════════════════════════════════════════════════════════════════
# Part 4: Cluster/sector demand curves -> ##new_cc_siteN## / pseudo-site inputs
# (for demand not tied to any specific DSH plant)
# ═══════════════════════════════════════════════════════════════════════

def build_sector_cluster_sites(cluster_sector_data: pl.DataFrame) -> Tuple[Dict, List]:
    """
    Map aggregated cluster/sector demand curves to CTM inputs, as a pseudo-site
    named 'cluster_site_{sector}_{cluster}' (or 'sector_site_{sector}' for
    cluster_6). Expects columns: Cluster, Sector, Scenario, Year, Value,
    Utility, Flow type (the shape produced by curves_utils.get_final_cluster_sector_curves).
    """
    logs = []
    inputs = {}
    sector = cluster = None

    for row in cluster_sector_data.to_dicts():
        sector = row.get("Sector").lower().replace('-', '_').replace(' ', '_')
        cluster = row.get("Cluster").lower().replace('-', '_').replace(' ', '_')
        utility = row.get("Utility").lower().replace('-', '_').replace(' ', '_')
        flow_type = row.get("Flow type", "demand").lower()
        value = row.get("Value")

        if not all([sector, cluster, utility, flow_type, value is not None]):
            continue

        input_key = f'sector_site_{sector}' if cluster == 'cluster_6' else f'cluster_site_{sector}_{cluster}'

        if value != 0:
            inputs[f"{sector}&&{cluster}&&{input_key}&&enabled"] = '1'
            inputs[f"{sector}&&{cluster}&&{input_key}&&{utility}_{flow_type}"] = str(value)

    if sector:
        logs.append(f"Cluster-sector: {sector}/{cluster} = {len(inputs)} inputs")
    return inputs, logs


def build_sector_cluster_sites_EXTRA(cluster_sector_data: pl.DataFrame, mapping: pl.DataFrame) -> Tuple[Dict, List]:
    """Same as build_sector_cluster_sites, but for refineries/steel only, mapped to a specific site number."""
    logs = []
    inputs = {}
    sector = cluster = None
    mapping_subset = mapping.filter(pl.col('DSH plant id') == '1')

    for row in cluster_sector_data.to_dicts():
        sector = row.get("Sector").lower().replace('-', '_').replace(' ', '_')
        cluster = row.get("Cluster").lower().replace('-', '_').replace(' ', '_')
        utility = row.get("Utility").lower().replace('-', '_').replace(' ', '_')
        flow_type = row.get("Flow type", "demand").lower()
        value = row.get("Value")

        if not all([sector, cluster, utility, flow_type, value is not None]):
            continue

        result = mapping_subset.filter(
            (pl.col('Sector').str.to_lowercase() == sector) & (pl.col('Cluster').str.to_lowercase() == cluster)
        ).select(pl.col('Name reformatted'))

        if result.is_empty():
            logs.append(f"[SKIP] No mapping for {sector}/{cluster}")
            continue

        site_number = result.item()

        if value != 0:
            inputs[f"{site_number}&&enabled"] = '1'
            inputs[f"{site_number}&&cluster"] = cluster
            inputs[f"{site_number}&&sector"] = sector
            inputs[f"{site_number}&&{utility}_{flow_type}"] = str(value)

    if sector:
        logs.append(f"Cluster-sector (extra): {sector}/{cluster} = {len(inputs)} inputs")
    return inputs, logs


# ═══════════════════════════════════════════════════════════════════════
# Part 5: Production (CHP) and flexibility table inputs
# ═══════════════════════════════════════════════════════════════════════

def build_ctm_inputs_from_production(
    sector: str,
    cluster: str,
    site: Optional[str],
    production_df: pl.DataFrame,
    is_bottom_up: bool = False,
    is_custom: bool = False,
    is_sector_cluster: bool = False,
) -> Tuple[Dict, List]:
    """
    Map a plant's Production sheet (Capacity, FLH, efficiencies) to CHP CTM inputs.
    Expects columns: Scenario, Year, Capacity, FLH, Efficiency electricity, Efficiency heat.
    """
    logs = []
    inputs = {}
    cluster = fix_string(cluster)
    sector = fix_string(sector)

    column_map = {
        "Capacity": "chp_capacity",
        "FLH": "chp_flh",
        "Efficiency electricity": "chp_electrical_efficiency",
        "Efficiency heat": "chp_thermal_efficiency",
    }

    for row in production_df.to_dicts():
        scenario = row.get("Scenario")
        year = str(row.get("Year"))

        for dsh_col, ctm_col in column_map.items():
            value = row.get(dsh_col)
            if value is None:
                continue
            try:
                val_float = float(value)
                if val_float <= 0:
                    continue

                if 'efficiency' in dsh_col.lower() and val_float > 1:
                    val_float /= 100

                if is_bottom_up or is_custom:
                    ctm_key = f"{site}&&{ctm_col}"
                elif is_sector_cluster:
                    ctm_key = f"{sector}&&{cluster}&&cluster&&{ctm_col}"
                else:
                    ctm_key = f"{sector}&&{cluster}&&{site}&&{ctm_col}"

                inputs[ctm_key] = str(val_float)

            except (ValueError, TypeError):
                logs.append(f"  [SKIP] {scenario}/{year} {ctm_col}: invalid value {value}")

    return inputs, logs


def build_ctm_inputs_from_flexibility(
    flexibility_df: pl.DataFrame,
    scenario: str,
    year: str,
    logs: Optional[list] = None,
) -> Tuple[Dict, List]:
    """
    Map a plant's Flexibility sheet to CTM inputs. Not tied to any site — these
    are global "additional CHP capacity" inputs.
    """
    if logs is None:
        logs = []
    inputs = {}

    filtered = flexibility_df.filter((pl.col("Scenario") == scenario) & (pl.col("Year") == str(year)))
    if filtered.is_empty():
        return inputs, logs

    column_map = {
        "Capacity": "additional_chp_capacity_additional_chp_capacity_input",
        "Efficiency electricity": "additional_chp_capacity_chp_electrical_efficiency_input",
        "Efficiency heat": "additional_chp_capacity_chp_thermal_efficiency_input",
    }

    for row in filtered.to_dicts():
        for dsh_col, ctm_col in column_map.items():
            value = row.get(dsh_col)
            if value is None or value == 0:
                continue
            try:
                val_float = float(value)
                if val_float == 0:
                    continue
                inputs[ctm_col] = str(val_float)
            except (ValueError, TypeError):
                logs.append(f"    [SKIP] Flexibility {ctm_col}: invalid value {value}")

    logs.append(f"    Flexibility: {len(inputs)} inputs")
    return inputs, logs


# ═══════════════════════════════════════════════════════════════════════
# Part 6: Per-(scenario, year) processing — plants + production + flexibility
# ═══════════════════════════════════════════════════════════════════════

def _build_production_for_plant(
    plant_info: dict,
    mapping_row: dict,
    production_df: pl.DataFrame,
    logs: list,
) -> Tuple[Dict, List]:
    """Build production/CHP inputs for a single plant, dispatching on site type."""
    inputs = {}
    is_bottom_up = mapping_row["Bottom-up"]
    is_new = mapping_row["New site"]
    ctm_sector = fix_string(mapping_row["Sector"])
    ctm_cluster = fix_string(mapping_row["Cluster"])
    ctm_api_name = mapping_row["API input name"]

    try:
        if is_bottom_up:
            site_name = ctm_api_name.split("&&")[0]
            prod_inputs, prod_logs = build_ctm_inputs_from_production(
                sector=ctm_sector, cluster=ctm_cluster, site=site_name,
                production_df=production_df, is_bottom_up=True,
            )
        elif is_new:
            custom_site = ctm_api_name.split("&&")[0]
            prod_inputs, prod_logs = build_ctm_inputs_from_production(
                sector=ctm_sector, cluster=ctm_cluster, site=custom_site,
                production_df=production_df, is_custom=True,
            )
        else:
            parts = ctm_api_name.split("&&")
            if len(parts) < 3:
                return inputs, logs
            sector, cluster, site = parts[0], parts[1], parts[2]
            prod_inputs, prod_logs = build_ctm_inputs_from_production(
                sector=sector, cluster=cluster, site=site, production_df=production_df,
            )

        inputs.update(prod_inputs)
        logs.extend(prod_logs)

    except Exception as e:
        logs.append(f"  [ERROR] Production for {plant_info['name']}: {e}")

    return inputs, logs


def process_plants_for_scenario_year(
    scenario: str,
    year: str,
    plants_in_year: List[Tuple[str, dict]],
    all_scenario_data: Dict,
    emission_cols: list,
    energy_cols: list,
    transformation_overrides: Optional[dict] = None,
) -> Tuple[Dict, List]:
    """
    Build all inputs for one scenario/year: plant demand+production rows,
    plus each unique plant's production and flexibility tables (once each).
    """
    logs = []
    all_inputs = {}
    processed_plants = set()

    by_flow_type: Dict[str, list] = {}
    for plant_id, row in plants_in_year:
        by_flow_type.setdefault(row.get("Flow type", "").lower(), []).append((plant_id, row))

    for flow_type, plants_for_flow in by_flow_type.items():
        plant_inputs, step_logs = build_ctm_inputs_from_plants(
            plants_in_group=plants_for_flow,
            all_scenario_data=all_scenario_data,
            emission_cols=emission_cols,
            energy_cols=energy_cols,
            flow_type=flow_type,
            transformation_overrides=transformation_overrides,
        )
        all_inputs.update(plant_inputs)
        logs.extend(step_logs)

    for plant_id, row in plants_in_year:
        if plant_id in processed_plants:
            continue
        processed_plants.add(plant_id)

        plant_info = all_scenario_data[plant_id]
        if "production_df" not in plant_info:
            continue

        filtered_prod = plant_info["production_df"].filter(
            (pl.col("Scenario") == scenario) & (pl.col("Year") == year)
        )
        if filtered_prod.is_empty():
            continue

        prod_inputs, logs = _build_production_for_plant(
            plant_info=plant_info,
            mapping_row=plant_info["mapping_row"],
            production_df=filtered_prod,
            logs=logs,
        )
        all_inputs.update(prod_inputs)

    for plant_id in processed_plants:
        plant_info = all_scenario_data[plant_id]
        if "flexibility_df" not in plant_info:
            continue

        flex_inputs, flex_logs = build_ctm_inputs_from_flexibility(
            flexibility_df=plant_info["flexibility_df"], scenario=scenario, year=year, logs=logs,
        )
        all_inputs.update(flex_inputs)
        logs.extend(flex_logs)

    return all_inputs, logs


# ═══════════════════════════════════════════════════════════════════════
# Part 7: Main orchestrator
# ═══════════════════════════════════════════════════════════════════════

def push_aggregated_by_scenario_year(
    plants_workbook_dir: str | list,
    mapping_df: pl.DataFrame,
    emission_cols: list = EMISSION_COLS_ORDER,
    energy_cols: list = UTILITY_COLS_ORDER,
    cluster_sector_file: Optional[str] | pl.DataFrame = None,
    cluster_sector_production_sheet_name: Optional[str] = None,
    cluster_sector_curves_sheet_name: Optional[str] = None,
    cluster_sector_production: Optional[pl.DataFrame] = None,
    reference_year: int = REFERENCE_YEAR,
    use_beta: bool = True,
    transformation_overrides: Optional[dict] = None,
    output_log_file: Optional[str] = None,
    reuse_sessions: Optional[Dict[Tuple[str, str], str]] = None,
    selected_scenarios: Optional[List[str]] = None,
    selected_years: Optional[List[str]] = None,
    session_path: Optional[str] = None,
    extra_inputs: Optional[Dict[str, str]] = None,
    log_container=None,
    only_load_scenario_data: bool = False,
) -> dict:
    """
    Main workflow: load plants, group by scenario-year, build inputs, push to CTM.

    `session_path`: if given, dumps each scenario/year's pushed inputs as JSON
    into this folder — useful for debugging a specific push. Left as None,
    nothing is written to disk (previously this wrote to the CWD unconditionally
    on every push — fixed while merging, see module docstring).

    Returns:
        {"logs", "sessions": {(scenario, year): session_id}, "scenario_data",
         "curves_data", "sector_cluster_prod_data", "total_plants",
         "total_scenario_years", "errors"}
    """
    all_logs: List[str] = []
    all_errors: List[str] = []
    sessions_created: Dict[Tuple[str, str], str] = {}
    extra_inputs = extra_inputs or {}
    selected_scenarios = selected_scenarios if selected_scenarios is not None else ALL_SCENARIOS
    selected_years = selected_years if selected_years is not None else SCENARIO_YEARS

    def log_message(msg):
        all_logs.append(msg)
        if log_container:
            log_container.write(msg)

    custom_inputs = get_custom_ctm_inputs()

    log_message("STEP 1: Loading plants...")
    all_scenario_data, scenario_year_groups, step_logs, step_errors = load_all_plants_scenario_data(
        plants_workbook_dir=plants_workbook_dir,
        mapping_df=mapping_df,
        emission_cols=emission_cols,
        energy_cols=energy_cols,
        reference_year=reference_year,
    )

    if only_load_scenario_data:
        return {"data": all_scenario_data}

    all_logs.extend(step_logs)
    all_errors.extend(step_errors)

    if not all_scenario_data:
        log_message("[ERROR] No plants loaded")
        return {
            "logs": all_logs, "sessions": {}, "total_plants": 0,
            "total_scenario_years": 0, "errors": all_errors,
        }

    # Cluster/sector demand curves (feed new/pseudo sites — see Part 4)
    cluster_sector_df_long = None
    cluster_sector_df_long_EXTRA = None
    cluster_sector_df_long_init = None
    sector_cluster_prod_df = None

    if cluster_sector_file is not None:
        try:
            log_message("STEP 1B: Loading and reshaping cluster/sector curves...")
            if isinstance(cluster_sector_file, str):
                cluster_sector_df_long_init = get_final_cluster_sector_curves(
                    excel_path=cluster_sector_file, sheet_name=cluster_sector_curves_sheet_name, years=SCENARIO_YEARS,
                )
            else:
                cluster_sector_df_long_init = get_final_cluster_sector_curves(
                    curves_df=cluster_sector_file, years=SCENARIO_YEARS,
                )

            cluster_sector_df_long = cluster_sector_df_long_init.filter(~pl.col('Sector').is_in(['refineries', 'steel']))
            cluster_sector_df_long_EXTRA = cluster_sector_df_long_init.filter(pl.col('Sector').is_in(['refineries', 'steel']))
            log_message(f"  OK Reshaped cluster/sector data: {len(cluster_sector_df_long)} rows")
        except Exception as e:
            log_message(f"[ERROR] Failed to load cluster-sector data: {e}")
            all_errors.append(str(e))

        try:
            log_message("STEP 1C: Loading cluster/sector production curves...")
            if cluster_sector_production is None:
                sector_cluster_prod_df = read_production_table_curves(
                    workbook_path=cluster_sector_file, sheet_name=cluster_sector_production_sheet_name,
                )
            else:
                sector_cluster_prod_df = read_production_table_curves(curves_df=cluster_sector_production)
            log_message(f"  OK Production cluster/sector data: {len(sector_cluster_prod_df)} rows")
        except Exception as e:
            log_message(f"[ERROR] Failed to load cluster-sector production data: {e}")
            all_errors.append(str(e))

    num_scenarios = len(selected_scenarios) * len(selected_years)
    log_message(f"STEP 2: Processing up to {num_scenarios} scenario-year combos...")

    dict_all_inputs = {}

    for (scenario, year), plants_in_year in sorted(scenario_year_groups.items()):
        if scenario not in selected_scenarios or year not in selected_years:
            continue

        scenario_key = (scenario, year)
        log_message(f"[{scenario} / {year}] - {len(plants_in_year)} plant-records")

        reuse_sid = (reuse_sessions or {}).get(scenario_key)

        try:
            ctm = CTMClient(use_beta=use_beta)
            if reuse_sid:
                ctm.load_session(reuse_sid)
                log_message(f"  Reusing session: {reuse_sid}")
            else:
                reuse_sid = ctm.create_clean_sheet_session()
                log_message(f"  Created session: {reuse_sid}")
        except Exception as e:
            log_message(f"  [ERROR] {e}")
            all_errors.append(str(e))
            continue

        all_inputs, step_logs = process_plants_for_scenario_year(
            scenario=scenario, year=year, plants_in_year=plants_in_year,
            all_scenario_data=all_scenario_data, emission_cols=emission_cols,
            energy_cols=energy_cols, transformation_overrides=transformation_overrides,
        )
        all_logs.extend(step_logs)

        if cluster_sector_df_long is not None:
            try:
                filtered = cluster_sector_df_long.filter(
                    (pl.col("Scenario").str.to_lowercase() == scenario.lower()) & (pl.col("Year") == year)
                )
                if not filtered.is_empty():
                    cluster_inputs, cluster_logs = build_sector_cluster_sites(cluster_sector_data=filtered)
                    all_inputs.update(cluster_inputs)
                    all_logs.extend(cluster_logs)
            except Exception as e:
                log_message(f"[ERROR] Cluster/sector: {e}")

        if cluster_sector_df_long_EXTRA is not None:
            try:
                filtered = cluster_sector_df_long_EXTRA.filter(
                    (pl.col("Scenario").str.to_lowercase() == scenario.lower()) & (pl.col("Year") == year)
                )
                if not filtered.is_empty():
                    cluster_inputs, cluster_logs = build_sector_cluster_sites_EXTRA(
                        cluster_sector_data=filtered, mapping=mapping_df,
                    )
                    all_inputs.update(cluster_inputs)
                    all_logs.extend(cluster_logs)
            except Exception as e:
                log_message(f"[ERROR] Cluster/sector (extra): {e}")

        if sector_cluster_prod_df is not None:
            filtered_prod = sector_cluster_prod_df.filter(
                (pl.col("Scenario") == scenario) & (pl.col("Year") == year)
            )
            if not filtered_prod.is_empty():
                for row in filtered_prod.to_dicts():
                    prod_inputs, prod_logs = build_ctm_inputs_from_production(
                        sector=row["Sector"], cluster=row["Cluster"], site=None,
                        production_df=pl.DataFrame(row), is_sector_cluster=True,
                    )
                    all_inputs.update(prod_inputs)
                    all_logs.extend(prod_logs)

        all_inputs.update(custom_inputs)
        log_message(f"Added {len(custom_inputs)} custom inputs")

        if extra_inputs:
            all_inputs.update(extra_inputs)

        if all_inputs and len(all_inputs) > 1:
            try:
                ctm.set_inputs(all_inputs)
                sessions_created[scenario_key] = reuse_sid
                log_message(f"  Pushed {len(all_inputs)} total inputs")
                dict_all_inputs[(scenario, year)] = all_inputs
            except Exception as e:
                all_errors.append(f"Failed to push: {e}")
                log_message(f"  [ERROR] {e}")
        else:
            log_message("  [SKIP] No valid inputs")

        if session_path:
            inputs_path = Path(session_path)
            inputs_path.mkdir(parents=True, exist_ok=True)
            with open(inputs_path / f'inputs_{scenario}_{year}.json', "w") as f:
                json.dump(all_inputs, f, indent=4)

    log_message("SUMMARY:")
    log_message(f"  Plants loaded: {len(all_scenario_data)}")
    log_message(f"  Scenario-year combos: {len(scenario_year_groups)}")
    log_message(f"  Sessions created: {len(sessions_created)}")
    log_message(f"  Errors: {len(all_errors)}")

    if output_log_file:
        with open(output_log_file, "w") as f:
            f.write("\n".join(all_logs))
        all_logs.append(f"Log written to {output_log_file}")

    return {
        "logs": all_logs,
        "sessions": sessions_created,
        "scenario_data": all_scenario_data,
        "all_inputs": dict_all_inputs,
        "curves_data": cluster_sector_df_long_init,
        "sector_cluster_prod_data": sector_cluster_prod_df,
        "total_plants": len(all_scenario_data),
        "total_scenario_years": len(scenario_year_groups),
        "errors": all_errors,
    }


def write_push_logs(result: dict, output_dir: str = "./push_logs") -> dict:
    """
    Write push logs/sessions/errors/summary to a timestamped folder. Intended
    for local/notebook use — the Streamlit app downloads these via buttons
    instead, so this isn't wired into the UI.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = Path(output_dir) / f"run_{timestamp}"
    run_folder.mkdir(parents=True, exist_ok=True)

    files = {}

    logs_file = run_folder / "logs.txt"
    with open(logs_file, "w") as f:
        f.write("\n".join(result.get("logs", [])))
    files["logs_file"] = str(logs_file)

    sessions_file = run_folder / "sessions.txt"
    with open(sessions_file, "w") as f:
        f.write("SESSIONS CREATED\n" + "=" * 70 + "\n\n")
        if result.get("sessions"):
            for (scenario, year), session_id in result["sessions"].items():
                f.write(f"{scenario} / {year}\n  Session ID: {session_id}\n\n")
        else:
            f.write("No sessions created.\n")
    files["sessions_file"] = str(sessions_file)

    errors_file = run_folder / "errors.txt"
    with open(errors_file, "w") as f:
        f.write("ERRORS\n" + "=" * 70 + "\n\n")
        if result.get("errors"):
            for i, error in enumerate(result["errors"], 1):
                f.write(f"{i}. {error}\n\n")
        else:
            f.write("No errors.\n")
    files["errors_file"] = str(errors_file)

    summary_file = run_folder / "summary.txt"
    with open(summary_file, "w") as f:
        f.write("PUSH SUMMARY\n" + "=" * 70 + "\n\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Total plants: {result.get('total_plants', 0)}\n")
        f.write(f"Scenario-year combos: {result.get('total_scenario_years', 0)}\n")
        f.write(f"Sessions created: {len(result.get('sessions', {}))}\n")
        f.write(f"Errors: {len(result.get('errors', []))}\n")
    files["summary_file"] = str(summary_file)

    files["folder"] = str(run_folder)
    return files