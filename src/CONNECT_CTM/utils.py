import polars as pl
from pathlib import Path
from openpyxl import load_workbook
from typing import Dict
import tempfile
from .constants import SCENARIO_YEARS, EMISSION_COLS_ORDER, UTILITY_COLS_ORDER
from .ctm_client import CTMClient
from .read_DSH_files import read_all_scenario_sheets
# read and transform mapping excel


def fix_string(word: str) -> str:
    if word is not None:
        return word.replace(' ', '_').replace('-', '_').lower()
    return ''

def fix_column(df: pl.DataFrame, col_name:str) -> pl.DataFrame:
    '''
    Make all elements in the columns be lowercase, replaces spaces and dashes with _
    '''
    aux = df.with_columns(
        pl.col(col_name)
        .str.replace_all(" ", "_")
        .str.replace_all("-", "_")
        .str.to_lowercase()
    )

    return aux


def normalize_sector_cluster_mapping(df:pl.DataFrame) -> pl.DataFrame:
    # Cluster normalizations
    cluster_map = {
        'nzkg': 'nzkg',
        'NZKG': 'nzkg',
        'rotterdam_moerdijk': 'rotterdam_moerdijk',
        'Rotterdam-Moerdijk': 'rotterdam_moerdijk',
        'rotterdam moerdijk': 'rotterdam_moerdijk',
        'cluster_6': 'cluster_6',
        'Cluster 6': 'cluster_6',
        'cluster 6': 'cluster_6',
        'Overig': 'cluster_6',
        'overig': 'cluster_6',
        'noord_nederland': 'noord_nederland',
        'Noord-Nederland': 'noord_nederland',
        'noord nederland': 'noord_nederland',
        'zeeland_west_brabant': 'zeeland_west_brabant',
        'Zeeland-West-Brabant': 'zeeland_west_brabant',
        'zeeland west brabant': 'zeeland_west_brabant',
        'Gebruiker stuurt op via API': 'gebruiker_stuurt_op_via_api',

    }
    
    # Sector normalizations
    sector_map = {
        'Organic base': 'organic_base_chemicals',
        'Organic base chemicals': 'organic_base_chemicals',
        'organic_base_chemicals': 'organic_base_chemicals',
        'Inorganic base chemicals': 'inorganic_base_chemicals',
        'inorganic_base_chemicals': 'inorganic_base_chemicals',
        'Other chemicals': 'other_chemicals',
        'other_chemicals': 'other_chemicals',
        'Other chemical': 'other_chemicals',
        'Food': 'food',
        'food': 'food',
        'Steel': 'steel',
        'steel': 'steel',
        'Refineries': 'refineries',
        'refineries': 'refineries',
        'Aluminium': 'aluminium',
        'aluminium': 'aluminium',
        'Paper': 'paper',
        'paper': 'paper',
        'Non-metallic minerals': 'non_metallic_minerals',
        'non_metallic_minerals': 'non_metallic_minerals',
        'non metallic minerals': 'non_metallic_minerals',
        'Other metals': 'other_metals',
        'other_metals': 'other_metals',
        'other metals': 'other_metals',
        'Machinery': 'machinery',
        'machinery': 'machinery',
        'Textiles and leather': 'textile_and_leather',
        'textile_and_leather': 'textile_and_leather',
        'Textile and leather': 'textile_and_leather',
        'Transport equipment': 'transport_equipment',
        'transport_equipment': 'transport_equipment',
        'Mining and quarrying': 'mining_and_quarrying',
        'mining_and_quarrying': 'mining_and_quarrying',
        'Central ICT': 'central_ict',
        'central_ict': 'central_ict',
        'Other': 'other',
        'other': 'other',
        'Gebruiker stuurt op via API': 'gebruiker_stuurt_op_via_api',
    }

     # Apply normalization
    df = df.with_columns([
        pl.col("Cluster")
        .replace(cluster_map),

        pl.col('Sector').replace(sector_map)
    ])

    return df


