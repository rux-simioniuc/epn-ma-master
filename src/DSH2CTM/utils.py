import polars as pl
import pandas as pd
import json
from .constants import *


def get_plant_name(df: pl.DataFrame, plant_id: str) -> str:
    """Extract and sanitise plant name for use in filenames."""
    result = df.filter(pl.col("Plant identifier") == plant_id).select("Plant name").head(1)
    if len(result) == 0:
        return f"Unknown_{plant_id[:8]}"
    return result[0, 0].replace("/", "_")


# update utility list

def update_utility_list(ref_utility_df:pl.DataFrame) ->list:
    utilities = ref_utility_df.select(pl.col('Utility')).to_series().to_list()
    updated = [i for i in UTILITY_COLS_ORDER if i in utilities]
    return updated

# ── Unit helpers ───────────────────────────────────────────────────────────

def _get_emission_units(ref_emission_df: pl.DataFrame) -> pl.DataFrame:
    return (
        ref_emission_df
        .with_columns(Emission=pl.col("Emission").replace("N₂O", "N2O"))
        .select(['Emission', 'Annual UOM'])
        .unique()
        .rename({'Emission': 'Type', 'Annual UOM': 'Unit'})
    )
 
def _get_utility_units(ref_utility_df: pl.DataFrame) -> pl.DataFrame:
    return (
        ref_utility_df
        .select(['Utility', 'Annual UOM', 'Peak UoM'])
        .unique()
        .rename({'Utility': 'Type', 'Annual UOM': 'Unit', 'Peak UoM': 'Peak unit'})
        # normalise casing to match column names (e.g. "other" -> "Other")
        .with_columns(pl.col('Type').str.strip_chars().str.to_titlecase())
    )
 
def get_all_units(ref_emission_df: pl.DataFrame, ref_utility_df: pl.DataFrame) -> pl.DataFrame:
    """Returns a DataFrame with columns [Type, Unit, Peak unit]."""
    emission_units = _get_emission_units(ref_emission_df)
    utility_units  = _get_utility_units(ref_utility_df)
    return pl.concat([emission_units, utility_units], how="diagonal")
 
# UOM overrides for columns not in the reference data
_UNIT_OVERRIDES = {
    'CO2 (fossil) CCU/CCS': 'kton/year',
    'CO2 (bio) CCU/CCS':    'kton/year',
    'F-gases':    'kton/year',
}
 
def get_unit(units_df: pl.DataFrame, substance_name: str, is_peak: bool = False) -> str | None:
    # check hardcoded overrides first (e.g. greenhouse cols not in reference data)
    if not is_peak and substance_name in _UNIT_OVERRIDES:
        return _UNIT_OVERRIDES[substance_name]

    lookup_name = 'Electricity' if substance_name == 'Electricity_peak' else substance_name
    is_peak     = is_peak or substance_name == 'Electricity_peak'
    unit_col    = 'Peak unit' if is_peak else 'Unit'

    result = units_df.filter(pl.col('Type') == lookup_name).select(unit_col).head(1)
    if len(result) > 0:
        unit = result[0, 0]
        if unit and len(str(unit)) > 0:
            return unit

    # fallback for energy carriers not present in this plant's reference data
    return 'MW' if is_peak else 'GWh/year'
 

# ── Plant details ──────────────────────────────────────────────────────────

def parse_All_EANs(df: pl.DataFrame) -> pl.DataFrame:
    """Expands the 'All EANs' JSON column into multiple rows/columns."""
    df_pd = df.to_pandas()
    df_pd['All EANs'] = df_pd['All EANs'].apply(json.loads)
    df_pd = df_pd.explode('All EANs', ignore_index=True)
    ean_df = pd.json_normalize(df_pd['All EANs'])
    df_pd = pd.concat([df_pd.drop('All EANs', axis=1), ean_df], axis=1)
    return pl.from_pandas(df_pd)


