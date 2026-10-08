import polars as pl
import pandas as pd
import json
from pathlib import Path
from constants import *


def parse_All_EANs(df:pl.DataFrame) -> pl.DataFrame:
    """_sumExpands the 'All EANs' column into multiple columns/rows

    Args:
        df (pl.DataFrame): _description_

    Returns:
        pl.DataFrame: _description_
    """
    # Convert to pandas
    df_pd = df.to_pandas()

    # Parse JSON strings
    df_pd['All EANs'] = df_pd['All EANs'].apply(json.loads)

    # Explode the list
    df_pd = df_pd.explode('All EANs', ignore_index=True)

    # Expand the dictionaries into columns
    ean_df = pd.json_normalize(df_pd['All EANs'])
    df_pd = pd.concat([df_pd.drop('All EANs', axis=1), ean_df], axis=1)

    # Convert back to Polars
    result = pl.from_pandas(df_pd)
    return result


def create_company_details_dfs(df: pl.DataFrame, plant_id: str) -> dict:
    '''
    Returns dictionary of plant_id: plant_details_df
    '''
    result = {}
    
    # for plant_id in df['Plant identifier'].unique():
    plant_data = df.filter(pl.col('Plant identifier') == plant_id)
    
    # Get base info (first row)
    base = plant_data.row(0, named=True)
    
    # Build rows
    rows = [
        ['Adres', base['Address']],
        ['Stad', base['City']],
        ['Postcode', base['Zip code']],
        ['Nieuw/Bestaand bedrijf', base['Existing plant/New plant']],
        ['Breedtegraad', base['Latitude']],
        ['Lengtegraad', base['Longitude']],
        ['Locatie', base['Plant name']],
        ['Sector (SBI/NACE code)', base['SBI code(s)']],
        ['Cluster (drop-down menu)', base['City']],
    ]
    
    # Define utility types and their Dutch names
    utility_mapping = {
        'Electricity': 'elektriciteit',
        'Natural Gas': 'aardgas',
        'Hydrogen': 'waterstof'
    }
    
    for utility_en, utility_nl in utility_mapping.items():
        # Filter and sort by main_connection
        connections = plant_data.filter(
            pl.col('utility_name').str.contains(utility_en)
        ).sort(pl.col('main_connection'), descending=True)
        
        # Add connection rows
        for i, conn in enumerate(connections.iter_rows(named=True), 1):
            rows.extend([
                [f'Aansluiting {utility_nl} {i}: EAN', conn['ean_code']],
                [f'Aansluiting {utility_nl} {i}: Netbeheerder', conn['grid_operator']],
                [f'Aansluiting {utility_nl} {i}: Type', conn['connection_type']],
                [f'Aansluiting {utility_nl} {i}: Hoofdaansluiting', conn['main_connection']]
            ])
    
    result[plant_id] = pd.DataFrame(rows, columns=['Field', 'Value'])
    
    return result


'''For Energy balance and emmisions '''

def get_prepared_emissions_forecast(df_emissions:pl.DataFrame) -> pl.DataFrame:
    # TODO: years should be dynamically set -> either by user or relative to current date
    relevant_columns = ['Plant name',
                        'Plant identifier',
                        'Company',
                        'Scenario',
                        'Version date',
                        'Emission',
                        '2024',
                        '2030',
                        '2035',
                        '2040',
                        '2050']
    
    result = df_emissions.select(relevant_columns)
    return result


