from .utils import *
import polars as pl
import pandas as pd
from .format_emissies_sheet import (
    write_plant_details_sheet,
    write_energy_balance_sheet,
    write_projects_sheet,
    write_production_sheet,
    write_storage_sheet,
    write_flexibility_sheet,
    write_scenario_sheets,
)
 
# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = "/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260625_live"
OUT_DIR = "/home/307920@ontw.alfa.local/projects/epn-ma-master/generated/result_v6"
REF_YEAR = 2024
 
# DATA_FILES = {
#     "emission_forecast": "datasafehouse-emission-forecast-export_all_v2_20260521_df20260423.csv",
#     "demand_forecast": "datasafehouse-forecast-export_all_v2_20260521_df20260423.csv",
#     "emission_reference": "reference_emission_data_df20260423.csv",
#     "demand_reference": "reference_utility_data_df20260423.csv",
#     "plants": "datasafehouse-plant-export.csv.csv",
#     "project_emissions": "datasafehouse-projectdata-export_emissions_df20260423.csv",
#     "project_utilities": "datasafehouse-projectdata-export_utilities_df20260423.csv",
#     "production": "data-export_electricity_production_df20260423.csv",
#     "storage": "data-export_energy_storage_df20260423.csv",
#     "flexibility": "data-export_flex_options_df20260423.csv",
# }

DATA_FILES = {
    "emission_forecast": "datasafehouse-emission-forecast-export_all_v3_20260625live.csv",
    "demand_forecast": "datasafehouse-forecast-export_all_v3_20260625live.csv",
    "emission_reference": "reference_emission_data_20260625live.csv",
    "demand_reference": "reference_utility_data_20260625live.csv",
    "plants": "datasafehouse-plant-export_20260625live.csv",
    "project_emissions": "datasafehouse-projectdata-export_emissions_20260625live.csv",
    "project_utilities": "datasafehouse-projectdata-export_utilities_20260625live.csv",
    "production": "data-export_electricity_production_20260625live.csv",
    "storage": "data-export_energy_storage_20260625live.csv",
    "flexibility": "data-export_flex_options_20260625live.csv",
}
 
 
def read_csv(filename: str) -> pl.DataFrame:
    """Read a CSV via pandas, falling back to Polars for malformed files."""
    filepath = f"{DATA_DIR}/{filename}"
    try:
        return pl.from_pandas(pd.read_csv(filepath))
    except pd.errors.ParserError:
        print(f"  [warn] Falling back to Polars for {filename}")
        return pl.read_csv(filepath, truncate_ragged_lines=True)
 
 
def load_data() -> dict[str, pl.DataFrame]:
    """Load all source CSVs and return as a named dict."""
    print("Loading data...")
    data = {name: read_csv(filename) for name, filename in DATA_FILES.items()}
    # Parse EANs once here so it's not repeated per plant
    data["plants_parsed"] = parse_All_EANs(data["plants"])
    print(f"  Loaded {len(DATA_FILES)} files.")
    return data
 
 
def process_plant(plant_id: str, data: dict[str, pl.DataFrame]) -> None:
    """Process a single plant and generate all Excel sheets."""
    plant_name = get_plant_name(data["plants"], plant_id)
    output_path = f"{OUT_DIR}/{plant_name}.xlsx"
    print(f"  Processing: {plant_name}")
 
    units = get_all_units(
        ref_emission_df=data["emission_reference"],
        ref_utility_df=data["demand_reference"],
    )
 
    # ── data preparation ───────────────────────────────────────────────────
    energy_balance = get_energy_balance_emissions_sheet(
        data["emission_forecast"],
        data["emission_reference"],
        data["demand_forecast"],
        data["demand_reference"],
        plant_id,
        REF_YEAR,
    )
 
    details = create_company_details_dfs(
        data["plants"],
        plant_id,
        parsed_df=data["plants_parsed"],
    )
 
    projects = get_project_sheet(
        data["project_emissions"],
        data["project_utilities"],
        plant_id,
    )
 
    production = get_production_sheet(data["production"], plant_id)
    storage = get_storage_sheet(data["storage"], plant_id)
    flexibility = get_flexibility_sheet(data["flexibility"], plant_id)
 
    # ── write sheets ──────────────────────────────────────────────────────
    write_plant_details_sheet(details, output_path)
    write_energy_balance_sheet(energy_balance, output_path, units=units, existing_path=output_path)
    write_projects_sheet(projects, output_path, units=units, existing_path=output_path)
    write_production_sheet(production, output_path, existing_path=output_path)
    write_storage_sheet(storage, output_path, existing_path=output_path)
    write_flexibility_sheet(flexibility, output_path, existing_path=output_path)
    write_scenario_sheets(energy_balance, output_path, units=units, existing_path=output_path)
 
    print(f"  -> Saved: {output_path}")


def main():
    data = load_data()

    plant_ids = data["plants"]["Plant identifier"].unique().to_list()
    print(f"\nProcessing {len(plant_ids)} plants...\n")

    failed = []
    # plant_ids = ['0ac0ee36-995e-4723-a75a-4ce8724b0560']
    # units = get_all_units(datap[])
    # plant_ids = [
    #             '406230a8-b9e8-4cc6-b5ca-736be061e310', 
    #              '6f852331-ede7-46bb-936a-cc595c3c53fc', 
    #              'fe750ef2-98dc-47bd-9c5e-91c57146bc81', 
    #              '11b16c45-a3f0-47dc-a540-36234763467a', 
    #              '48fb5231-1d91-4906-97e7-8c44332b0637', 
    #              '9759c317-7a91-4e02-a8d3-7f32a61a4458', 
    #              '91a42c6f-b7d3-4010-b8b9-20441ab16f38', 
    #              'cb8337ec-4ee7-4d36-ae76-f57a996b864d', 
    #              '476f395e-d20d-44f3-b5bd-f01c5f2a0d81'
    #              ]

    # tata steel
    plant_ids = ['f67fb011-8516-4403-a0aa-1ac3d89404a8']

    for plant_id in plant_ids:
        try:
            process_plant(plant_id, data)
        except Exception as e:
            plant_name = get_plant_name(data["plants"], plant_id)
            print(f"  [ERROR] {plant_name} ({plant_id}): {e}")
            failed.append((plant_name, plant_id, e))

    print(f"\nDone. {len(plant_ids) - len(failed)}/{len(plant_ids)} plants succeeded.")
    if failed:
        print("\nFailed plants:")
        for name, pid, err in failed:
            print(f"  - {name} ({pid}): {err}")


if __name__ == "__main__":
    main()