def create_company_details_dfs(df: pl.DataFrame, plant_id: str,
                                parsed_df: pl.DataFrame = None) -> pl.DataFrame:
    """
    Returns a two-column [Field, Value] DataFrame of plant details.
    Pass parsed_df to avoid re-parsing All EANs on every call.
    """
    working_df = parsed_df if parsed_df is not None else parse_All_EANs(df)
    plant_data = working_df.filter(pl.col('Plant identifier') == plant_id)
    base = plant_data.row(0, named=True)

    sbi_key = next(
    (key for key in base.keys() if "SBI" in key),
    None
)

    rows = [
        ['Adres',                    base['Address']],
        ['Stad',                     base['City']],
        ['Postcode',                 base['Zip code']],
        ['Nieuw/Bestaand bedrijf',   base['Existing plant/New plant']],
        ['Breedtegraad',             base['Latitude']],
        ['Lengtegraad',              base['Longitude']],
        ['Locatie',                  base['Plant name']],
        ['Sector (SBI/NACE code)',   base[sbi_key]],
        ['Cluster (drop-down menu)', base['City']],
    ]

    utility_mapping = {
        'Electricity': 'elektriciteit',
        'Natural Gas':  'aardgas',
        'Hydrogen':     'waterstof',
    }

    for utility_en, utility_nl in utility_mapping.items():
        connections = plant_data.filter(
            pl.col('utility_name').str.contains(utility_en)
        ).sort(pl.col('main_connection'), descending=True)

        for i, conn in enumerate(connections.iter_rows(named=True), 1):
            rows.extend([
                [f'Aansluiting {utility_nl} {i}: EAN',              conn['ean_code']],
                [f'Aansluiting {utility_nl} {i}: Netbeheerder',     conn['grid_operator']],
                [f'Aansluiting {utility_nl} {i}: Type',             conn['connection_type']],
                [f'Aansluiting {utility_nl} {i}: Hoofdaansluiting', conn['main_connection']],
            ])

    return pl.DataFrame(rows, schema=['Field', 'Value'], orient='row')


# ── Energy balance & emissions ─────────────────────────────────────────────

def get_prepared_emissions_forecast(df_emissions: pl.DataFrame = None) -> pl.DataFrame:
    if df_emissions is None or len(df_emissions) == 0:
        return pl.DataFrame()
    relevant_columns = ['Plant name', 'Plant identifier', 'Company',
                        'Scenario', 'Emission'] + [REFERENCE_YEAR] + SCENARIO_YEARS
    return df_emissions.select(relevant_columns)


def get_prepared_energy_balance(df_forecast: pl.DataFrame = None) -> pl.DataFrame:
    if df_forecast is None or len(df_forecast) == 0:
        return pl.DataFrame()
    relevant_columns = ['Plant name', 'Plant identifier', 'Company',
                        'Scenario', 'Utility', 'Peak/Annual', 'Flow type'
                        ] + [REFERENCE_YEAR] + SCENARIO_YEARS
    return df_forecast.select(relevant_columns)


def _get_val(df: pl.DataFrame, col: str) -> float | None:
    result = df.select(pl.col(col)).head(1)
    return result[0, 0] if len(result) > 0 else None


