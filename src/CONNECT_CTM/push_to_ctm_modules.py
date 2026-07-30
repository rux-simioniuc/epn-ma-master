"""
Modular CTM push workflow:
1. load_all_plants_scenario_data() -> load and group plants
2. build_ctm_inputs_from_plants() -> map plant data to CTM format
3. build_ctm_inputs_from_cluster_sector() -> map aggregate data to CTM format
4. push_to_ctm_session() -> create/load session and push inputs
"""

import polars as pl
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import tempfile

from .ctm_client import CTMClient
from .read_DSH_files import read_all_scenario_sheets, read_production_table, read_production_table_curves, read_plant_details
from .utils import read_and_transform_mapping, fix_string, get_final_cluster_sector_curves
from .push_to_ctm import (
    construct_site_inputs,
    construct_bottom_up_inputs,
    construct_custom_site_inputs,
)
from .constants import SCENARIO_YEARS, REFERENCE_YEAR, EMISSION_COLS_ORDER, UTILITY_COLS_ORDER    
from .ctm_constants import SECTORS, CLUSTERS, ALL_SCENARIOS


def get_custom_ctm_inputs() -> Dict:
    """
    Custom CTM inputs (hardcoded).
    These get added to all CTM pushes.
    """
    return {
        "tata_steel&&waste_gas_to_chp_first": "1",
        "shell_pernis&&waste_gas_to_chp_first": "1",

        "##new_cc_site17##&&latitude": "53.30315087671532",
        "##new_cc_site17##&&longitude": "6.986967610715365",

        "##new_cc_site9##&&latitude": "53.30315087671532",
        "##new_cc_site9##&&longitude": "6.986967610715365",
    }



# -- 1. LOAD & GROUP PLANTS -------------------------------------------------

