import polars as pl
from pathlib import Path
from .constants import SCENARIO_YEARS
from .ctm_client import CTMClient
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
        curves: pl.DataFrame = None, 
        all_years: list = SCENARIO_YEARS
        ) -> pl.DataFrame:

    if excel_path is not None:
        curves = pl.read_excel(excel_path)

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
        curves_df: pl.DataFrame = None,
        years: list[str] = SCENARIO_YEARS
) -> pl.DataFrame:
    
    init_curves = get_aggregated_curves(excel_path=excel_path, curves=curves_df, all_years=years)
    reshaped = reshape_cluster_sector_curves(init_curves, years)

    return reshaped



