import polars as pl
import pandas as pd
import json
import os
import re
import io
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import logging
import geopandas as gpd
from pathlib import Path
from typing import Literal
import xlsxwriter
import streamlit as st

from .constants import PATH_PERSISTENTS, CTM_TO_REGIO_SECTOR

print(PATH_PERSISTENTS)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("geocode")

geolocator = Nominatim(user_agent="my_geocoder")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

# Rough NL bounding box (incl. Wadden islands, excl. Caribbean NL)
NL_LAT_MIN, NL_LAT_MAX = 50.75, 53.7
NL_LON_MIN, NL_LON_MAX = 3.2, 7.22

def in_netherlands(lat, lon):
    if lat is None or lon is None:
        return False
    return NL_LAT_MIN <= lat <= NL_LAT_MAX and NL_LON_MIN <= lon <= NL_LON_MAX

def geocode_row(address, zip_code, city):
    parts = [p for p in [address, zip_code, city, 'Netherlands'] if p]
    if not parts:
        return (None, None)
    query = ", ".join(parts)
    try:
        loc = geocode(query)
        return (loc.latitude, loc.longitude) if loc else (None, None)
    except Exception as e:
        log.info(f"  geocode error for '{query}': {e}")
        return (None, None)

def fix_coords(df: pl.DataFrame, log_container=None) -> pl.DataFrame:
    n_missing = 0
    n_bad = 0
    n_regeocoded = 0
    n_nulled = 0
    n_bad_no_address = 0

    lats, lons = [], []

    def log_message(msg: str):
        print(msg)
        if log_container:
            log_container.write(msg)

    for row in df.iter_rows(named=True):
        lat, lon = row["Latitude"], row["Longitude"]
        address, zip_code, city = row["Address"], row["Zip code"], row["City"]
        plant = row.get("Plant name") or row.get("Plant identifier")
        has_address = bool(address or zip_code or city)

        if lat is None or lon is None:
            n_missing += 1
            if has_address:
                new_lat, new_lon = geocode_row(address, zip_code, city)
                if in_netherlands(new_lat, new_lon):
                    log_message(f"[MISSING->FOUND] {plant}: -> ({new_lat}, {new_lon})")
                    lat, lon = new_lat, new_lon
                    n_regeocoded += 1
                else:
                    log_message(f"[MISSING->STILL MISSING] {plant}: no valid geocode")
                    lat, lon = None, None
            else:
                lat, lon = None, None

        elif not in_netherlands(lat, lon):
            n_bad += 1
            if has_address:
                new_lat, new_lon = geocode_row(address, zip_code, city)
                if in_netherlands(new_lat, new_lon):
                    log_message(f"[BAD->FIXED] {plant}: ({lat}, {lon}) -> ({new_lat}, {new_lon})")
                    lat, lon = new_lat, new_lon
                    n_regeocoded += 1
                else:
                    log_message(f"[BAD->NULLED] {plant}: ({lat}, {lon}) -> could not confirm NL coords, setting None")
                    lat, lon = None, None
                    n_nulled += 1
            else:
                log_message(f"[BAD->NULLED, NO ADDRESS] {plant}: ({lat}, {lon}) -> no address to re-geocode, setting None")
                lat, lon = None, None
                n_bad_no_address += 1
                n_nulled += 1

        lats.append(lat)
        lons.append(lon)

    df = df.with_columns([
        pl.Series("Latitude", lats),
        pl.Series("Longitude", lons),
    ])

    log_message("---- Summary ----")
    log_message(f"Missing coords:        {n_missing}")
    log_message(f"Out-of-NL coords:      {n_bad}  (of which no address: {n_bad_no_address})")
    log_message(f"Re-geocoded OK:        {n_regeocoded}")
    log_message(f"Set to None,None:      {n_nulled}")

    return df

# df = fix_coords(df)

def get_plants_missing_coords(df):
    return df.filter(
        pl.col("Latitude").is_null() | pl.col("Longitude").is_null() 
        ).select('Plant name').to_series().to_list()


def load_geo_file(file_path: str, layer:str='buurten') -> gpd.GeoDataFrame:
    return gpd.read_file(file_path, layer=layer)