def load_all_plants_scenario_data(
    plants_workbook_dir: str |list,
    mapping_df: pl.DataFrame,
    emission_cols: list[str],
    energy_cols: list[str],
    reference_year: int = REFERENCE_YEAR,
    aggregate_flow_types: bool = True
) -> Tuple[Dict, Dict, List, List]:
    """
    Load all plants' scenario data and group by (scenario, year).
    Flow type data remains in each row.
    
    Returns:
        (all_scenario_data, scenario_year_groups, logs, errors)
        
        all_scenario_data: {
            plant_id: {
                "name": plant_name,
                "df": scenario_df,
                "mapping_row": {sector, cluster, site, ...}
            }
        }
        
        scenario_year_groups: {
            (scenario, year): [(plant_id, row_data), ...]
            where row_data contains {Scenario, Year, Flow type, emissions, energy...}
        }
        
        logs: list of log messages
        errors: list of error messages
    """
    logs = []
    all_scenario_data = {}
    errors = []
        
    # -- Determine source: directory or list of bytes --------------------
    if isinstance(plants_workbook_dir, str):
        # Directory mode
        workbook_dir = Path(plants_workbook_dir)
        workbooks = [(wb_path, None) for wb_path in workbook_dir.glob("*.xlsx")]
        logs.append(f"Found {len(workbooks)} workbooks in {workbook_dir}")
        print(f"Found {len(workbooks)} workbooks in {workbook_dir}")

    
    elif isinstance(plants_workbook_dir, list):
        # List of bytes mode
        workbooks = []
        
        
        for item in plants_workbook_dir:
            # Handle both (filename, bytes) tuples and plain bytes
            if isinstance(item, tuple):
                filename, file_bytes = item
            else:
                filename = item.name
                file_bytes = item
            
            workbooks.append((filename, file_bytes))
        
        logs.append(f"Found {len(workbooks)} Excel files in list")
        print(f"Found {len(workbooks)} Excel files in list")
        # print(workbooks)
    
    else:
        errors.append(f"Invalid plants_workbook_dir type: {type(plants_workbook_dir)}")
        print(f"Invalid plants_workbook_dir type: {type(plants_workbook_dir)}")
        return all_scenario_data, {}, logs, errors

     # -- Process each workbook ------------------------------------------
    for wb_source, file_bytes in workbooks:
        plant_name = Path(wb_source).stem if isinstance(wb_source, str) else str(wb_source).split('/')[-1].split('.')[0]
        try:
            # Find plant in mapping by name
            plant_match = mapping_df.filter(pl.col("DSH plant name") == plant_name)
            if plant_match.is_empty():
                logs.append(f"[WARN] {plant_name} not in mapping")
                print(f"[WARN] {plant_name} not in mapping")
                continue
            
            plant_id = plant_match.row(0, named=True)["DSH plant id"]

            # ── Handle file source ─────────────────────────────────────
            if isinstance(plants_workbook_dir, str):
                # Directory mode: use path directly
                wb_path = wb_source
            else:
                # Bytes mode: save to temp file
                try:
                                # Read UploadedFile to bytes
                    if hasattr(file_bytes, 'read'):
                        # It's a Streamlit UploadedFile
                        file_content = file_bytes.read()
                    else:
                        # It's already bytes
                        file_content = file_bytes

                    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                        tmp.write(file_content)
                        tmp.flush()
                        wb_path = tmp.name

                except Exception as e:
                    print(f'[ERROR] {e}')
            
            # Load scenario data
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
                    # "df_production": production_df,
                    "mapping_row": plant_match.row(0, named=True),
                    "latitude": plant_details.get("Latitude"),
                    "longitude": plant_details.get("Longitude"),
            }
                logs.append(f"✓ {plant_name}: {len(scenario_df)} rows")

                # Try to load production table (optional, may be empty)
                try:
                    production_df = read_production_table(workbook_path=str(wb_path))
                    if not production_df.is_empty():
                        all_scenario_data[plant_id]["production_df"] = production_df
                        # logs.append(f"  └- Production table: {len(production_df)} rows")
                except Exception as e:
                    logs.append(f"  [WARN] No production table: {e}")

                # same thing for the flexibility
                # TODO this is TEMPORARY
                if plant_name == 'Air Liquide Pernis':
                    try:
                        flexibility_df = read_production_table(workbook_path=str(wb_path), sheet_name='Flexibility')
                        if not flexibility_df.is_empty():
                            # filter out comments after the table
                            flexibility_df = flexibility_df.filter(pl.col('Year').is_not_null())
                            all_scenario_data[plant_id]["flexibility_df"] = flexibility_df
                            logs.append(f"  └- Flexibility table: {len(flexibility_df)} rows")
                    except Exception as e:
                        logs.append(f"  [WARN] No production table: {e}")

                '''#same thing for the flexibility table'''
                '''??????????????????????????????????????'''

            # Clean up temp file if created
            if not isinstance(plants_workbook_dir, str):
                try:
                    Path(wb_path).unlink()
                except:
                    pass
        except Exception as e:
            errors.append(f"{plant_name}: {e}")
            logs.append(f"[ERROR] {errors[-1]}")
            print(f"[ERROR] {errors[-1]}")
    
    # Group by (scenario, year)
    scenario_year_groups = {}
    
    for plant_id, plant_data in all_scenario_data.items():
        for row in plant_data["df"].to_dicts():
            scenario = row["Scenario"]
            year = str(row["Year"])
            key = (scenario, year)
            
            if key not in scenario_year_groups:
                scenario_year_groups[key] = []
            scenario_year_groups[key].append((plant_id, row))
    
    logs.append(f"Grouped into {len(scenario_year_groups)} scenario-year combos (all flow_types per session)")
    print('read and loaded all plant excels')
    # print(all_scenario_data)
    return all_scenario_data, scenario_year_groups, logs, errors


# -- 2. BUILD PLANT INPUTS --------------------------------------------------

def build_ctm_inputs_from_plants(
    plants_in_group: List[Tuple[str, dict]],
    all_scenario_data: Dict,
    emission_cols: list[str],
    energy_cols: list[str],
    flow_type: str,
    transformation_overrides: dict = None,
) -> Tuple[Dict, List]:
    """
    Map plant scenario data to CTM input format.
    
    Args:
        plants_in_group: [(plant_id, row_data), ...]
        all_scenario_data: from load_all_plants_scenario_data()
        emission_cols, energy_cols: column names
        flow_type: "demand" or "production"
        transformation_overrides: {plant_id: "0" or "1"}
    
    Returns:
        (inputs_dict, logs)
        
        inputs_dict: {ctm_key: value, ...}
    """
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

        # fix sector and cluster non existent
        if ctm_sector not in SECTORS:
            pass
        if ctm_cluster not in CLUSTERS:
            pass

        
        try:
            if is_bottom_up:
                site_name = ctm_api_name.split("&&")[0]
                transformation = transformation_overrides.get(ctm_api_name) if transformation_overrides else None
                plant_inputs = construct_bottom_up_inputs(
                    sector=ctm_sector,
                    cluster=ctm_cluster,
                    site=site_name,
                    row_data=row_data,
                    emission_cols=emission_cols,
                    energy_cols=energy_cols,
                    flow_type=flow_type,
                    logs=logs,
                    transformation=transformation,
                )
                inputs.update(plant_inputs)
            
            elif is_new:
                plant_info = all_scenario_data[plant_id]
                latitude = str(plant_info.get("latitude"))
                longitude = str(plant_info.get("longitude"))
                custom_site = ctm_api_name.split("&&")[0]
                plant_inputs = construct_custom_site_inputs(
                    sector=ctm_sector,
                    cluster=ctm_cluster,
                    custom_site=custom_site,
                    row_data=row_data,
                    emission_cols=emission_cols,
                    energy_cols=energy_cols,
                    flow_type=flow_type,
                    logs=logs,
                    latitude=latitude,
                    longitude=longitude,
                )
                inputs.update(plant_inputs)
            
            else:
                # Regular site
                parts = ctm_api_name.split("&&")
                if len(parts) >= 3:
                    sector, cluster, site = parts[0], parts[1], parts[2]
                    transformation = transformation_overrides.get(ctm_api_name) if transformation_overrides else None
                    plant_inputs = construct_site_inputs(
                        sector=sector,
                        cluster=cluster,
                        site=site,
                        row_data=row_data,
                        emission_cols=emission_cols,
                        energy_cols=energy_cols,
                        flow_type=flow_type,
                        logs=logs,
                        transformation=transformation,
                    )
                    inputs.update(plant_inputs)
        
        except Exception as e:
            logs.append(f"[ERROR] {plant_name}: {e}")
    
    return inputs, logs


