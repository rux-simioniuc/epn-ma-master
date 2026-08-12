import polars as pl
from typing import Optional
from .ctm_client import CTMClient
from .read_DSH_files import read_all_scenario_sheets
from .utils import fix_string
from .ctm_constants import (
    CTM_ENERGY_COLUMN_MAP,
    get_valid_ctm_inputs,
    get_valid_ctm_inputs_bottom_up,
    get_valid_ctm_inputs_custom,
    get_valid_ctm_inputs_cluster,
    get_valid_ctm_inputs_sector,
)

# ── Sector -> transformation mapping ────────────────────────────────────────
ALWAYS_TRANSFORMATION_SECTORS = {'methanol', 'ammonia', 'waste'}

def infer_transformation(sector: str) -> str:
    """Infer transformation flag from sector. Default to 0 (final demand)."""
    if sector.lower() in ALWAYS_TRANSFORMATION_SECTORS:
        return "1"
    return "0"


def energy_column_name(dsh_col: str, flow_type: str) -> Optional[str]:
    """
    Map DSH energy column to CTM input column.
    Returns None if no valid mapping exists.
    """
    # Try direct mapping first
    if dsh_col in CTM_ENERGY_COLUMN_MAP:
        ctm_base = CTM_ENERGY_COLUMN_MAP[dsh_col]
        return f"{ctm_base}_{flow_type}"
    
    # Try normalized name (lowercase, spaces->underscores)
    normalized = dsh_col.lower().replace(" ", "_").replace("(", "").replace(")", "")
    if normalized in CTM_ENERGY_COLUMN_MAP:
        ctm_base = CTM_ENERGY_COLUMN_MAP[normalized]
        return f"{ctm_base}_{flow_type}"
    
    return None


def emission_column_name(dsh_col: str) -> str:
    """Map DSH emission column to CTM input column (production only)."""
    col_map = {
        "CO2": "co2_emissions_production",
        "Methane": "methane_emissions_production",
        "N2O": "n2o_emissions_production",
        "F-gases": "f_gas_emissions_production",
    }
    return col_map.get(dsh_col, None)


def construct_site_inputs(
    sector: str,
    cluster: str,
    site: str,
    row_data: dict,
    emission_cols: list[str],
    energy_cols: list[str],
    flow_type: str,
    logs: list,
    transformation: Optional[str] = None,
) -> dict:
    """Construct CTM input dict for a regular site (sector/cluster/site hierarchy)."""
 
    sector = fix_string(sector)
    cluster = fix_string(cluster)
 
    inputs = {
        f"{sector}&&{cluster}&&{site}&&enabled": "1",
    }
    
    trans_flag = transformation or infer_transformation(sector)
    inputs[f"{sector}&&{cluster}&&{site}&&transformation"] = trans_flag
    
    # Energy columns
    for col in energy_cols:
        if 'peak' not in col:
            val = row_data.get(col)
            if val is not None and val != 0:  # Skip 0 and None
                # if val < 0:
                #     logs.append(f"    [SKIP NEG] {col}={val}")
                #     continue
                ctm_col = energy_column_name(col, flow_type)
                if ctm_col is None:
                    # logs.append(f"    [SKIP UNMAPPED] {col} (no CTM mapping)")
                    continue
                inputs[f"{sector}&&{cluster}&&{site}&&{ctm_col}"] = str(val)
    
    # Emission columns (production only)
    if flow_type == "production":
        for col in emission_cols:
            val = row_data.get(col)
            if val is not None and val != 0:  # ← Skip 0 and None
                # if val < 0:
                #     logs.append(f"    [SKIP NEG] {col}={val}")
                #     continue
                ctm_col = emission_column_name(col)
                if ctm_col:
                    inputs[f"{sector}&&{cluster}&&{site}&&{ctm_col}"] = str(val)
    
    # # LDSH peak electricity (if Electricity_peak exists and != 0)
    # if "Electricity_peak" in row_data:
    #     val = row_data.get("Electricity_peak")
    #     if val is not None and val != 0:  # only if not 0
    #         if flow_type == "demand":
    #             inputs[f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_demand_future"] = str(val)
    #         elif flow_type == "production":
    #             inputs[f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_production_future"] = str(val)
    
    # Validate inputs against CTM schema
    valid_keys = get_valid_ctm_inputs(sector, cluster, site)
    inputs = validate_and_filter_inputs(inputs, valid_keys, logs)
    
    return inputs