def create_emissions_sheet(
    df: pl.DataFrame = None,
    ref_df: pl.DataFrame = None,
    plant_id: str = None,
    ref_year: int = 2024,
) -> pl.DataFrame:
    """
    Creates emissions part of the sheet.
    Demand is always None (supply-only data)
    """

    if df is None or len(df) == 0 or ref_df is None or len(ref_df) == 0:
        return pl.DataFrame(schema=META_COLS_ORDER + EMISSION_COLS_ORDER)#, "CO2", "Methane", "N2O", "F-gases", "other"])

    plant_data = (
        df.filter(pl.col("Plant identifier") == plant_id)
        .with_columns(Emission=pl.col("Emission").replace("N₂O", "N2O"))
    )

    if plant_data is None or len(plant_data) == 0:
        return pl.DataFrame(schema=META_COLS_ORDER + EMISSION_COLS_ORDER)

    reference = (
        ref_df.filter(pl.col("Plant identifier") == plant_id)
        .with_columns(Emission=pl.col("Emission").replace("N₂O", "N2O"))
        .with_columns(pl.lit("Reference").alias("Scenario"))
        .filter(pl.col("Year").cast(pl.Utf8) == str(ref_year))
    )

    # year_cols = [str(ref_year), "2030", "2035", "2040", "2050"]
    year_cols = [str(ref_year)] + SCENARIO_YEARS 

    emissions = plant_data["Emission"].unique().sort().to_list()
    strategies = plant_data["Scenario"].unique().to_list()
    # sort alphabetically so the strategies have always the same order
    strategies.sort()
    # ordered_strategies = ["Preferred"] + [s for s in strategies if s != "Preferred"]
    ordered_strategies = [i for i in STRATEGIES_ORDER if i in strategies]

    rows = []
    for year in year_cols:
        is_ref = year == str(ref_year)
        strategies_this_year = ["Reference"] if is_ref else ordered_strategies

        for strategy in strategies_this_year:
            working_df = reference if is_ref else plant_data
            row_production = [year, strategy, "production"]
            row_demand = [year, strategy, "demand"]

            for emission in emissions:
                if is_ref:
                    sub = working_df.filter(pl.col("Emission") == emission)
                    val = _get_val(sub, "Annual amount")
                else:
                    sub = working_df.filter(
                        (pl.col("Scenario") == strategy)
                        & (pl.col("Emission") == emission)
                    )
                    val = _get_val(sub, year)

                row_production.append(val)
                row_demand.append(None)  # Demand always None per spec

            rows.append(row_demand)
            rows.append(row_production)

    columns = META_COLS_ORDER + emissions

    # NOx is folded into N2O per business rule, then dropped
    return (
        pl.DataFrame(rows, schema=columns, orient='row')
        .with_columns(
            (pl.col("NOx").cast(pl.Float64).fill_null(0.0) 
             + pl.col("N2O").cast(pl.Float64).fill_null(0.0)
             ).alias("N2O")
        )

        # TODO fix this, make it dynamic
        .select(META_COLS_ORDER + STRICT_EMISSIONS_ORDER)
    )


def create_vraagenproductie_sheet(
    df_forecast: pl.DataFrame = None,
    ref_df: pl.DataFrame = None,
    plant_id: str = None,
    ref_year: int = 2024,
) -> pl.DataFrame:
    
    if df_forecast is None or len(df_forecast) == 0 or ref_df is None or len(ref_df) == 0:
        return pl.DataFrame(schema=META_COLS_ORDER + UTILITY_COLS_ORDER)# + utility_columns)

    plant_data = df_forecast.filter(pl.col("Plant identifier") == plant_id)
    reference = (
        ref_df.filter(pl.col("Plant identifier") == plant_id)
        .filter(pl.col("Year").cast(pl.Utf8) == str(ref_year))
        .with_columns(pl.lit("Reference").alias("Scenario"))
    )

    if plant_data is None or len(plant_data) == 0:
        return pl.DataFrame(schema=META_COLS_ORDER + UTILITY_COLS_ORDER)# + utility_columns)

    year_cols = [str(ref_year)] + SCENARIO_YEARS
    utilities = plant_data["Utility"].unique().sort().to_list()
    strategies = plant_data["Scenario"].unique().to_list()
    flow_types = plant_data["Flow type"].unique().to_list()
    # flow_types = [i.replace('_', ' ') for i in flow_types]

    # sort alphabetically so the strategies have always the same order
    strategies.sort()
    strategies = ["Preferred"] + [s for s in strategies if s != "Preferred"]
    strategies = [i for i in STRATEGIES_ORDER if i in strategies]

    # Build column list with Electricity_peak inserted right after Electricity
    utility_columns = []
    for u in utilities:
        utility_columns.append(u)
        if u == "Electricity":
            utility_columns.append("Electricity_peak")

    rows = []
    for year in year_cols:
        is_ref = year == str(ref_year)

        if is_ref:
            # Use canonical map from constants to guarantee consistent flow labels
            for ref_col, flow_label in REFERENCE_FLOW_COL_MAP.items():
                row = [year, "Reference", flow_label]
                for u in utilities:
                    sub = reference.filter(pl.col("Utility") == u)
                    row.append(_get_val(sub, ref_col))
                    if u == "Electricity":
                        peak_col = REFERENCE_PEAK_COL_MAP[ref_col]
                        row.append(_get_val(sub, peak_col))
                rows.append(row)
        else:
            for strategy in strategies:
                for flow in flow_types:
                    row = [year, strategy, flow.replace('_', ' ')]
                    for u in utilities:
                        sub = plant_data.filter(
                            (pl.col("Utility") == u)
                            & (pl.col("Flow type") == flow)
                            & (pl.col("Scenario") == strategy)
                        )
                        annual = sub.filter(pl.col("Peak/Annual") == "annual")
                        row.append(_get_val(annual, year))
                        if u == "Electricity":
                            peak = sub.filter(pl.col("Peak/Annual") == "peak")
                            row.append(_get_val(peak, year))
                    rows.append(row)

    columns = ["Year", "Strategy", "Flow type"] + utility_columns
    return pl.DataFrame(rows, schema=columns, orient="row")