def read_and_transform_mapping(
        excel_path: str = None,
        mapping_df: pl.DataFrame = None,
        markers: list = ['Bestaande niet-bottom-up sites', 'Bottom-up sites', 'New sites'],
        marker_column_name:str = 'Name',
        save_file: bool = False,
        save_path: str = '', # if empty defaults to location of original file,
        normalize_sector_cluster:bool = False
) -> pl.DataFrame:

    if excel_path is not None:
        maps = pl.read_excel(excel_path)
    else:
        maps = mapping_df

    df = maps.with_columns(
        pl.when(pl.col(marker_column_name).is_in(markers))
        .then(pl.col(marker_column_name))
        .otherwise(None)
        .forward_fill()
        .alias('category')
    )

    df = df.filter(~pl.col(marker_column_name).is_in(markers))

    # create bool columns
    result = df.with_columns([pl.when(pl.col('category')=='New sites')
                 .then(pl.lit(True))
                 .otherwise(False)
                 .alias('New site'),
                 
                 pl.when(pl.col('category')=='Bottom-up sites')
                 .then(pl.lit(True))
                 .otherwise(False)
                 .alias('Bottom-up')
                 ])
    
    result = result.with_columns(
        pl.col("API input name")
        .str.replace_all(r"[\s-]+", "_")
        .str.to_lowercase()
        )
    
    # fix the mapping with the API
    ctm = CTMClient(use_beta=True)
    ctm.create_clean_sheet_session()
    ctm.load_all_list()

    # site_lookup = ctm.build_site_lookup()

    site_names_in_mapping = result.filter(
        ~pl.col('Name reformatted').str.contains('new_cc_site')
        ).select(pl.col('Name reformatted')
                 ).to_series().to_list()
    
    site_lookup = {}
    
    for site in site_names_in_mapping:
        site_lookup[site] = ctm.find_sector_cluster_site(site)


    ctm.delete_session()

    api_sites = pl.DataFrame([
        {
            "API name": site,
            "CTM sector": values["sector"],
            "CTM cluster": values["cluster"],
        }
        for site, values in site_lookup.items() if values is not None
    ])

    result = result.join(
        api_sites,
        left_on="Name reformatted",
        right_on="API name",
        how="left",
    )

    result = (
        result
        .with_columns(
            pl.coalesce(
                pl.col("CTM cluster"),
                pl.col("Cluster")
            ).alias("Cluster")
        )
        .with_columns(
            pl.coalesce(
                pl.col("CTM sector"),
                pl.col("Sector")
            ).alias("Sector")
        )
        .drop(["CTM cluster", "CTM sector"])
    )

    if normalize_sector_cluster:

        result = normalize_sector_cluster_mapping(result)


    if save_file:
        if save_path == '':
            save_path = Path(excel_path).parent
            
        result.write_csv(f'{save_path}/mapping.csv')

    return result



def get_aggregated_curves(
        excel_path: str= None,
        sheet_name: str = 'resultaat',
        curves: pl.DataFrame = None, 
        all_years: list = SCENARIO_YEARS
        ) -> pl.DataFrame:

    if excel_path is not None:
        curves = pl.read_excel(excel_path, sheet_name=sheet_name)

    curves = curves.with_columns(pl.col("Cluster").str.to_lowercase().replace('overig', 'cluster 6').alias('Cluster'))

    for col in ['Cluster', 'Sector']:
        curves = fix_column(curves, col)
    
    curves = curves.with_columns(pl.col('Energiedrager').str.to_lowercase())

    sums = curves.group_by(['Cluster', 'Sector', 'Scenario', 'Energiedrager']
                ).agg(
                    [pl.col(i).sum() for i in all_years]
                ).sort(['Cluster', 'Sector', 'Scenario', 'Energiedrager'])
    

    energidragers_map = {
        'elektriciteit': 'electricity',
        'gas': 'natural_gas',
        'waterstof': 'hydrogen_(>98%_vol%)',
        'Oil and oil products': 'oil_and_oil_products'
    }

    sums = sums.with_columns([
        pl.col("Energiedrager").str.to_lowercase().replace(energidragers_map).alias('Utility'),
        pl.lit('demand').alias('Flow type')]).drop('Energiedrager')
    
    return sums