# -- 3. BUILD CLUSTER/SECTOR INPUTS -----------------------------------------

def build_ctm_inputs_from_cluster_sector(
    cluster_sector_data: pl.DataFrame,
) -> Tuple[Dict, List]:
    """
    Map cluster/sector aggregated data to CTM input format.
    
    Args:
        cluster_sector_data: DataFrame (after reshape_cluster_sector_curves) with columns:
            Cluster, Sector, Scenario, Year, Value, Utility, Flow type
    
    Returns:
        (inputs_dict, logs)
    """
    logs = []
    inputs = {}
    
    # Iterate over rows
    for row in cluster_sector_data.to_dicts():
        sector = row.get("Sector").lower().replace('-', '_').replace(' ', '_')
        cluster = row.get("Cluster").lower().replace('-', '_').replace(' ', '_')
        utility = row.get("Utility").lower().replace('-', '_').replace(' ', '_')
        flow_type = row.get("Flow type", "demand").lower()
        value = row.get("Value")
        
        if not all([sector, cluster, utility, flow_type, value is not None]):
            continue

        # enable the sector / industry curves
        enable_key = f"{sector}&&{cluster}&&cluster&&enable"
        inputs[enable_key] = '1'

        
        # Normalize utility name to CTM format (lowercase, spaces->underscores)
        ctm_utility = utility#.lower().replace(" ", "_").replace("(", "").replace(")", "")
        
        # Build CTM input key for cluster level
        ctm_key = f"{sector}&&{cluster}&&cluster&&{ctm_utility}_{flow_type}"
        if value != 0:
            inputs[ctm_key] = str(value)

            # if sector in ['refineries', 'steel']:
            #     print('x')
            
    logs.append(f"Cluster-sector: {sector}/{cluster} = {len(inputs)} inputs")
    
    return inputs, logs


def build_sector_cluster_sites(
    cluster_sector_data: pl.DataFrame,
) -> Tuple[Dict, List]:
    """
    Map cluster/sector aggregated data to CTM input format.
    
    Args:
        cluster_sector_data: DataFrame (after reshape_cluster_sector_curves) with columns:
            Cluster, Sector, Scenario, Year, Value, Utility, Flow type
    
    Returns:
        (inputs_dict, logs)
    """
    logs = []
    inputs = {}
    
    # Iterate over rows
    for row in cluster_sector_data.to_dicts():
        sector = row.get("Sector").lower().replace('-', '_').replace(' ', '_')
        cluster = row.get("Cluster").lower().replace('-', '_').replace(' ', '_')
        utility = row.get("Utility").lower().replace('-', '_').replace(' ', '_')
        flow_type = row.get("Flow type", "demand").lower()
        value = row.get("Value")
        
        if not all([sector, cluster, utility, flow_type, value is not None]):
            continue

        # Normalize utility name to CTM format (lowercase, spaces->underscores)
        ctm_utility = utility

        if cluster == 'cluster_6':
            input_key = f'sector_site_{sector}'
        else:
            input_key = f'cluster_site_{sector}_{cluster}'

        if value != 0:
            # enable the sector / industry curves
            enable_key = f"{sector}&&{cluster}&&{input_key}&&enabled"
            inputs[enable_key] = '1'
            
            # Build CTM input key for cluster level
            ctm_key = f"{sector}&&{cluster}&&{input_key}&&{ctm_utility}_{flow_type}"
            inputs[ctm_key] = str(value)
            
    logs.append(f"Cluster-sector: {sector}/{cluster} = {len(inputs)} inputs")
    
    return inputs, logs