def create_emissions_sheet(df: pl.DataFrame, ref_df: pl.DataFrame, plant_id: str, ref_year:int=2024) -> pl.DataFrame:
    '''
    Creates emissions part of sheet sheet 

    df is the dataframe from forecast: datasafehouse-emission-forecast-export_all_v1_20260508.csv

    Note: Demand is automatically set to None (as per example sheet)
    '''
    plant_data = df.filter(pl.col('Plant identifier') == plant_id)
    plant_data = plant_data.with_columns(Emission=pl.col('Emission').replace('N₂O', 'N2O'))

    reference = ref_df.filter(pl.col('Plant identifier') == plant_id)
    reference = reference.with_columns(Emission=pl.col('Emission').replace('N₂O', 'N2O')).with_columns(pl.lit('Reference').alias('Scenario'))
    reference = reference.filter(pl.col('Year')==ref_year)

    # TODO dinamically extract years?
    year_cols = [str(ref_year), '2030', '2035', '2040', '2050']
    emissions = plant_data['Emission'].unique().sort().to_list()
    # print(emissions)
    strategies = plant_data['Scenario'].unique().to_list()
    
    rows = []

    # display preferred strategies first
    for year in year_cols:
        year_label = year

        if year == str(ref_year):
            strategy = 'Reference'
            working_df = reference
        else:    
            strategy = 'Preferred'  
            working_df = plant_data

        # TODO fix the Demand/Supply thing; it should be 4 things like the projects
        row_demand = [year_label, strategy, "Demand"]
        row_supply = [year_label, strategy, "Supply"]
        # Add values for each emission
        for emission in emissions:
            if year == str(ref_year):
                value = working_df.filter(
                    pl.col('Emission') == emission
                ).select('Annual amount').head(1)
            else:
                value = working_df.filter(
                    (pl.col('Scenario') == strategy) & 
                    (pl.col('Emission') == emission)
                ).select(pl.col(year)).head(1)  
            
            row_supply.append(value[0, 0] if len(value) > 0 else None)
            row_demand.append(None)
        
        rows.append(row_demand)
        rows.append(row_supply)
        
        # Only show year in first row of each year group
        # year_label = ''

    for year in year_cols:
        if year != str(ref_year):
            year_label = year  # Keep the year label for first row
            
            # Add each strategy for this year
            for strategy in strategies:
                if strategy != 'Preferred':

                    row_demand = [year_label, strategy, "Demand"]
                    row_supply = [year_label, strategy, "Supply"]
                
                    # Add values for each emission
                    for emission in emissions:
                        value = plant_data.filter(
                            (pl.col('Scenario') == strategy) & 
                            (pl.col('Emission') == emission)
                        ).select(pl.col(year)).head(1)  
                        
                        row_supply.append(value[0, 0] if len(value) > 0 else None)
                        row_demand.append(None)
                    
                    rows.append(row_demand)
                    rows.append(row_supply)

    
    # Create DataFrame
    columns = ['Year', 'Strategy', 'Flow type'] + emissions
    df_export = pd.DataFrame(rows, columns=columns)
    df_export = pl.from_pandas(df_export)
    
    df_export = df_export.with_columns((pl.col('NOx').cast(pl.Float64) + pl.col('N2O').cast(pl.Float64)).alias('N2O')).select(['Year', 'Strategy', 'Flow type', 'CO2', 'Methane', 'N2O', 'F-gases'])
    
    return df_export


def get_prepared_energy_balance(df_forecast:pl.DataFrame) -> pl.DataFrame:
    relevant_columns = ['Plant name',
                        'Plant identifier',
                        'Company',
                        'Main EAN',
                        'Scenario',
                        'Version date',
                        'Utility',
                        'Peak/Annual',
                        'Flow type',
                        '2024',
                        '2030',
                        '2035',
                        '2040',
                        '2050']
    
    return df_forecast.select(relevant_columns)


def create_vraagenproductie_sheet(df: pl.DataFrame, ref_df:pl.DataFrame, plant_id: str, ref_year:int=2024) -> pd.DataFrame:
    '''
    Creates vraag en productie part of the emission sheet 

    df is datasafehouse-forecast-export_all_v1_20260508.csv

    '''
    plant_data = df.filter(pl.col('Plant identifier') == plant_id)
    
    if len(plant_data) == 0:
        return pd.DataFrame()
    
    year_cols = [str(ref_year), '2030', '2035', '2040', '2050']
    utilities = plant_data['Utility'].unique().sort().to_list()
    strategies = plant_data['Scenario'].unique().to_list()
    
    rows = []

    # display preferred scenarios first
    for year in year_cols:
        year_label = year
        strategy = 'Preferred'
        row_demand = [year_label, strategy, "Demand"]
        row_supply = [year_label, strategy, "Supply"]
        # Add values for each emission
        for utility in utilities:
            value = plant_data.filter(
                (pl.col('Scenario') == strategy) & 
                (pl.col('Utility') == utility)
            ).select(pl.col(year)).head(1)  
            
            row_supply.append(value[0, 0] if len(value) > 0 else None)
            row_demand.append(None)
        
        rows.append(row_demand)
        rows.append(row_supply)
        
        # Only show year in first row of each year group
        # year_label = ''


    
    for year in year_cols:
        year_label = year  # Keep the year label for first row
        
        # Add each scenario for this year
        for strategy in strategies:
            if strategy != 'Preferred':

                row_demand = [year_label, strategy, "Demand"]
                row_supply = [year_label, strategy, "Supply"]
            
                # Add values for each emission
                for utility in utilities:
                    value = plant_data.filter(
                        (pl.col('Scenario') == strategy) & 
                        (pl.col('Utility') == utility)
                    )
                    
                    value_demand = value.filter(pl.col('Flow type')=='demand').select(pl.col(year)).head(1)  
                    value_supply = value.filter(pl.col('Flow type') == 'supply').select(pl.col(year)).head(1)  
                                       
                    
                    row_supply.append(value_supply[0, 0] if len(value_supply) > 0 else None)
                    row_demand.append(value_demand[0, 0] if len(value_demand) > 0 else None)
                
                rows.append(row_demand)
                rows.append(row_supply)
            
            # Only show year in first row of each year group
            # year_label = ''
    
    # Create DataFrame
    columns = ['Year', 'Strategy', 'Flow type'] + utilities
    df_export = pd.DataFrame(rows, columns=columns)

    df_export = pl.from_pandas(df_export)
    
    return df_export
    