def construct_bottom_up_inputs(
    sector: str,
    cluster: str,
    site: str,
    row_data: dict,
    emission_cols: list[str],
    energy_cols: list[str],
    flow_type: str,
    logs: list,
    transformation: Optional[str] = None,
) -> dict:
    """Construct CTM input dict for a bottom-up site (flat pattern)."""
    
    inputs = {f"{site}&&enabled": "1"}
 
    sector = fix_string(sector)
    cluster = fix_string(cluster)
 
    if transformation:
        inputs[f"{site}&&transformation"] = transformation
    
    # Energy columns
    for col in energy_cols:
        if 'peak' not in col:
            val = row_data.get(col)
            if val is not None and val != 0:  # Skip 0 and None
                # if val < 0:
                #     logs.append(f"    [SKIP NEG] {col}={val}")
                #     continue
                ctm_col = energy_column_name(col, flow_type)
                if ctm_col is None:
                    # logs.append(f"    [SKIP UNMAPPED] {col} (no CTM mapping)")
                    continue
                inputs[f"{site}&&{ctm_col}"] = str(val)
    
    # Emission columns (production only)
    if flow_type == "production":
        for col in emission_cols:
            val = row_data.get(col)
            if val is not None and val != 0:  # Skip 0 and None
                # if val < 0:
                #     logs.append(f"    [SKIP NEG] {col}={val}")
                #     continue
                ctm_col = emission_column_name(col)
                if ctm_col:
                    inputs[f"{site}&&{ctm_col}"] = str(val)
    
    '''Note: Electricity peak is deprecated in CTM; no longer using this input'''
    
    # LDSH peak electricity (flat format for bottom-up)
    # if "Electricity_peak" in row_data:
    #     val = row_data.get("Electricity_peak")
    #     if val is not None and val != 0:  
    #         if flow_type == "demand":
    #             inputs[f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_demand_future"] = str(val)
    #         elif flow_type == "production":
    #             inputs[f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_production_future"] = str(val)
    
    # Validate inputs
    valid_keys = get_valid_ctm_inputs_bottom_up(sector, cluster, site)
    inputs = validate_and_filter_inputs(inputs, valid_keys, logs)
    
    return inputs
 
 
def construct_custom_site_inputs(
    sector: str,
    cluster: str,
    custom_site: str,
    row_data: dict,
    emission_cols: list[str],
    energy_cols: list[str],
    flow_type: str,
    logs: list,
    latitude: float = None,      
    longitude: float = None,
) -> dict:
    """Construct CTM input dict for a custom site (flat pattern)."""
 
    sector = fix_string(sector)
    cluster = fix_string(cluster)
 
    inputs = {f"{custom_site}&&enabled": "1"}

    # Add sector, cluster, location for new sites
    if sector:
        inputs[f"{custom_site}&&sector"] = sector
    if cluster:
        inputs[f"{custom_site}&&cluster"] = cluster
    if latitude is not None:
        inputs[f"{custom_site}&&latitude"] = str(latitude)
    if longitude is not None:
        inputs[f"{custom_site}&&longitude"] = str(longitude)
    
    # Energy columns
    for col in energy_cols:
        if 'peak' not in col:
            val = row_data.get(col)
            if val is not None and val != 0:  # Skip 0 and None
                # if val < 0:
                #     logs.append(f"    [SKIP NEG] {col}={val}")
                #     continue
                ctm_col = energy_column_name(col, flow_type)
                if ctm_col is None:
                    # logs.append(f"    [SKIP UNMAPPED] {col} (no CTM mapping)")
                    continue
                inputs[f"{custom_site}&&{ctm_col}"] = str(val)
        
    # Emission columns (production only)
    if flow_type == "production":
        for col in emission_cols:
            val = row_data.get(col)
            if val is not None and val != 0:  # Skip 0 and None
                # if val < 0:
                #     logs.append(f"    [SKIP NEG] {col}={val}")
                #     continue
                ctm_col = emission_column_name(col)
                if ctm_col:
                    inputs[f"{custom_site}&&{ctm_col}"] = str(val)
    
    # # LDSH peak electricity (flat format for custom sites)
    # if "Electricity_peak" in row_data:
    #     val = row_data.get("Electricity_peak")
    #     if val is not None and val != 0:  
    #         if flow_type == "demand":
    #             inputs[f"ldsh&&{custom_site}&&{CTM_LDSH_PEAK_ELECTRICITY}_demand_future"] = str(val)
    #         elif flow_type == "production":
    #             inputs[f"ldsh&&{custom_site}&&{CTM_LDSH_PEAK_ELECTRICITY}_production_future"] = str(val)
    
    # Validate inputs
    valid_keys = get_valid_ctm_inputs_custom(sector, cluster, custom_site)
    inputs = validate_and_filter_inputs(inputs, valid_keys, logs)
    
    return inputs