def build_ctm_inputs_from_production(
    sector: str,
    cluster: str,
    site: str,
    production_df: pl.DataFrame,
    is_bottom_up: bool = False,      
    is_custom: bool = False,
    is_sector_cluster: bool = False
) -> Tuple[Dict, List]:
    """
    Map production table data to CTM input format.
    
    Args:
        sector, cluster, site: site hierarchy
        production_df: DataFrame with columns:
            Scenario, Year, Capacity, FLH, Efficiency electricity, Efficiency heat
    
    Returns:
        (inputs_dict, logs)
    """
    logs = []
    inputs = {}
    
    cluster = fix_string(cluster)
    sector = fix_string(sector)

    # Map DSH production columns to CTM input names
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
            
            if value is not None:
                try:
                    # Convert to float (handle string values)
                    val_float = float(value)
                    if val_float > 0:   # skip 0 values

                        # check if efficiency values are fractions
                        # ctm requires values between 0 and 1
                        if 'efficiency' in dsh_col.lower():
                            if val_float > 1:
                                val_float /= 100

                        # if val_float < 0:
                        #     logs.append(f"  [SKIP NEG] {scenario}/{year} {ctm_col}={val_float}")
                        #     continue
                        
                        if is_bottom_up or is_custom:
                            ctm_key = f"{site}&&{ctm_col}"  # Flat pattern
                        elif is_sector_cluster:
                            ctm_key = f"{sector}&&{cluster}&&cluster&&{ctm_col}"
                        else:
                            ctm_key = f"{sector}&&{cluster}&&{site}&&{ctm_col}"

                        inputs[ctm_key] = str(val_float)
                
                except (ValueError, TypeError):
                    logs.append(f"  [SKIP] {scenario}/{year} {ctm_col}: invalid value {value}")
    
    # logs.append(f"  Production: {site} {scenario}/{year} = {len(inputs)} inputs")
    
    return inputs, logs


def build_ctm_inputs_from_flexibility(
    flexibility_df: pl.DataFrame,
    scenario: str,
    year: str,
    logs: list = None,
) -> Tuple[Dict, List]:
    """
    Build CTM inputs from Flexibility table (scenario+year aggregated).
    
    Maps to:
    - Capacity -> additional_chp_capacity_additional_chp_capacity_input
    - Efficiency electricity -> additional_chp_capacity_chp_electrical_efficiency_input
    - Efficiency heat -> additional_chp_capacity_chp_thermal_efficiency_input
    
    Not tied to a site - global flexibility inputs.
    """
    
    if logs is None:
        logs = []
    
    inputs = {}
    
    # Filter to this scenario/year
    filtered = flexibility_df.filter(
        (pl.col("Scenario") == scenario) &
        (pl.col("Year") == str(year))
    )
    
    if filtered.is_empty():
        return inputs
    
    # Map columns to CTM inputs
    column_map = {
        "Capacity": "additional_chp_capacity_additional_chp_capacity_input",
        "Efficiency electricity": "additional_chp_capacity_chp_electrical_efficiency_input",
        "Efficiency heat": "additional_chp_capacity_chp_thermal_efficiency_input",
    }
    
    for row in filtered.to_dicts():
        for dsh_col, ctm_col in column_map.items():
            value = row.get(dsh_col)
            
            if value is not None and value != 0:  # Skip None and 0
                try:
                    val_float = float(value)
                    if val_float <= 0:  # Skip 0 and negative
                        # if val_float < 0:
                        #     logs.append(f"    [SKIP NEG] Flexibility {ctm_col}={val_float}")
                        continue
                    
                    inputs[ctm_col] = str(val_float)
                
                except (ValueError, TypeError):
                    logs.append(f"    [SKIP] Flexibility {ctm_col}: invalid value {value}")
    
    logs.append(f"    Flexibility: {len(inputs)} inputs")
    return inputs, logs

# -- 4. PUSH TO CTM SESSION -------------------------------------------------