def reshape_cluster_sector_curves(
    curves_df: pl.DataFrame,
    year_cols: list = SCENARIO_YEARS,
) -> pl.DataFrame:
    """
    Reshape sector/cluster curves from wide format (years as columns) to long format.
    
    Input schema:
        Cluster, Sector, Scenario, 2024, 2030, 2035, 2040, 2050, Utility, Flow type
        (year columns contain the actual values)
    
    Output schema:
        Cluster, Sector, Scenario, Year, Value, Utility, Flow type
    
    Args:
        curves_df: DataFrame with year columns
        year_cols: list of year column names (default: SCENARIO_YEARS)
    
    Returns:
        DataFrame in long format
    """
    
    # Unpivot year columns
    id_cols = ['Cluster', 'Sector', 'Scenario', 'Utility', 'Flow type']
    
    # Filter to only year columns that exist
    year_cols = [col for col in year_cols if col in curves_df.columns]
    
    # Unpivot: wide to long
    long_df = curves_df.unpivot(
        index=id_cols,
        on=year_cols,
        variable_name='Year',
        value_name='Value',
    )
    
    # Cast Year to string (in case it's not already)
    long_df = long_df.with_columns(pl.col('Year').cast(pl.Utf8))
    
    return long_df


def get_final_cluster_sector_curves(
        excel_path: str = None,
        sheet_name: str = 'resultaat',
        curves_df: pl.DataFrame = None,
        years: list[str] = SCENARIO_YEARS
) -> pl.DataFrame:
    
    init_curves = get_aggregated_curves(excel_path=excel_path, sheet_name=sheet_name, curves=curves_df, all_years=years)
    reshaped = reshape_cluster_sector_curves(init_curves, years)

    return reshaped


def push_ctm_scenario_to_etm(ctm_session:str, etm_session:str, etm_token:str, log_container=None):
    # Instead of print() or appending to logs list:
    def log_message(msg):
        if log_container:
            log_container.write(msg)

    try:
        ctm = CTMClient(use_beta=True)
        ctm.load_session(session_id=ctm_session)
    except Exception as e:
        print('Err loading the CTM session')
        log_message(f"[ERR] Loading CTM session: {e}")

    # Try coupling immediately (empty session)
    try:
        etm_result = ctm.couple_etm(
            auth_token=etm_token,
            etm_session_id=etm_session
        )
        print('Pushed CTM session to ETM')
        log_message(f'[SUCCESS] Pushed CTM {ctm_session} to ETM {etm_session}.')
        return etm_result
    except Exception as e: 
        log_message(f"[ERR] Pushing to ETM: {e}")
        print(f'Err pushing to ETM: {e}')  