def get_energy_balance_emissions_sheet(
    df_emissions: pl.DataFrame = None,
    df_reference_emissions: pl.DataFrame = None,
    df_forecast: pl.DataFrame = None,
    df_reference_forecast: pl.DataFrame = None,
    plant_id: str = None,
    ref_year: int = 2024,
) -> pl.DataFrame:
    
    if all(df is None or len(df) == 0 for df in [df_emissions, df_forecast, df_reference_emissions, df_reference_forecast]):
        return pl.DataFrame(schema=EMISSIES_VRAAG_COLUMN_ORDER)
    
    df_emissions_processed = get_prepared_emissions_forecast(df_emissions)
    df_forecast_processed  = get_prepared_energy_balance(df_forecast)

    emissions      = create_emissions_sheet(df_emissions_processed, df_reference_emissions, plant_id, ref_year) if len(df_emissions_processed) > 0 else pl.DataFrame()
    energy_balance = create_vraagenproductie_sheet(df_forecast_processed, df_reference_forecast, plant_id, ref_year) if len(df_forecast_processed) > 0 else pl.DataFrame()

    if len(energy_balance) == 0 and len(emissions) == 0:
        return pl.DataFrame(schema=EMISSIES_VRAAG_COLUMN_ORDER)
    
    if len(energy_balance) == 0:
        return emissions
    if len(emissions) == 0:
        return energy_balance

    result = energy_balance.join(
        emissions,
        on=['Year', 'Strategy', 'Flow type'],
        how='left',
    )

    missing_cols = [col for col in EMISSIES_VRAAG_COLUMN_ORDER if col not in result.columns]
    if missing_cols:
        result = result.with_columns([pl.lit(None).alias(col) for col in missing_cols])

    # Select all columns in canonical order
    return result.select(EMISSIES_VRAAG_COLUMN_ORDER)


# ── Projects ───────────────────────────────────────────────────────────────

def _unique_list(df: pl.DataFrame, col: str) -> list:
    """Get unique non-null values from a column as a list."""
    return df[col].drop_nulls().unique().to_list()


def get_and_check_EAN(df: pl.DataFrame, ean_col: str = "EAN code") -> str | None:
    ean_codes = _unique_list(df, ean_col)
    if len(ean_codes) == 0:
        return None
    if len(ean_codes) > 1:
        print(f"  [warn] Project has multiple EANs ({ean_codes}). Using first.")
    return str(ean_codes[0])


def get_project_details(projects_df: pl.DataFrame, plant_id: str) -> pl.DataFrame:
    projects_df_aux = projects_df.filter(pl.col("Plant identifier") == plant_id)
    if len(projects_df_aux) == 0:
        return pl.DataFrame(schema=PROJECT_DETAILS_ORDER + ["EAN", "CO2"])

    projects = _unique_list(projects_df_aux, "Project name")

    rows = []
    for project in projects:
        proj = projects_df_aux.filter(pl.col("Project name") == project)
        proj_details = list(proj.head(1).select(PROJECT_DETAILS_COLS).row(0))
        ean = get_and_check_EAN(proj)

        # CO2 annual emission — filter for CO2 row, take Annual emission value
        co2_val = _get_val(
            proj.filter(pl.col("Emission") == "CO2"),
            "Annual emission"
        )

        rows.append(proj_details + [ean, co2_val])

    aux_projects = pl.DataFrame(
        rows,
        schema=PROJECT_DETAILS_COLS + ["EAN", "CO2"],
        orient="row",
    )

    for scenario in STRATEGIES_ORDER[2:]:
        aux_projects = aux_projects.with_columns(
            pl.col("Associated Scenarios")
            .fill_null("")
            .str.contains(scenario, literal=True)
            .alias(f"Part of {scenario} scenario")
        )

    return aux_projects