def push_to_ctm_session(
    inputs: Dict,
    session_id: Optional[str] = None,
    use_beta: bool = True,
    auto_create: bool = True,
) -> Tuple[Optional[str], List, List]:
    """
    Push inputs to CTM session.
    
    Args:
        inputs: {ctm_key: value, ...}
        session_id: existing session ID (optional); if None, creates new
        use_beta: use CTM beta environment
        auto_create: if session_id is None, create clean sheet; else error
    
    Returns:
        (session_id_used, logs, errors)
    """
    logs = []
    errors = []
    
    ctm = CTMClient(use_beta=use_beta)
    
    # Load or create session
    if session_id:
        try:
            ctm.load_session(session_id)
            logs.append(f"Loaded session: {session_id}")
        except Exception as e:
            errors.append(f"Failed to load session {session_id}: {e}")
            return None, logs, errors
    elif auto_create:
        try:
            session_id = ctm.create_clean_sheet_session()
            logs.append(f"Created session: {session_id}")
        except Exception as e:
            errors.append(f"Failed to create session: {e}")
            return None, logs, errors
    else:
        errors.append("No session_id provided and auto_create=False")
        return None, logs, errors
    
    # Push inputs
    if not inputs or len(inputs) <= 1:
        logs.append("[SKIP] No valid inputs to push")
        return session_id, logs, errors
    
    try:
        ctm.set_inputs(inputs)
        logs.append(f"✓ Pushed {len(inputs)} inputs")
    except Exception as e:
        errors.append(f"Failed to push inputs: {e}")
        logs.append(f"[ERROR] {errors[-1]}")
    
    # Cleanup
    try:
        ctm.delete_session()
    except:
        pass
    
    return session_id, logs, errors


# -- 5. MAIN ORCHESTRATOR --------------------------------------------------