def get_energy_balance_emissions_sheet(df_emissions:pl.DataFrame, df_forecast: pl.DataFrame, plant_id:str)->pl.DataFrame:
    
    df_emissions_processed = get_prepared_emissions_forecast(df_emissions)
    df_forecast_processed = get_prepared_energy_balance(df_forecast)

    emissions = create_emissions_sheet(df_emissions_processed, plant_id)
    energy_balance = create_vraagenproductie_sheet(df_forecast_processed, plant_id)

    result = emissions.join(
        energy_balance,
        on=['Year', 'Strategy', 'Flow type'],
        how='inner',
        coalesce=True)
    
    return result.select(EMISSIES_VRAAG_COLUMN_ORDER)



'''For the PROJECTS sheet'''



def get_and_check_EAN(df:pl.DataFrame, ean_col: str = 'EAN code') -> str | None:
    ean_code_list = df.select(pl.col(ean_col)).filter(pl.col(ean_col).is_not_null()).unique().to_series().to_list()
    # print(ean_code_list)
    if len(ean_code_list) == 0:
        print('No EAN code found.')
        return None
    if len(ean_code_list) > 1:
        # TODO add raise warning
        print('Same project has too many EANs. Using the first found one.')
    ean_code = ean_code_list[0]

    return str(ean_code)



def get_project_details(projects_df:pl.DataFrame, plant_id:str) -> pl.DataFrame:
    rows = []
    counter = 0

    projects_df_aux = projects_df.filter(pl.col('Plant identifier') == plant_id)

    projects = projects_df_aux.select(pl.col('Project name')
                                  ).unique().to_series().to_list()

    for project in projects:
        counter += 1
        proj = projects_df_aux.filter(pl.col('Project name') == project)
        proj_details = proj.head(1).select(PROJECT_DETAILS_COLS).row(0)#.to_list()
        
        ean = get_and_check_EAN(proj)

        row = list(proj_details + (ean,))
        rows.append(row)

    df_export = pd.DataFrame(rows, columns=PROJECT_DETAILS_COLS + 'EAN')
    df_export = pl.from_pandas(df_export)

    # TODO fix column types
    return df_export


def get_project_values(projects_df:pl.DataFrame, plant_id:str) -> pl.DataFrame:

    projects_df_aux = projects_df.filter(pl.col('Plant identifier') == plant_id)
    projects = projects_df_aux.select(pl.col('Project name')
                                  ).unique().to_series().to_list()
    rows = []
    for project in projects:
        working_df = projects_df.filter(
            pl.col('Project name') == project
            ).filter(pl.col('Utility').is_in(greenhouse_cols + asking_cols))
        
        rows_per_project = {}

        for value_type in value_rows:
            rows_per_project[value_type] = [project, value_type]
            # for greenhouse gasses (broeikasgas)
            for col in greenhouse_cols:
                aux = working_df.filter(pl.col('Utility') == col)
                
                val = aux.select(pl.col(value_to_cols_dict[value_type])).head(1)[0,0]
                rows_per_project[value_type].append(val)

            for col in asking_cols:
                if col == 'Electricity_peak':
                    aux = working_df.filter(pl.col('Utility') == 'Electricity')
                    val = aux.select(pl.col(value_to_cols_electricity_MW_dict[value_type])).head(1)[0,0]
                    rows_per_project[value_type].append(val)
                else:
                    aux = working_df.filter(pl.col('Utility') == col)
                
                    val = aux.select(pl.col(value_to_cols_dict[value_type])).head(1)[0,0]
                    rows_per_project[value_type].append(val)
                    

            
            rows.append(rows_per_project[value_type])

    columns = ['Project', 'Type'] + greenhouse_cols + asking_cols
    df_export = pd.DataFrame(rows, columns=columns)
    df_export = pl.from_pandas(df_export)

    return df_export

            
    