def transform_df_to_geo(df: pl.DataFrame) -> gpd.GeoDataFrame:
    '''
    Transform the plant_data df to geopandas dataframe
    '''

    plant_data = df.to_pandas()
    plant_geo = gpd.GeoDataFrame(
        pd.DataFrame(plant_data),
        geometry=gpd.points_from_xy(
            plant_data["Longitude"],
            plant_data["Latitude"]
        ),
        crs="EPSG:4326"
    )
    return plant_geo


def add_buurtcode_to_plantcoords(plant_df:str, buurt_file_gpkg:str):
    buurt_df = load_geo_file(buurt_file_gpkg)
    plant_geo_df = transform_df_to_geo(plant_df)
    plant_geo_df = plant_geo_df.to_crs(buurt_df.crs)

    res = gpd.sjoin(
        plant_geo_df,
        buurt_df[["buurtcode", "buurtnaam", "geometry"]],
        how="left",
        predicate="intersects"
    )

    return res


def get_new_zip_to_buurt_mapping(buurt_gdf, zip_gdf) -> pl.DataFrame:

    zip_gdf = zip_gdf.to_crs(buurt_gdf.crs)
    
    joined = gpd.overlay(zip_gdf[['postcode6', 'geometry']], buurt_gdf[["buurtcode", "buurtnaam", "geometry"]], how="intersection", keep_geom_type=False)
    joined["overlap_area"] = joined.geometry.area

    # pick the buurt with the largest overlap per zip code
    best_match = joined.loc[joined.groupby("postcode6")["overlap_area"].idxmax()].reset_index(drop=True)[['postcode6', 'buurtcode', 'buurtnaam']]
    match_df = pl.from_pandas(pd.DataFrame(best_match))
    return match_df


def add_grid_provider_types(df: pl.DataFrame) -> pl.DataFrame:
    def get_provider_types(value):
        if not value:
            return None, None

        # Handle empty elements in the source
        value = re.sub(r",\s*,", ",", value)

        try:
            items = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None, None

        electricity = None
        gas = None

        for item in items:
            provider = item.get("grid_operator")
            utility = item.get("utility_name")

            if not provider:
                continue

            if utility == "Electricity":
                if provider.lower() == "tennet":
                    electricity = "TSO"
                elif electricity is None:
                    electricity = "DSO"

            elif utility == "Natural Gas":
                if provider.upper() == "GTS":
                    gas = "TSO"
                elif gas is None:
                    gas = "DSO"

        return electricity, gas

    return df.with_columns(
        pl.col("All EANs")
        .map_elements(
            get_provider_types,
            return_dtype=pl.Struct([
                pl.Field("provider_electricity", pl.String),
                pl.Field("provider_gas", pl.String),
            ]),
        )
        .alias("_provider_types")
    ).unnest("_provider_types")


def file_exists(file_path) -> bool:
    return Path(file_path).exists()

def get_col_names_from_type(data_type: Literal['coordinates', 'providers']):
    if data_type == 'coordinates':
        col1 = 'Latitude'
        col2 = 'Longitude'
    else:
        col1 = 'provider_energy'
        col2 = 'provider_gas'
    return col1, col2

def join_dfs(
    df1: pl.DataFrame,
    df2: pl.DataFrame,
    data_type: Literal["coordinates", "providers"],
) -> pl.DataFrame:

    col1, col2 = get_col_names_from_type(data_type)

    result = df1.join(
        df2.select(["Plant identifier", col1, col2]),
        on="Plant identifier",
        how="left",
        suffix="_2",
    )

    for col in [col1, col2]:
        persistent_col = pl.col(f"{col}_2")

        if data_type == "coordinates":
            valid = persistent_col.is_not_null() & persistent_col.is_not_nan()
        else:
            valid = (
                persistent_col.is_not_null()
                & (persistent_col.str.strip_chars() != "")
            )

        result = result.with_columns(
            pl.when(valid)
            .then(persistent_col)
            .otherwise(pl.col(col))
            .alias(col)
        )

    return result.drop([f"{col1}_2", f"{col2}_2"])


def overwrite_df_with_persistent_vals(init_df: pl.DataFrame, data_type: Literal['coordinates', 'providers']) -> pl.DataFrame:
    if file_exists(PATH_PERSISTENTS[data_type]):
        df2 = pl.read_csv(PATH_PERSISTENTS[data_type])
        if df2.is_empty():
            return init_df
        return join_dfs(init_df, df2, data_type)
    else:
        return init_df   