def push_aggregated_by_scenario_year(
    plants_workbook_dir: str | list,
    mapping_df: pl.DataFrame,
    emission_cols: list[str] = EMISSION_COLS_ORDER,
    energy_cols: list[str] = UTILITY_COLS_ORDER,
    cluster_sector_file: Optional[str] | pl.DataFrame = None,
    cluster_sector_production_sheet_name: str = None,
    cluster_sector_curves_sheet_name: str = None,
    cluster_sector_production: pl.DataFrame = None,
    reference_year: int = REFERENCE_YEAR,
    use_beta: bool = True,
    transformation_overrides: dict = None,
    output_log_file: Optional[str] = None,
    reuse_sessions: Optional[Dict[Tuple, str]] = None,
    selected_scenarios: list[str] = ALL_SCENARIOS,
    selected_years: list[str] = SCENARIO_YEARS,
    session_path: str = ''
) -> dict:
    """
    Main workflow: Load plants, group by scenario-year, build inputs, push to CTM.
    
    Args:
        plants_workbook_dir: directory containing Excel files
        mapping_df: polars df with the mapping
        emission_cols, energy_cols: from constants
        cluster_sector_file: optional excel with cluster/sector aggregated data
        reference_year: year to skip
        use_beta: use CTM beta
        transformation_overrides: {plant_id: "0" or "1"}
        output_log_file: write full log to file
        reuse_sessions: {(scenario, year): session_id} to reuse existing sessions
    
    Returns:
        {
            "logs": [...],
            "sessions": {(scenario, year): session_id, ...},
            "total_plants": int,
            "total_scenario_years": int,
            "errors": [...],
        }
    """
    all_logs = []
    all_errors = []
    sessions_created = {}

    custom_inputs = get_custom_ctm_inputs()
    
    all_logs.append(f"\n{'='*70}")
    all_logs.append("AGGREGATED PUSH BY SCENARIO-YEAR (MODULAR)")
    all_logs.append(f"{'='*70}\n")
    
    # Step 1: Load all plants
    all_logs.append("STEP 1: Loading plants...")
    print("STEP 1: Loading plants...")
    all_scenario_data, scenario_year_groups, step_logs, step_errors = load_all_plants_scenario_data(
        plants_workbook_dir=plants_workbook_dir,
        mapping_df=mapping_df,
        emission_cols=emission_cols,
        energy_cols=energy_cols,
        reference_year=reference_year,
    )
    all_logs.extend(step_logs)
    all_errors.extend(step_errors)
    
    if not all_scenario_data:
        all_logs.append("[ERROR] No plants loaded")
        print("[ERROR] No plants loaded")
        return {
            "logs": all_logs,
            "sessions": {},
            "total_plants": 0,
            "total_scenario_years": 0,
            "errors": all_errors,
        }
    
    # Load and reshape cluster/sector data if provided
    cluster_sector_df_long = None
    sector_cluster_prod_df = None
    if cluster_sector_file is not None:
        try:
            all_logs.append("STEP 1B: Loading and reshaping cluster/sector curves...")
            print("STEP 1B: Loading and reshaping cluster/sector curves...")
            if type(cluster_sector_file) == str:
                # if it's a path
                cluster_sector_df_long = get_final_cluster_sector_curves(excel_path=cluster_sector_file, sheet_name=cluster_sector_curves_sheet_name, years=SCENARIO_YEARS)
            else:
                # if it's a dataframe
                cluster_sector_df_long = get_final_cluster_sector_curves(curves_df=cluster_sector_file, years=SCENARIO_YEARS)

            cluster_sector_df_long = cluster_sector_df_long.filter(~pl.col('Sector').is_in(['refineries', 'steel']))
            all_logs.append(f"  ✓ Reshaped cluster/sector data: {len(cluster_sector_df_long)} rows")
        except Exception as e:
            all_logs.append(f"[ERROR] Failed to load cluster-sector data: {e}")
            all_errors.append(str(e))
            print(f"[ERROR] Failed to load cluster-sector data: {e}")


        try:
            all_logs.append("STEP 1C: Loading and reshaping cluster/sector curves for production...")
            print("STEP 1C: Loading and reshaping cluster/sector curves for production...")
            if cluster_sector_production is None:
                sector_cluster_prod_df  = read_production_table_curves(workbook_path=cluster_sector_file, sheet_name=cluster_sector_production_sheet_name)
            else:
                sector_cluster_prod_df  = read_production_table_curves(curves_df=cluster_sector_production)

            all_logs.append(f"  ✓ Production cluster/sector data: {len(sector_cluster_prod_df )} rows")
        except Exception as e:
            all_logs.append(f"[ERROR] Failed to load cluster-sector production data: {e}")
            all_errors.append(str(e))
            print(f"[ERROR] Failed to load cluster-sector production data: {e}")


    
    # Step 2: Process each scenario-year combo
    num_scenarios = len(selected_scenarios) * len(selected_years)
    all_logs.append(f"\nSTEP 2: Processing {num_scenarios} scenario-year combos...")
    print(f"\nSTEP 2: Processing {num_scenarios} scenario-year combos...")

    for (scenario, year), plants_in_year in sorted(scenario_year_groups.items()):
        print(f'{scenario}, {year}, {type(year)}, {scenario in selected_scenarios}, {year in selected_years}')
        if (scenario in selected_scenarios) and (year in selected_years):
            scenario_key = (scenario, year)
            all_logs.append(f"\n[{scenario} / {year}] — {len(plants_in_year)} plant-records")
            
            # Create or reuse session
            reuse_sid = None
            if reuse_sessions and scenario_key in reuse_sessions:
                reuse_sid = reuse_sessions[scenario_key]
                all_logs.append(f"  Reusing session: {reuse_sid}")
            
            try:
                if reuse_sid:
                    ctm = CTMClient(use_beta=use_beta)
                    ctm.load_session(reuse_sid)
                else:
                    ctm = CTMClient(use_beta=use_beta)
                    reuse_sid = ctm.create_clean_sheet_session()
                
                all_logs.append(f"  Session: {reuse_sid}")
            except Exception as e:
                all_logs.append(f"  [ERROR] {e}")
                all_errors.append(str(e))
                print(f"  [ERROR] {e}")
                continue
            
            # Process all plant-level data in one efficient pass
            all_inputs, step_logs = process_plants_for_scenario_year(
                scenario=scenario,
                year=year,
                plants_in_year=plants_in_year,
                all_scenario_data=all_scenario_data,
                emission_cols=emission_cols,
                energy_cols=energy_cols,
                transformation_overrides=transformation_overrides,
            )
            all_logs.extend(step_logs)
            
            # Add cluster/sector inputs
            if cluster_sector_df_long is not None:
                try:
                    filtered = cluster_sector_df_long.filter(
                        (pl.col("Scenario").str.to_lowercase() == scenario.lower()) & 
                        (pl.col("Year") == year)
                    )
                    if not filtered.is_empty():
                        cluster_inputs, cluster_logs = build_sector_cluster_sites(
                            cluster_sector_data=filtered
                        )
                        all_inputs.update(cluster_inputs)
                        all_logs.extend(cluster_logs)
                except Exception as e:
                    all_logs.append(f"[ERROR] Cluster/sector: {e}")
            
            # Add sector/cluster production
            if sector_cluster_prod_df is not None:
                filtered_prod = sector_cluster_prod_df.filter(
                    (pl.col("Scenario") == scenario) & (pl.col("Year") == year)
                )
                
                if not filtered_prod.is_empty():
                    for row in filtered_prod.to_dicts():
                        prod_inputs, prod_logs = build_ctm_inputs_from_production(
                            sector=row["Sector"],
                            cluster=row["Cluster"],
                            site=None,
                            production_df=pl.DataFrame(row),
                            is_sector_cluster=True,
                        )
                        all_inputs.update(prod_inputs)
                        all_logs.extend(prod_logs)

            # add custom inputs
            all_inputs.update(custom_inputs)
            all_logs.append(f"Added {len(custom_inputs)} custom inputs")

            
            # Push to CTM
            if all_inputs and len(all_inputs) > 1:
                try:
                    ctm.set_inputs(all_inputs)
                    sessions_created[scenario_key] = reuse_sid
                    all_logs.append(f"  ✓ Pushed {len(all_inputs)} total inputs")
                    print(f"  ✓ Pushed {len(all_inputs)} total inputs")
                except Exception as e:
                    all_errors.append(f"Failed to push: {e}")
                    all_logs.append(f"  [ERROR] {e}")
                    print(f"Failed to push: {e}")
            else:
                all_logs.append(f"  [SKIP] No valid inputs")


            inputs_path = Path(session_path)
            inputs_path.mkdir(parents=True, exist_ok=True)
            inputs_file = f'{inputs_path}/inputs_{scenario}_{year}.json'
            with open(inputs_file, "w") as f:
                 json.dump(all_inputs, f, indent=4)
            print(f'--------- done with {scenario} {year} ----------')
    
    # Step 3: Summary
    all_logs.append(f"\n{'='*70}")
    all_logs.append("SUMMARY:")
    all_logs.append(f"  Plants loaded: {len(all_scenario_data)}")
    all_logs.append(f"  Scenario-year-flow combos: {len(scenario_year_groups)}")
    all_logs.append(f"  Sessions created: {len(sessions_created)}")
    all_logs.append(f"  Errors: {len(all_errors)}")
    all_logs.append(f"{'='*70}\n")

    print(f"\n{'='*70}")
    print("SUMMARY:")
    print(f"  Plants loaded: {len(all_scenario_data)}")
    print(f"  Scenario-year-flow combos: {len(scenario_year_groups)}")
    print(f"  Sessions created: {len(sessions_created)}")
    print(f"  Errors: {len(all_errors)}")
    print(f"{'='*70}\n")
    
    # Write log file if requested
    if output_log_file:
        with open(output_log_file, "w") as f:
            f.write("\n".join(all_logs))
        all_logs.append(f"Log written to {output_log_file}")
    
    return {
        "logs": all_logs,
        "sessions": sessions_created,
        "total_plants": len(all_scenario_data),
        "total_scenario_years": len(scenario_year_groups),
        "errors": all_errors,
    }