def construct_cluster_inputs(
    sector: str,
    cluster: str,
    cluster_data: dict,  # {utility: value, ...}
    emission_cols: list[str],
    energy_cols: list[str],
    flow_type: str,
    logs: list,
) -> dict:
    """
    Construct CTM input dict for a cluster.
    
    cluster_data: dict of {utility_name: value}
    Flow type is either "demand" or "production"
    """
    
    inputs = {
        f"{sector}&&{cluster}&&cluster&&enabled": "1",
    }
    
    # Map utilities to CTM inputs
    for utility, value in cluster_data.items():
        # if value is None or value < 0:
            # if value is not None and value < 0:
            #     logs.append(f"    [SKIP NEG] {cluster}/{utility}/{flow_type}={value}")
            # continue
        
        # Find CTM column name for this utility
        ctm_col = None
        
        # Try direct match
        if utility in CTM_ENERGY_COLUMN_MAP:
            ctm_col = CTM_ENERGY_COLUMN_MAP[utility]
        else:
            # Try normalized
            normalized = utility.lower().replace(" ", "_").replace("(", "").replace(")", "")
            if normalized in CTM_ENERGY_COLUMN_MAP:
                ctm_col = CTM_ENERGY_COLUMN_MAP[normalized]
        
        if ctm_col is None:
            logs.append(f"    [SKIP UNMAPPED] {utility} (no CTM mapping)")
            continue
        
        # Build CTM key: sector&&cluster&&cluster&&utility_flowtype
        ctm_key = f"{sector}&&{cluster}&&cluster&&{ctm_col}_{flow_type}"
        inputs[ctm_key] = str(value)
    
    # Validate inputs
    valid_keys = get_valid_ctm_inputs_cluster(sector, cluster)
    inputs = validate_and_filter_inputs(inputs, valid_keys, logs)
    
    return inputs


def construct_sector_inputs(
    sector: str,
    sector_data: dict,  # {utility: value, ...}
    emission_cols: list[str],
    energy_cols: list[str],
    flow_type: str,
    logs: list,
) -> dict:
    """
    Construct CTM input dict for a sector.
    
    sector_data: dict of {utility_name: value}
    Flow type is either "demand" or "production"
    """
    
    inputs = {
        f"{sector}&&sector&&enabled": "1",
    }
    
    # Map utilities to CTM inputs
    for utility, value in sector_data.items():
        # if value is None or value < 0:
        #     if value is not None and value < 0:
        #         logs.append(f"    [SKIP NEG] {sector}/{utility}/{flow_type}={value}")
        #     continue
        
        # Find CTM column name for this utility
        ctm_col = None
        
        # Try direct match
        if utility in CTM_ENERGY_COLUMN_MAP:
            ctm_col = CTM_ENERGY_COLUMN_MAP[utility]
        else:
            # Try normalized
            normalized = utility.lower().replace(" ", "_").replace("(", "").replace(")", "")
            if normalized in CTM_ENERGY_COLUMN_MAP:
                ctm_col = CTM_ENERGY_COLUMN_MAP[normalized]
        
        if ctm_col is None:
            logs.append(f"    [SKIP UNMAPPED] {utility} (no CTM mapping)")
            continue
        
        # Build CTM key: sector&&sector&&utility_flowtype
        ctm_key = f"{sector}&&sector&&{ctm_col}_{flow_type}"
        inputs[ctm_key] = str(value)
    
    # Validate inputs
    valid_keys = get_valid_ctm_inputs_sector(sector)
    inputs = validate_and_filter_inputs(inputs, valid_keys, logs)
    
    return inputs