def merge_for_persistent_save(
    new_df: pl.DataFrame,
    persistent_df: pl.DataFrame,
    data_type: Literal["coordinates", "providers"],
) -> pl.DataFrame:
    """
    Merge freshly edited/generated data with the existing persistent file
    for SAVING. New values win when present; old persistent values are kept
    for plants not touched in this session.

    Unlike join_dfs/overwrite_df_with_persistent_vals (which are for LOADING
    and correctly prefer persistent values), this keeps the union of both
    plant sets and prefers the NEW data -- reusing the load-time merge here
    was the bug: it silently discarded edits (old always won) and dropped
    any plant not present in the df being saved (write_csv overwrote the
    whole file with just that subset).
    """
    col1, col2 = get_col_names_from_type(data_type)

    new_df = new_df.select(["Plant identifier", col1, col2])
    persistent_df = persistent_df.select(["Plant identifier", col1, col2])

    result = new_df.join(
        persistent_df,
        on="Plant identifier",
        how="full",
        coalesce=True,
        suffix="_old",
    )

    for col in [col1, col2]:
        new_col = pl.col(col)
        old_col = pl.col(f"{col}_old")

        if data_type == "coordinates":
            new_valid = new_col.is_not_null() & new_col.is_not_nan()
        else:
            new_valid = new_col.is_not_null() & (new_col.str.strip_chars() != "")

        result = result.with_columns(
            pl.when(new_valid).then(new_col).otherwise(old_col).alias(col)
        )

    return result.select(["Plant identifier", col1, col2])


def append_to_persistent_file(
    df: pl.DataFrame,
    data_type: Literal["coordinates", "providers"],
):
    col1, col2 = get_col_names_from_type(data_type)

    if file_exists(PATH_PERSISTENTS[data_type]):
        persistent_df = pl.read_csv(PATH_PERSISTENTS[data_type])
        final_df = (
            merge_for_persistent_save(df, persistent_df, data_type)
            if not persistent_df.is_empty()
            else df.select(["Plant identifier", col1, col2])
        )
    else:
        final_df = df.select(["Plant identifier", col1, col2])

    final_df.write_csv(PATH_PERSISTENTS[data_type])


def delete_persistent_file(data_type: Literal['coordinates', 'provider']):
    if file_exists(PATH_PERSISTENTS[data_type]):
        os.remove(PATH_PERSISTENTS[data_type])
        st.info(f'Deleted file at {PATH_PERSISTENTS[data_type]}')


def get_available_mapping_versions(dir_path='src/REGIONALIZATION/ref_data/buurt_mapping'):

    directory = Path(dir_path)
    files = list(directory.rglob("*.gpkg"))
    files = [str(f).split('/')[-1] for f in files]

    return files

def get_final_plant_mapping(df_provider: pl.DataFrame, df_buurt:pl.DataFrame) -> pl.DataFrame:
    res = df_provider.select(['Plant identifier', 'Plant name','provider_electricity', 'provider_gas']).join(
        df_buurt.select(['Plant identifier', 'buurtcode', 'buurtnaam']),
        on='Plant identifier',
        how='full'
    ).drop('Plant identifier_right')
    return res


def read_and_save_regio_categories(path_excel: str, 
                                 save_path:str = 'src/REGIONALIZATION/ref_data/categories/', 
                                 header_row:int=1):
    overview = pl.read_excel(path_excel,
                            columns= [0, 1, 2, 3],
                            read_options={"header_row": header_row}
                        )

    overview.write_csv(f'{save_path}/overview_categories.csv')
    return overview

def get_overview_categories() -> pl.DataFrame:
    if os.path.isfile('src/REGIONALIZATION/ref_data/categories/overview_categories.csv'):
        return pl.read_csv('src/REGIONALIZATION/ref_data/categories/overview_categories.csv')
    else:
        return read_and_save_regio_categories(path_excel='src/REGIONALIZATION/ref_data/categories/Regionalization_categories_overview_copy.xlsx')
    

# ═══════════════════════════════════════════════════════════════════════
# Step 1: tidy (long-format) table
# ═══════════════════════════════════════════════════════════════════════
 