from datetime import datetime
from pathlib import Path


def write_push_logs(
    result: dict,
    output_dir: str = "./push_logs",
) -> dict:
    """
    Write push logs to organized folder structure.
    Creates a new timestamped folder with separate log files.
    
    Args:
        result: return dict from push_aggregated_by_scenario_year()
        output_dir: base directory for logs
    
    Returns:
        {
            "folder": path_to_folder,
            "logs_file": path,
            "sessions_file": path,
            "errors_file": path,
        }
    """
    
    # Create timestamped folder
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = Path(output_dir) / f"run_{timestamp}"
    run_folder.mkdir(parents=True, exist_ok=True)
    
    files = {}
    
    # -- Write main logs --------------------------------------------
    logs_file = run_folder / "logs.txt"
    with open(logs_file, "w") as f:
        f.write("\n".join(result.get("logs", [])))
    files["logs_file"] = str(logs_file)
    
    # -- Write sessions --------------------------------------------
    sessions_file = run_folder / "sessions.txt"
    with open(sessions_file, "w") as f:
        f.write("SESSIONS CREATED\n")
        f.write("="*70 + "\n\n")
        
        if result.get("sessions"):
            for key, session_id in result["sessions"].items():
                scenario, year = key
                f.write(f"{scenario} / {year}\n")
                f.write(f"  Session ID: {session_id}\n\n")
        else:
            f.write("No sessions created.\n")
    files["sessions_file"] = str(sessions_file)
    
    # -- Write errors ----------------------------------------------
    errors_file = run_folder / "errors.txt"
    with open(errors_file, "w") as f:
        f.write("ERRORS\n")
        f.write("="*70 + "\n\n")
        
        if result.get("errors"):
            for i, error in enumerate(result["errors"], 1):
                f.write(f"{i}. {error}\n\n")
        else:
            f.write("No errors.\n")
    files["errors_file"] = str(errors_file)
    
    # -- Write summary ---------------------------------------------
    summary_file = run_folder / "summary.txt"
    with open(summary_file, "w") as f:
        f.write("PUSH SUMMARY\n")
        f.write("="*70 + "\n\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Total plants: {result.get('total_plants', 0)}\n")
        f.write(f"Scenario-year combos: {result.get('total_scenario_years', 0)}\n")
        f.write(f"Sessions created: {len(result.get('sessions', {}))}\n")
        f.write(f"Errors: {len(result.get('errors', []))}\n")
    files["summary_file"] = str(summary_file)
    
    files["folder"] = str(run_folder)
    
    return files


