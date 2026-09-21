"""
Curves Utils - process cluster/sector energy demand curves (used for the
##new_cc_siteN## custom-site pathway).
"""

import polars as pl

from .constants import SCENARIO_YEARS
from .string_utils import fix_column


def get_aggregated_curves(
    excel_path: str = None,
    sheet_name: str = 'resultaat',
    curves: pl.DataFrame = None,
    all_years: list = SCENARIO_YEARS,
) -> pl.DataFrame:
    """
    Read raw cluster/sector curves and aggregate to
    Cluster, Sector, Scenario, Energiedrager, <year columns>.
    """
    if excel_path is not None:
        curves = pl.read_excel(excel_path, sheet_name=sheet_name)

    curves = curves.with_columns(
        pl.col("Cluster").str.to_lowercase().replace('overig', 'cluster 6').alias('Cluster')
    )

    for col in ['Cluster', 'Sector']:
        curves = fix_column(curves, col)

    curves = curves.with_columns(pl.col('Energiedrager').str.to_lowercase())

    sums = curves.group_by(
        ['Cluster', 'Sector', 'Scenario', 'Energiedrager']
    ).agg(
        [pl.col(i).sum() for i in all_years]
    ).sort(['Cluster', 'Sector', 'Scenario', 'Energiedrager'])

    energidragers_map = {
        'elektriciteit': 'electricity',
        'gas': 'natural_gas',
        'waterstof': 'hydrogen_(>98%_vol%)',
        'Oil and oil products': 'oil_and_oil_products',
    }

    sums = sums.with_columns([
        pl.col("Energiedrager").str.to_lowercase().replace(energidragers_map).alias('Utility'),
        pl.lit('demand').alias('Flow type'),
    ]).drop('Energiedrager')

    return sums


def reshape_cluster_sector_curves(
    curves_df: pl.DataFrame,
    year_cols: list = SCENARIO_YEARS,
) -> pl.DataFrame:
    """
    Reshape from wide (years as columns) to long format.

    In:  Cluster, Sector, Scenario, 2024, 2030, ..., Utility, Flow type
    Out: Cluster, Sector, Scenario, Year, Value, Utility, Flow type
    """
    id_cols = ['Cluster', 'Sector', 'Scenario', 'Utility', 'Flow type']
    year_cols = [col for col in year_cols if col in curves_df.columns]

    long_df = curves_df.unpivot(
        index=id_cols,
        on=year_cols,
        variable_name='Year',
        value_name='Value',
    )

    return long_df.with_columns(pl.col('Year').cast(pl.Utf8))


def get_final_cluster_sector_curves(
    excel_path: str = None,
    sheet_name: str = 'resultaat',
    curves_df: pl.DataFrame = None,
    years: list[str] = SCENARIO_YEARS,
) -> pl.DataFrame:
    """Read + aggregate + reshape cluster/sector curves in one call."""
    init_curves = get_aggregated_curves(
        excel_path=excel_path, sheet_name=sheet_name, curves=curves_df, all_years=years
    )
    return reshape_cluster_sector_curves(init_curves, years)