# def build_regionalization_electricity_demand(
#     plant_data: dict[str, pl.DataFrame],  # keyed by Plant identifier
#     location_df: pl.DataFrame,             # Plant identifier, Plant name, provider_electricity, provider_gas, buurtcode, buurtnaam
# ) -> pl.DataFrame:
#     """
#     Tidy electricity-demand-by-site table for regionalization.
#     Restricted to Flow type == 'demand'. One row per (Plant identifier, Scenario, Year).
#     """
#     rows = []
 
#     for plant_id, df in plant_data.items():
#         demand = df.filter(pl.col("Flow type") == "demand").select([
#             "Scenario", "Year", "Electricity", 'CO2', 'Hydrogen ( >98% vol.%) (LHV)', "Heat", "Sector", "Cluster", "Plant name",
#         ])
#         if demand.is_empty():
#             continue
#         demand = demand.with_columns(pl.lit(plant_id).str.split('__').list.first().alias("Plant identifier"))
#         rows.append(demand)
 
#     if not rows:
#         return pl.DataFrame()
 
#     combined = pl.concat(rows, how="vertical_relaxed")
 
#     result = combined.join(
#         location_df.select(["Plant identifier", "provider_electricity", "buurtcode", "buurtnaam"]),
#         on="Plant identifier",
#         how="left",  # keeps plants with missing location; buurtcode/buurtnaam land null
#     )
 
#     missing = (
#         result.filter(pl.col("buurtcode").is_null())
#         .select("Plant name").unique().to_series().to_list()
#     )
#     if missing:
#         print(f"[WARN] {len(missing)} plant(s) missing location data: {missing}")
 
#     result = result.with_columns([
#         pl.lit("Electricity").alias("Carrier"),
#         pl.lit("Demand").alias("Type"),
#         pl.col("provider_electricity").alias("Level"),
#         (pl.lit("Industry_") + pl.col("Sector")).alias("ID"),
#     ])
#     print(result)
 
#     return result.select([
#         "Plant identifier", "Plant name", "Sector", "Cluster",
#         "buurtcode", "buurtnaam",
#         "Scenario", "Year", "Carrier", "Level", "Type", "ID",
#         "Electricity",
#     ])
 

def _extract_carrier_rows(df: pl.DataFrame, source_col: str, flow_types: list[str], type_label: str) -> pl.DataFrame:
    """
    Filter df to the given DSH flow type(s) and pull one value column out.
    When flow_types has more than one entry (demand + captive use), sum them
    per (Scenario, Year, Sector, Cluster, Plant name) -- they're two
    components of the same final demand, not independent figures.
    """
    if source_col not in df.columns:
        return pl.DataFrame()

    subset = df.filter(pl.col("Flow type").is_in(flow_types)).select([
        "Scenario", "Year", "Sector", "Cluster", "Plant name", source_col,
    ])
    if subset.is_empty():
        return pl.DataFrame()

    if len(flow_types) > 1:
        subset = subset.group_by(["Scenario", "Year", "Sector", "Cluster", "Plant name"]).agg(
            pl.col(source_col).sum()
        )

    return subset.rename({source_col: "Value"}).with_columns(pl.lit(type_label).alias("Type"))