def get_master_projects(
        mapping_df: pl.DataFrame,
        reference_emission_df: pl.DataFrame,
        reference_utility_df: pl.DataFrame, 
        projects_emission_df: pl.DataFrame,
        projects_utility_df: pl.DataFrame,
        REF_YEAR: str = '2024',
        included_emissions: list[str] = ['CO2', 'CCU/CCS'],
        scenario_list: list[str]= ['Electrification', 'Hydrogen', 'CCS and (green) gas'] # TODO these are in english in DSH but Dutch in all other scenario work; what do?
        )-> pl.DataFrame:

    # some constants
    basic_details_cols = [
        'Plant identifier',
        'Plant',
        'Cluster',
        'Project name',
        'Project Type',
        'Description',
        'Prob. of success',
        'Year of operation',]

    details_cols = basic_details_cols + ['Associated Scenarios',
                                         'Part of Preferred Strategy',]

    emission_cols = included_emissions
    utility_cols = [
        'Electricity',
        'Electricity_peak',
        'Natural Gas',
        'Hydrogen',
        'Green gas',
        'Other',
        ]

    # STRATEGIES_ORDER = ['Electrification', 'Hydrogen', 'CCS and (green) gas']

    print(f'utility cols {projects_utility_df.columns}')

    # select only relevant columns
    proj_utilities_filt = projects_utility_df.select(
        details_cols + [
            'Utility',
            'Demand annual',
            'Supply annual',
            'Offtake peak'
            ])

    proj_emissions_filt = projects_emission_df.select(
        details_cols + [
            'Emission',
            'Annual emission',
            ])

    # pivot emissions
    emissions_pivoted = proj_emissions_filt.pivot(
            "Emission",
            index= [x for x in proj_emissions_filt.columns if x not in ['Emission', 'Annual emission']],
            values='Annual emission'
        ).with_columns(pl.sum_horizontal("NOx", "N2O").alias('N2O')
                    ).drop(['NOx'])

    # pivot utilities
    # select CCU/CCS only for supply and add them up
    utilities_ccu = proj_utilities_filt.filter(pl.col('Utility').is_in(['CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS'])
                                           ).pivot(
                                               'Utility',
                                                values='Supply annual',
                                                index = ['Plant identifier',
                                                         'Project name',
                                                        ]
                ).with_columns(pl.sum_horizontal('CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS').alias('CCU/CCS')
                ).drop(['CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS'])

    # get the peak electricity
    utilities_peak = proj_utilities_filt.filter(pl.col('Utility') == 'Electricity').pivot(
                'Utility',
                values='Offtake peak',
                index = ['Plant identifier',
                    'Project name',
                    ],
            ).rename({'Electricity':'Electricity_peak'})

    # get rest of utilities
    utilities_all = proj_utilities_filt.filter(~pl.col('Utility').is_in(['CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS'])).pivot(
                'Utility',
                values=['Demand annual'],
                index = details_cols,      
            ).with_columns(
                pl.sum_horizontal('Hydrogen ( >98% vol.%) (LHV)','Hydrogen ( <98% vol.%) (LHV)').alias('Hydrogen')
                ).drop(['Hydrogen ( <98% vol.%) (LHV)', 'Hydrogen ( >98% vol.%) (LHV)'])

    # join everything for utility
    utilities_pivoted = utilities_all.join(
        utilities_peak,
        on=['Plant identifier', 'Project name'],
        how='full'
    )
    utilities_pivoted = utilities_pivoted.drop([i for i in utilities_pivoted.columns if '_right' in i])

    utilities_pivoted = utilities_pivoted.join(
        utilities_ccu,
        on=['Plant identifier', 'Project name'],
        how='full'
    )
    utilities_pivoted = utilities_pivoted.drop([i for i in utilities_pivoted.columns if '_right' in i])

    # join emissions and utilities
    projects = utilities_pivoted.join(
        emissions_pivoted,
        on= ['Plant identifier', 'Project name'],
        how='full'
    )

    # complete common columns then remove the duplicate
    # the fill_null() replaces missing values
    projects = projects.with_columns([pl.col(i).fill_null(pl.col(f'{i}_right')) for i in details_cols]
                      ).drop([f'{i}_right' for i in details_cols])

    # select only relevant cols
    projects = projects.select([x for x in details_cols + emission_cols + utility_cols if x in projects.columns])

    # add columns for scenarios'
    for scenario in scenario_list:
        projects = projects.with_columns(
            pl.col("Associated Scenarios")
            .fill_null("")
            .str.contains(scenario, literal=True)
            .alias(f"Scenario {scenario}")
        )

    # preferred strategy maps to VT and Midden
    # TODO: make an option for user selection of this
    projects = projects.with_columns(
            [pl.col('Part of Preferred Strategy').alias('Scenario VT'), 
            pl.col('Part of Preferred Strategy').alias('Scenario Midden')]
            ).drop(['Associated Scenarios', 'Part of Preferred Strategy'])


    # work the reference data now
    # select the reference year only
    ref_emission_filt = reference_emission_df.filter(pl.col('Year').cast(pl.String) == REF_YEAR)
    ref_utility_filt = reference_utility_df.filter(pl.col('Year').cast(pl.String) == REF_YEAR)

    # pivot
    ref_emission_pivoted = ref_emission_filt.pivot(
        'Emission',
        index = ['Plant identifier', 'Plant'],
        values=['Annual amount']
    ).with_columns(pl.sum_horizontal("NOx", "N2O").alias('N2O')
                ).drop(['NOx'])

    # same work as for the project utilities
    ref_util_ccu = ref_utility_filt.filter(pl.col('Utility').is_in(['CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS'])
                                            ).pivot(
                                                'Utility',
                                                    values='Annual supply',
                                                    index = ['Plant identifier']
                    ).with_columns(pl.sum_horizontal('CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS').alias('CCU/CCS')
                    ).drop(['CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS'])


    ref_util_peak = ref_utility_filt.filter(pl.col('Utility') == 'Electricity'
                                            ).pivot(
                                                'Utility',
                                                values='Peak demand',
                                                index = ['Plant identifier'],
                                            ).rename({'Electricity':'Electricity_peak'})


    ref_util_all = ref_utility_filt.filter(~pl.col('Utility').is_in(['CO2 (fossil) CCU/CCS','CO2 (bio) CCU/CCS'])
                                           ).pivot(
                                               'Utility',
                                                values=['Annual demand'],
                                                index = ['Plant identifier'],      
                                                ).with_columns(
                                                    pl.sum_horizontal('Hydrogen ( >98% vol.%) (LHV)','Hydrogen ( <98% vol.%) (LHV)').alias('Hydrogen')
                                                    ).drop(['Hydrogen ( <98% vol.%) (LHV)', 'Hydrogen ( >98% vol.%) (LHV)'])

    ref_util_pivoted = ref_util_all.join(
        ref_util_peak,
        on=['Plant identifier'],
        how='full'
    )

    ref_util_pivoted = ref_util_pivoted.drop([i for i in ref_util_pivoted.columns if '_right' in i])

    ref_util_pivoted = ref_util_pivoted.join(
        ref_util_ccu,
        on=['Plant identifier'],
        how='full'
    )
    ref_util_pivoted = ref_util_pivoted.drop([i for i in ref_util_pivoted.columns if '_right' in i])

    ref_full = ref_util_pivoted.join(ref_emission_pivoted,
                      on=['Plant identifier'],
                      how='full')

    ref_full = ref_full.with_columns([pl.lit(None).alias(i) for i in emission_cols + utility_cols if i not in ref_full.columns])

    ref_full = ref_full.select(['Plant identifier'] + emission_cols + utility_cols)

    # now add the reference
    merged = projects.join(
        ref_full,
        on='Plant identifier',
        how='left',
        suffix='_ref'
    )

    for metric in emission_cols+utility_cols:
        proj_col = metric
        ref_col = f"{metric}_ref"
        percent_col = f"{metric}_%"
        
        if ref_col in merged.columns and proj_col in merged.columns:
            # (proj_col / ref_col ) * 100    
            merged = merged.with_columns(
                pl.when(pl.col(ref_col) != 0)
                .then((pl.col(proj_col) / pl.col(ref_col)) * 100)
                .otherwise(None)
                .alias(percent_col)
            )
        
    # Drop reference columns (keep only original + percentages)
    cols_to_drop = [f"{m}_ref" for m in emission_cols+utility_cols if f"{m}_ref" in merged.columns]
    merged = merged.drop(cols_to_drop)

    # get the order for the value cols
    metric_pairs = []
    for metric in emission_cols+utility_cols:
        if metric in merged.columns:
            metric_pairs.append(metric)
        percent_col = f"{metric}_%"
        if percent_col in merged.columns:
            metric_pairs.append(percent_col)

    # add cluster/sector from mapping file
    mapping = mapping_df.select(['DSH plant id', 'Sector', 'Cluster'])

    merged = merged.drop('Cluster').join(mapping,
                left_on='Plant identifier',
                right_on = 'DSH plant id',
                how='left')

    merged_fin = merged.select(basic_details_cols + metric_pairs + [x for x in merged.columns if 'scenario' in x.lower()])

    return merged_fin