def _build_production_for_plant(
    plant_id: str,
    plant_info: dict,
    mapping_row: dict,
    production_df,
    scenario: str,
    year: str,
    logs: list,
) -> Tuple[Dict, List]:
    """
    Build production inputs for a single plant.
    Extracted helper to reduce nesting.
    """
    
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
                sector=ctm_sector,
                cluster=ctm_cluster,
                site=site_name,
                production_df=production_df,
                is_bottom_up=True
            )
        elif is_new:
            custom_site = ctm_api_name.split("&&")[0]
            prod_inputs, prod_logs = build_ctm_inputs_from_production(
                sector=ctm_sector,
                cluster=ctm_cluster,
                site=custom_site,
                production_df=production_df,
                is_custom=True
            )
        else:
            # Regular site
            parts = ctm_api_name.split("&&")
            if len(parts) >= 3:
                sector, cluster, site = parts[0], parts[1], parts[2]
                prod_inputs, prod_logs = build_ctm_inputs_from_production(
                    sector=sector,
                    cluster=cluster,
                    site=site,
                    production_df=production_df,
                )
            else:
                return inputs, logs
        
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
    transformation_overrides: dict = None,
) -> Tuple[Dict, List]:
    """
    Process all plant data for a single scenario-year combo.
    Single efficient loop that handles:
    - Plant inputs (demand + production flow types)
    - Production table inputs (once per unique plant)
    - Flexibility table inputs (once per unique plant)
    
    Returns:
        (all_inputs, logs)
    """
    
    logs = []
    all_inputs = {}
    processed_plants = set()
    
    # -- Group by flow_type ----------------------------------------
    by_flow_type = {}
    for plant_id, row in plants_in_year:
        flow_type = row.get("Flow type", "").lower()
        if flow_type not in by_flow_type:
            by_flow_type[flow_type] = []
        by_flow_type[flow_type].append((plant_id, row))
    
    # -- Build plant inputs for each flow_type ----------------------
    for flow_type, plants_for_flow in by_flow_type.items():
        # logs.append(f"  [{flow_type}] — {len(plants_for_flow)} plants")
        
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
    
    # -- Process production tables (once per unique plant) ----------
    # logs.append(f"  [production tables]")
    for plant_id, row in plants_in_year:
        if plant_id in processed_plants:
            continue
        processed_plants.add(plant_id)
        
        plant_info = all_scenario_data[plant_id]
        if "production_df" not in plant_info:
            continue
        
        production_df = plant_info["production_df"]
        mapping_row = plant_info["mapping_row"]
        
        # Filter to this scenario-year
        filtered_prod = production_df.filter(
            (pl.col("Scenario") == scenario) & (pl.col("Year") == year)
        )
        
        if filtered_prod.is_empty():
            continue
        
        # Build production inputs
        prod_inputs, prod_logs = _build_production_for_plant(
            plant_id=plant_id,
            plant_info=plant_info,
            mapping_row=mapping_row,
            production_df=filtered_prod,
            scenario=scenario,
            year=year,
            logs=logs,
        )
        all_inputs.update(prod_inputs)
        logs.extend(prod_logs)
    
    # -- Process flexibility tables (once per unique plant) --------
    logs.append(f"  [flexibility tables]")
    for plant_id in processed_plants:
        plant_info = all_scenario_data[plant_id]
        if "flexibility_df" not in plant_info:
            continue
        
        flexibility_df = plant_info["flexibility_df"]
        
        # Filter to this scenario-year
        filtered_flex = flexibility_df.filter(
            (pl.col("Scenario") == scenario) & (pl.col("Year") == year)
        )
        
        if filtered_flex.is_empty():
            continue
        
        # Build flexibility inputs
        flex_inputs, flex_logs = build_ctm_inputs_from_flexibility(
            flexibility_df=flexibility_df,
            scenario=scenario,
            year=year,
            logs=logs,
        )
        all_inputs.update(flex_inputs)
        logs.extend(flex_logs)
    
    return all_inputs, logs