def build_regionalization_tidy_tables(
    plant_data: dict[str, pl.DataFrame],  # loaded with aggregate_flow_types=False -- see note above
    location_df: pl.DataFrame,
) -> dict[str, pl.DataFrame]:
    """
    One tidy long-format table per carrier:
        Electricity  -- Demand (demand+captive use) + Flexibility (source col 'PtH')
        Heat         -- Demand (source col 'Heat', flow type 'supply')
        Hydrogen     -- Demand (demand+captive use) + Supply
        Methane      -- Demand (demand+captive use) + Supply (source col 'Natural Gas')
        CO2          -- Demand (demand+captive use) + Supply

    Level rules:
        Electricity -> location_df.provider_electricity
        Methane     -> location_df.provider_gas
        Heat        -> location_df.provider_gas (copies Methane's connection type)
        Hydrogen    -> literal "TSO" (assumed)
        CO2         -> literal "TSO" (assumed)
    """
    CARRIER_SOURCES = {
        "Electricity": [
            ("Electricity", ["demand", "captive use"], "Demand"),
            ("PtH", ["flexibility"], "Flexibility"),
        ],
        "Heat": [
            ("Heat", ["supply"], "Demand"),
        ],
        "Hydrogen": [
            ("Hydrogen ( >98% vol.%) (LHV)", ["demand", "captive use"], "Demand"),
            ("Hydrogen ( >98% vol.%) (LHV)", ["supply"], "Supply"),
        ],
        "Methane": [
            ("Natural Gas", ["demand", "captive use"], "Demand"),
            ("Natural Gas", ["supply"], "Supply"),
        ],
        "CO2": [
            ("CO2", ["demand", "captive use"], "Demand"),
            ("CO2", ["supply"], "Supply"),
        ],
    }

    CARRIER_LEVEL_RULES = {
        "Electricity": ("column", "provider_electricity"),
        "Methane": ("column", "provider_gas"),
        "Heat": ("column", "provider_gas"),
        "Hydrogen": ("literal", "TSO"),
        "CO2": ("literal", "TSO"),
    }

    results: dict[str, pl.DataFrame] = {}

    for carrier, sources in CARRIER_SOURCES.items():
        rows = []

        for plant_key, df in plant_data.items():
            plant_id = str(plant_key).split('__')[0]

            for source_col, flow_types, type_label in sources:
                extracted = _extract_carrier_rows(df, source_col, flow_types, type_label)
                if extracted.is_empty():
                    continue
                rows.append(extracted.with_columns(pl.lit(plant_id).alias("Plant identifier")))

        if not rows:
            results[carrier] = pl.DataFrame()
            continue

        combined = pl.concat(rows, how="vertical_relaxed").with_columns(pl.lit(carrier).alias("Carrier"))

        rule_type, rule_value = CARRIER_LEVEL_RULES[carrier]
        location_cols = ["Plant identifier", "buurtcode", "buurtnaam"]
        if rule_type == "column":
            location_cols.insert(1, rule_value)

        result = combined.join(
            location_df.select(location_cols),
            on="Plant identifier",
            how="left",
        )

        missing = (
            result.filter(pl.col("buurtcode").is_null())
            .select("Plant name").unique().to_series().to_list()
        )
        if missing:
            print(f"[WARN] {carrier}: {len(missing)} plant(s) missing location data: {missing}")

        result = result.with_columns(
            pl.col(rule_value).alias("Level") if rule_type == "column" else pl.lit(rule_value).alias("Level")
        )

        results[carrier] = result.select([
            "Plant identifier", "Plant name", "Sector", "Cluster",
            "buurtcode", "buurtnaam",
            "Scenario", "Year", "Carrier", "Level", "Type",
            "Value",
        ])

    return results

# ═══════════════════════════════════════════════════════════════════════
# Step 2: column groups, driven by categories_overview.csv
# ═══════════════════════════════════════════════════════════════════════

def load_category_groups(categories_df: pl.DataFrame) -> pl.DataFrame:
    """
    Normalize categories_overview.csv into the shape used to build the Excel
    header. The CSV's own column names don't match ours:
        'Energy carrier' -> Carrier
        'Type'           -> Level   (DSO/TSO)
        'Sector'         -> Type    (Demand/Flexibility)
        'Category'       -> ID      (e.g. "Industry_chemicals_PtH")
    Sector (display, e.g. "chemicals") and the PtH flag are both derived
    from Category/ID.
    """
    return categories_df.rename({
        "Energy carrier": "Carrier",
        "Type": "Level",
        "Sector": "Type",
        "Category": "ID",
    }).with_columns([
        pl.col("ID").str.contains("_PtH").alias("PtH"),
        pl.col("ID").str.replace(r"^Industry_", "").str.replace(r"_PtH$", "").alias("Sector"),
    ])