def read_all_scenario_sheets_from_excels(
    excel_files_dict: Dict[str, bytes],
    reference_year: str|int = '2024',
) -> pl.DataFrame:
    """
    Read all Scenario X sheets from all generated Excel files.
    Returns combined DataFrame with plant name from filename.
    """
        
    all_scenario_records = []
    
    for file_name, file_bytes in excel_files_dict.items():
        # Extract plant name from filename (e.g., "Plant A.xlsx" → "Plant A")
        plant_name = Path(file_name).stem
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        try:
            
            df = read_all_scenario_sheets(
                workbook_path=str(tmp_path),
                emission_cols=EMISSION_COLS_ORDER,
                energy_cols=UTILITY_COLS_ORDER,
                reference_year='0', # if it's 0 the reference is also included here
                aggregate_flow_types=False, 
            )

            reference = df.filter(
                pl.col("Year") == str(reference_year)
            )
            
            # Set Scenario to 'Reference'
            reference = reference.with_columns(
                pl.lit("Reference").alias("Scenario")
            )
            
            # Remove duplicates (same plant, year, flow_type should have same metric values)
            reference = reference.unique(
                subset=["Scenario", "Year", "Flow type"],
                keep="first"
            )

            scenario_data = df.filter(pl.col("Year") != "2024")

            # Combine
            master = pl.concat([scenario_data, reference])

            if not master.is_empty():
                # Add plant name
                master = master.with_columns(
                    pl.lit(plant_name).alias("Plant name")
                )
                all_scenario_records.append(master)
                
        
        except Exception as e:
            print(f"    [ERROR] {e}")
        finally:
            Path(tmp_path).unlink()  # Clean up temp file
 
    if all_scenario_records:
        scenario_data = pl.concat(all_scenario_records, how='vertical_relaxed')
        # print(f"Combined scenario data: {scenario_data.shape}")
        # print(f"Columns: {scenario_data.columns}")
    else:
        print("No scenario data found!")
        scenario_data = pl.DataFrame()
        
    return scenario_data


def get_master_emissions_utilities(
        mapping_df: pl.DataFrame,
        excel_files_dict: Dict[str, bytes],
        reference_year: str|int = '2024',
        ) -> pl.DataFrame:

    scenario_data = read_all_scenario_sheets_from_excels(
        excel_files_dict, reference_year
    )

    mapping_subset = mapping_df.select([
        "DSH plant name",
        "Cluster",
        "Sector",
    ]).unique()
    
    # Join on plant name
    df_enriched = scenario_data.join(
        mapping_subset,
        left_on='Plant name',
        right_on="DSH plant name",
        how="left"
    )

    # Drop DSH plant name (duplicate)
    if "DSH plant name" in df_enriched.columns:
        df_enriched = df_enriched.drop("DSH plant name")

    # Reorder: Cluster and Sector after plant info, before metrics
    base_cols = ["Plant name", "Cluster", "Sector", "Scenario", "Year", "Flow type"]
    metric_cols = [c for c in df_enriched.columns if c not in base_cols]

    df_enriched = df_enriched.select(base_cols + metric_cols).sort(['Plant name', 'Year', 'Flow type'])

    return df_enriched

