import polars as pl
import pandas as pd
import json
import os
import re
import glob
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import logging
import geopandas as gpd
from pathlib import Path
from typing import Literal
import streamlit as st

from .constants import PATH_PERSISTENTS

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

        