def build_column_groups(
    tidy_df: pl.DataFrame,
    categories_df: pl.DataFrame,
    selected_scenarios: list[str],
    selected_years: list[str],
) -> list[dict]:
    """
    Build the Excel column groups from categories_overview.csv.
    Any sector in the plant data not present in the overview maps to "other".
    """
    category_groups = load_category_groups(categories_df)

    tidy_df = tidy_df.with_columns(
        pl.col("Sector").replace_strict(CTM_TO_REGIO_SECTOR, default="other").alias("Sector")
    )

    scenario_years = (
        tidy_df
        .filter(pl.col("Scenario").is_in(selected_scenarios) & pl.col("Year").is_in(selected_years))
        .select(["Scenario", "Year"])
        .unique()
    )

    all_groups = scenario_years.join(category_groups, how="cross")

    has_other = (
        tidy_df
        .filter(
            pl.col("Scenario").is_in(selected_scenarios)
            & pl.col("Year").is_in(selected_years)
            & (pl.col("Sector") == "other")
        )
        .height > 0
    )

    if has_other:
        other_templates = (
            category_groups
            .select(["Carrier", "Level", "Type"])
            .unique()
            .with_columns([
                pl.lit("other").alias("Sector"),
                pl.lit("Industry_other").alias("ID"),
            ])
        )
        other_groups = scenario_years.join(other_templates, how="cross")
        all_groups = pl.concat([all_groups, other_groups], how="diagonal_relaxed")

    return all_groups.sort(["Scenario", "Year", "Sector", "Level", "Type", "ID"]).to_dicts()

# ═══════════════════════════════════════════════════════════════════════
# Step 3: merged-header Excel writer
# ═══════════════════════════════════════════════════════════════════════

def _write_grouped_header(worksheet, row_idx, start_col, col_groups, label_key, fmt, group_keys=None):
    """
    Write a header row, merging consecutive columns that share the same
    value for `group_keys` (defaults to [label_key]). Requires col_groups
    sorted so matching group_keys are contiguous.
    """
    if group_keys is None:
        group_keys = [label_key]

    i = 0
    n = len(col_groups)
    while i < n:
        j = i
        current = tuple(col_groups[i][k] for k in group_keys)
        while j + 1 < n and tuple(col_groups[j + 1][k] for k in group_keys) == current:
            j += 1

        span = j - i + 1
        col = start_col + i
        text = col_groups[i][label_key]

        if span > 1:
            worksheet.merge_range(row_idx, col, row_idx, col + span - 1, text, fmt)
        else:
            worksheet.write(row_idx, col, text, fmt)

        i = j + 1


def _write_plain_header(worksheet, row_idx, start_col, col_groups, label_key, fmt):
    """Write a header row with NO merging -- one value per column, always."""
    for i, group in enumerate(col_groups):
        worksheet.write(row_idx, start_col + i, group[label_key], fmt)