def get_project_values(projects_df: pl.DataFrame, plant_id: str) -> pl.DataFrame:
    projects_df_aux = projects_df.filter(pl.col("Plant identifier") == plant_id)

    if len(projects_df_aux) == 0:
        return pl.DataFrame(schema = ["Project name", "Type"] + greenhouse_cols + UTILITY_COLS_ORDER)

    projects = _unique_list(projects_df_aux, "Project name")

    rows = []
    for project in projects:
        working_df = projects_df_aux.filter(
            (pl.col("Project name") == project)
            & (pl.col("Utility").is_in(greenhouse_cols + asking_cols))
        )

        for value_type in value_rows:
            row = [project, value_type]

            for col in greenhouse_cols:
                sub = working_df.filter(pl.col("Utility") == col)
                row.append(_get_val(sub, value_to_cols_dict[value_type]))

            for col in asking_cols:
                if col == "Electricity_peak":
                    sub = working_df.filter(pl.col("Utility") == "Electricity")
                    row.append(_get_val(sub, value_to_cols_electricity_MW_dict[value_type]))
                else:
                    sub = working_df.filter(pl.col("Utility") == col)
                    row.append(_get_val(sub, value_to_cols_dict[value_type]))

            rows.append(row)

    # Use greenhouse_cols + asking_cols which now share order with energy_emissions_cols
    columns = ["Project name", "Type"] + greenhouse_cols + UTILITY_COLS_ORDER
    return pl.DataFrame(rows, schema=columns, orient="row")


def get_project_sheet(
    df_emissions: pl.DataFrame = None,
    df_utilities: pl.DataFrame = None,
    plant_id: str = None,
) -> pl.DataFrame:
    
    df_emissions = df_emissions.filter(pl.col('Plant identifier') == plant_id)
    df_utilities = df_utilities.filter(pl.col('Plant identifier') == plant_id)

    # if df_emissions is None or len(df_emissions) == 0:
    #     if df_utilities is None or len(df_utilities) == 0:
    #         return pl.DataFrame()
    #     # return get_project_values(df_utilities, plant_id)
    #     df_emissions = df_utilities.with_columns([pl.lit('').alias('Emission'), pl.lit('0').alias('Annual emission')])
    
    # if df_utilities is None or len(df_utilities) == 0:
    #     return get_project_details(df_emissions, plant_id)

    res_emissions = get_project_details(df_emissions, plant_id)
    res_utilities = get_project_values(df_utilities, plant_id)

    # Cast Project name to string to handle null type issues
    res_emissions = res_emissions.with_columns(
        pl.col('Project name').cast(pl.Utf8)
    )
    res_utilities = res_utilities.with_columns(
        pl.col('Project name').cast(pl.Utf8)
    )


    joined = res_utilities.join(res_emissions, on='Project name', how='left')
    # Put detail cols first, then value cols, deduplicating any overlaps
    return joined.select(
        list(dict.fromkeys(res_emissions.columns + res_utilities.columns))
    ).sort('Project name')


# ── Simple sheets (production / storage / flexibility) ────────────────────

_COMMON_DROP = ["Plant", "Plant identifier", "Company", "Version date"]

def _get_simple_sheet(df: pl.DataFrame, plant_id: str,
                      extra_drop: list[str] = []) -> pl.DataFrame:
    drop_cols = [c for c in _COMMON_DROP + extra_drop if c in df.columns]
    return (
        df.filter(pl.col("Plant identifier") == plant_id)
        .drop(drop_cols)
        .sort("Year")
    )

def get_production_sheet(df: pl.DataFrame, plant_id: str) -> pl.DataFrame:
    return _get_simple_sheet(df, plant_id, extra_drop=["Secondary fuel ratio (%)"])

def get_storage_sheet(df: pl.DataFrame, plant_id: str) -> pl.DataFrame:
    return _get_simple_sheet(df, plant_id)

def get_flexibility_sheet(df: pl.DataFrame, plant_id: str) -> pl.DataFrame:
    return _get_simple_sheet(df, plant_id)