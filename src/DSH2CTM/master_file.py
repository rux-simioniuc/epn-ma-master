import polars as pl
import pandas as pd


from .utils import parse_All_EANs
from main import load_data

def prep_emission_reference(df:pl.DataFrame, REF_YEAR:str='2024'):
    df = (
        df.select(
        ['Plant', 'Plant identifier', 'Cluster','Emission', 'Year', 'Annual amount'])
            .filter(pl.col('Year').cast(pl.Utf8) == REF_YEAR)
            .rename({'Annual amount' : 'Value'})
            .pivot('Emission', index=['Plant identifier', 'Plant', 'Cluster', 'Year'], values='Value')
            .with_columns(pl.lit("Reference").alias("Scenario"))
            .with_columns(pl.lit('production').alias('Flow type'))
            .with_columns(
                        (pl.col("NOx").cast(pl.Float64).fill_null(0.0) 
                         + pl.col("N2O").cast(pl.Float64).fill_null(0.0)
                         ).alias("N2O")
                    )
            .drop(['NOx'])
    )

    return df

def prep_emission_forecast(df:pl.DataFrame, YEARS:list[str] = ['2024', '2030', '2035', '2040', '2050']):
    df = (
        df.drop(['Company', 'Version date'])
        .unpivot(YEARS, index = ['Plant name', 'Plant identifier', 'Scenario', 'Emission'], variable_name='Year', value_name='Value')
        .pivot('Emission', index=['Plant identifier', 'Plant name', 'Scenario', 'Year'], values='Value')
        .with_columns(pl.lit('production').alias('Flow type'))
        .with_columns(
                        (pl.col("NOx").cast(pl.Float64).fill_null(0.0) 
                            + pl.col("N₂O").cast(pl.Float64).fill_null(0.0)
                            ).alias("N2O")
                        )
                .drop(['NOx', 'N₂O'])
    )
    return df


def prep_utilities_reference(df:pl.DataFrame, REF_YEAR:str='2024'):
    pass