def write_regionalization_excel(
    tidy_tables: dict[str, pl.DataFrame],
    categories_df: pl.DataFrame,
    selected_scenarios: list[str],
    selected_years: list[str],
) -> bytes:
    """
    New layout: CHECKSUM / SCENARIO / YEAR / CARRIER / LEVEL / TYPE / ID
    header rows (no separate Sector/PtH rows -- ID is the raw Category
    string, e.g. "Industry_food_PtH"), Plant identifier / Plant name /
    BU2023_CODE / BU2023_NAME as the leading row-identity columns.
    """
    combined_tidy = pl.concat(
        [df for df in tidy_tables.values() if not df.is_empty()],
        how="diagonal_relaxed",
    )
    combined_tidy = combined_tidy.with_columns(
        pl.col("Sector").replace_strict(CTM_TO_REGIO_SECTOR, default="other").alias("Sector")
    )

    col_groups_all = build_column_groups(
        combined_tidy, categories_df,
        selected_scenarios=selected_scenarios, selected_years=selected_years,
    )

    carriers = sorted(categories_df.select(pl.col('Energy carrier')).unique().to_series().to_list())

    buffer = io.BytesIO()
    with xlsxwriter.Workbook(buffer) as workbook:
        header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "border": 1})
        label_format = workbook.add_format({"bold": True, "border": 1})
        site_header_format = workbook.add_format({
            "bold": True, "bg_color": "#1F4E78", "font_color": "white", "border": 1,
        })
        carrier_format = workbook.add_format({"bold": True, "align": "center", "bg_color": "#FF0000", "border": 1})
        checksum_format = workbook.add_format({"bold": True, "align": "center", "bg_color": "#FFFF00", "border": 1})

        for carrier in carriers:
            col_groups = [g for g in col_groups_all if g["Carrier"] == carrier]
            if not col_groups:
                continue

            tidy_df = combined_tidy.filter(pl.col("Carrier") == carrier)

            ws = workbook.add_worksheet(carrier)

            PLANT_ID_COL, PLANT_NAME_COL, BU_CODE_COL, BU_NAME_COL = 0, 1, 2, 3
            LABEL_COL = 4
            DATA_START_COL = LABEL_COL + 1

            ROW_CHECKSUM, ROW_SCENARIO, ROW_YEAR = 0, 1, 2
            ROW_CARRIER, ROW_LEVEL, ROW_TYPE, ROW_ID = 3, 4, 5, 6
            DATA_START_ROW = ROW_ID + 1

            sites = (
                tidy_df.select(["Plant identifier", "Plant name", "buurtcode", "buurtnaam"])
                .unique().sort("Plant name")
                if not tidy_df.is_empty() else pl.DataFrame()
            )
            n_sites = len(sites)

            ws.write(ROW_CHECKSUM, LABEL_COL, "CHECKSUM", label_format)
            ws.write(ROW_SCENARIO, LABEL_COL, "SCENARIO", label_format)
            ws.write(ROW_YEAR, LABEL_COL, "YEAR", label_format)
            ws.write(ROW_CARRIER, LABEL_COL, "CARRIER", label_format)
            ws.write(ROW_LEVEL, LABEL_COL, "LEVEL", label_format)
            ws.write(ROW_TYPE, LABEL_COL, "TYPE", label_format)
            ws.write(ROW_ID, LABEL_COL, "ID", label_format)

            ws.write(ROW_ID, PLANT_ID_COL, "Plant identifier", site_header_format)
            ws.write(ROW_ID, PLANT_NAME_COL, "Plant name", site_header_format)
            ws.write(ROW_ID, BU_CODE_COL, "BU2023_CODE", site_header_format)
            ws.write(ROW_ID, BU_NAME_COL, "BU2023_NAME", site_header_format)

            for i, group in enumerate(col_groups):
                col = DATA_START_COL + i
                ws.write(ROW_SCENARIO, col, group["Scenario"], header_format)
                ws.write(ROW_YEAR, col, group["Year"], header_format)
                ws.write(ROW_CARRIER, col, group["Carrier"], carrier_format)
                ws.write(ROW_LEVEL, col, group["Level"], header_format)
                ws.write(ROW_TYPE, col, group["Type"], header_format)

                header_text = f"{group['Type']}_{group['ID']}_{group['Level']}_{group['Scenario']}{group['Year']}"
                ws.write(ROW_ID, col, header_text, header_format)

                if n_sites > 0:
                    data_col_letter = xlsxwriter.utility.xl_col_to_name(col)
                    first_row, last_row = DATA_START_ROW + 1, DATA_START_ROW + n_sites
                    ws.write_formula(
                        ROW_CHECKSUM, col,
                        f"=SUM({data_col_letter}{first_row}:{data_col_letter}{last_row})",
                        checksum_format,
                    )
                else:
                    ws.write(ROW_CHECKSUM, col, 0, checksum_format)

            if tidy_df.is_empty():
                continue

            value_lookup = {
                (r["Plant name"], r["Scenario"], r["Year"], r["Sector"], r["Level"], r["Type"]): r["Value"]
                for r in tidy_df.to_dicts()
            }

            for r, site in enumerate(sites.to_dicts()):
                row = DATA_START_ROW + r
                ws.write(row, PLANT_ID_COL, site["Plant identifier"])
                ws.write(row, PLANT_NAME_COL, site["Plant name"])
                ws.write(row, BU_CODE_COL, site["buurtcode"])
                ws.write(row, BU_NAME_COL, site["buurtnaam"])

                for i, group in enumerate(col_groups):
                    col = DATA_START_COL + i
                    value = value_lookup.get(
                        (site["Plant name"], group["Scenario"], group["Year"], group["Sector"], group["Level"], group["Type"])
                    )
                    if value is not None:
                        ws.write(row, col, value)

    buffer.seek(0)
    return buffer.getvalue()


def build_regionalization_excel(
    plant_data: dict[str, pl.DataFrame],
    location_df: pl.DataFrame,
    categories_df: pl.DataFrame,
    selected_scenarios: list[str], 
    selected_years: list[str]
) -> bytes:
    """Convenience: tidy table -> merged-header Excel bytes, in one call."""
    tidy_dict = build_regionalization_tidy_tables(plant_data, location_df)
    return write_regionalization_excel(tidy_dict, categories_df, selected_scenarios, selected_years)