def push_plant_to_ctm(
    plant_id: str,
    plant_name: str,
    workbook_path: str,
    mapping_df: pl.DataFrame,
    emission_cols: list[str],
    energy_cols: list[str],
    reference_year: int = 2024,
    use_beta: bool = False,
    transformation_overrides: dict = None,
    valid_energy_cols: list[str] = None,
) -> dict:
    """
    Push a plant's modified scenario data to CTM.
    Uses ONE reusable session for all scenario/year/flow type combos.
    """
    
    logs = []
    errors = []
    custom_sites_used = {}
    total_inputs = 0
    scenarios_pushed = {}
    
    logs.append(f"\n{'='*70}")
    logs.append(f"Plant: {plant_name} ({plant_id})")
    logs.append(f"{'='*70}")
    
    # Filter energy columns to valid ones
    if valid_energy_cols:
        energy_cols_filtered = [c for c in energy_cols if c in valid_energy_cols]
        if len(energy_cols_filtered) < len(energy_cols):
            logs.append(f"[INFO] Filtered {len(energy_cols)} -> {len(energy_cols_filtered)} valid energy cols")
            energy_cols = energy_cols_filtered
    
    # Load scenario data
    try:
        scenario_df = read_all_scenario_sheets(
            workbook_path=workbook_path,
            emission_cols=emission_cols,
            energy_cols=energy_cols,
            reference_year=reference_year,
            aggregate_flow_types=True,
        )
        if scenario_df.is_empty():
            logs.append("[WARN] No scenario data in workbook")
            return {
                "logs": logs,
                "scenarios": {},
                "custom_sites_used": [],
                "total_inputs_pushed": 0,
                "errors": [],
            }
    except Exception as e:
        errors.append(f"Failed to read scenario sheets: {e}")
        logs.append(f"[ERROR] {errors[-1]}")
        return {
            "logs": logs,
            "scenarios": {},
            "custom_sites_used": [],
            "total_inputs_pushed": 0,
            "errors": errors,
        }
    
    logs.append(f"Loaded {len(scenario_df)} rows")
    
    # Find plant in mapping
    plant_mapping = mapping_df.filter(pl.col("DSH plant id") == plant_id)
    
    if plant_mapping.is_empty():
        logs.append(f"[WARN] Plant not in mapping -> custom site")
        is_matched = False
        is_bottom_up = False
        ctm_sector = None
        ctm_cluster = None
        ctm_site = None
        custom_site_for_plant = None
    else:
        row = plant_mapping.row(0, named=True)
        is_matched = True
        is_bottom_up = row["Bottom-up"]
        is_new = row["New site"]
        ctm_sector = row["Sector"].lower().replace(' ', '_')
        ctm_cluster = row["Cluster"].lower().replace('-', '_').replace(' ', '_')
        ctm_api_name = row["API input name"]
        
        if is_bottom_up:
            ctm_site = ctm_api_name
            logs.append(f"[MATCH] Bottom-up: {ctm_site}")
        elif is_new:
            # Extract from API name (##new_cc_site5##)
            if "new_cc_site" in ctm_api_name:
                custom_site_for_plant = ctm_api_name
                custom_sites_used[plant_id] = custom_site_for_plant
                logs.append(f"[NEW] Custom site: {custom_site_for_plant}")
            else:
                errors.append(f"New site but invalid API name: {ctm_api_name}")
                logs.append(f"[ERROR] {errors[-1]}")
                return {
                    "logs": logs,
                    "scenarios": {},
                    "custom_sites_used": list(custom_sites_used.values()),
                    "total_inputs_pushed": 0,
                    "errors": errors,
                }
        else:
            # Regular site
            parts = ctm_api_name.split("&&")
            if len(parts) >= 3:
                ctm_sector = parts[0]
                ctm_cluster = parts[1]
                ctm_site = parts[2]
                logs.append(f"[MATCH] Regular: {ctm_sector}&&{ctm_cluster}&&{ctm_site}")
            else:
                errors.append(f"Invalid API name: {ctm_api_name}")
                logs.append(f"[ERROR] {errors[-1]}")
                return {
                    "logs": logs,
                    "scenarios": {},
                    "custom_sites_used": list(custom_sites_used.values()),
                    "total_inputs_pushed": 0,
                    "errors": errors,
                }
    
    logs.append(f"\nPushing {len(scenario_df)} rows:\n")
    
    # Create ONE CTM session for all rows
    ctm = CTMClient(use_beta=use_beta)
    
    try:
        session_id = ctm.create_clean_sheet_session()
        logs.append(f"CTM Session: {session_id}\n")
    except Exception as e:
        errors.append(f"Failed to create session: {e}")
        logs.append(f"[ERROR] {errors[-1]}")
        return {
            "logs": logs,
            "scenarios": {},
            "custom_sites_used": list(custom_sites_used.values()),
            "total_inputs_pushed": 0,
            "errors": errors,
        }
    
    # Iterate through rows (NO grouping - already structured correctly)
    for row_data in scenario_df.to_dicts():
        scenario = row_data["Scenario"]
        year = str(row_data["Year"])
        flow_type = row_data.get("Flow type", "").lower()
        
        scenario_key = (scenario, year, flow_type)
        logs.append(f"  [{scenario} / {year} / {flow_type}]")
        
        # Construct inputs
        inputs = {}
        
        if is_matched:
            if is_bottom_up:
                transformation = transformation_overrides.get(plant_id) if transformation_overrides else None
                site_inputs = construct_bottom_up_inputs(
                    sector=ctm_sector,
                    cluster=ctm_cluster,
                    site=ctm_site,
                    row_data=row_data,
                    emission_cols=emission_cols,
                    energy_cols=energy_cols,
                    flow_type=flow_type,
                    logs=logs,
                    transformation=transformation,
                )
                inputs.update(site_inputs)
            else:
                transformation = transformation_overrides.get(plant_id) if transformation_overrides else None
                site_inputs = construct_site_inputs(
                    sector=ctm_sector,
                    cluster=ctm_cluster,
                    site=ctm_site,
                    row_data=row_data,
                    emission_cols=emission_cols,
                    energy_cols=energy_cols,
                    flow_type=flow_type,
                    logs=logs,
                    transformation=transformation,
                )
                inputs.update(site_inputs)
        else:
            # Custom site
            # plant_info = all_scenario_data[plant_id]
            # latitude = plant_info.get("latitude")
            # longitude = plant_info.get("longitude")
            site_inputs = construct_custom_site_inputs(
                sector=ctm_sector,
                cluster=ctm_cluster,
                custom_site=custom_site_for_plant,
                row_data=row_data,
                emission_cols=emission_cols,
                energy_cols=energy_cols,
                flow_type=flow_type,
                logs=logs,
                # latitude=latitude,
                # longitude=longitude,
            )
            inputs.update(site_inputs)
        
        # Push to CTM
        if len(inputs) <= 1:  # Only enabled flag
            logs.append(f"    [SKIP] No data")
            continue
        
        try:
            ctm.set_inputs(inputs)
            total_inputs += len(inputs)
            scenarios_pushed[scenario_key] = session_id
            logs.append(f"    ✓ {len(inputs)} inputs")
        except Exception as e:
            errors.append(f"Failed to push {scenario}/{year}/{flow_type}: {e}")
            logs.append(f"    [ERROR] {errors[-1]}")
    
    # Cleanup
    # try:
    #     ctm.delete_session()
    # except:
    #     pass
    
    logs.append(f"\n{'='*70}")
    logs.append(f"Summary: {total_inputs} inputs / {len(scenarios_pushed)} scenarios pushed")
    logs.append(f"Custom sites: {len(custom_sites_used)}")
    logs.append(f"Errors: {len(errors)}")
    logs.append(f"{'='*70}\n")
    
    return {
        "logs": logs,
        "scenarios": scenarios_pushed,
        "custom_sites_used": list(custom_sites_used.values()),
        "total_inputs_pushed": total_inputs,
        "errors": errors,
    }


# ── Input validation ───────────────────────────────────────────────────────

def validate_and_filter_inputs(
    inputs: dict,
    valid_keys: set,
    logs: list,
) -> dict:
    """
    Filter inputs to only valid CTM keys.
    Logs filtered-out keys.
    Returns filtered dict.
    """
    filtered = {}
    invalid = []
    
    for key, value in inputs.items():
        if key in valid_keys:
            filtered[key] = value
        else:
            invalid.append(key)
    
    if invalid:
        logs.append(f"    [INVALID] Filtered {len(invalid)} keys: {', '.join(invalid[:3])}{'...' if len(invalid) > 3 else ''}")
    
    return filtered



