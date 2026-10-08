from utils import *
import polars as pl
import pandas as pd
from format_emissies_sheet import *



emission_forecast_df = pl.from_pandas(pd.read_csv('/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260508_new/datasafehouse-emission-forecast-export_all_v2_20260521_df20260423.csv'))
demand_forecast_df = pl.from_pandas(pd.read_csv('/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260508_new/datasafehouse-forecast-export_all_v2_20260521_df20260423.csv'))

emission_reference_df = pl.from_pandas(pd.read_csv('/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260508_new/reference_emission_data_df20260423.csv'))
demand_reference_df = pl.from_pandas(pd.read_csv('/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260508_new/reference_utility_data_df20260423.csv'))

ref_year = 2024


ids = emission_forecast_df.select(pl.col('Plant identifier')).unique().to_series().to_list()

plants = pl.from_pandas(pd.read_csv('/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260508_new/datasafehouse-plant-export.csv.csv'))

path = '/home/307920@ontw.alfa.local/projects/epn-ma-master/generated/inter_xcels2'

    # test the project sheet
project_emissions = pl.from_pandas(pd.read_csv(
    '/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260508_new/datasafehouse-projectdata-export_emissions_df20260423.csv'))

project_utilities = pl.from_pandas(pd.read_csv(
    '/home/307920@ontw.alfa.local/projects/epn-ma-master/data/dsh/20260508_new/datasafehouse-projectdata-export_utilities_df20260423.csv'
))
ids = ['a6870790-8e59-4f8e-bd7e-a8c70d1683e9']

for i in ids:
    # i = 'eccbf834-1291-48d8-b391-3f78387b8b4b'
    r = get_energy_balance_emissions_sheet(emission_forecast_df, 
                                           emission_reference_df, 
                                           demand_forecast_df, 
                                           demand_reference_df, 
                                           i, 
                                           ref_year)
    plant_name = emission_forecast_df.filter(pl.col('Plant identifier') == i).select('Plant name').head(1)[0,0].replace('/', '_')


    # details = create_company_details_dfs(plants, i)
    # print()

    units = get_all_units(
        ref_emission_df=emission_reference_df,
        ref_utility_df=demand_reference_df,
    )

    xcel_name = f'{plant_name}_inter.xlsx'
    final_path =  f'{path}/{xcel_name}'

    # write_plant_details_sheet(details,final_path)
    # write_energy_balance_sheet(r, 
    #                            output_path=final_path,
    #                            existing_path=final_path)
    



    projects_fin = get_project_sheet(project_emissions, project_utilities, i)

    write_projects_sheet(projects_fin, 
                         output_path=final_path,
                         units=units, 
                         #existing_path=final_path
                         )

    # print(f'Done with {plant_name}')


# for i in ids:
#     aux = create_company_details_dfs(plants, i)
#     print('x')


i = 'c00446f2-df0c-466d-a5c9-82f434123d17'





