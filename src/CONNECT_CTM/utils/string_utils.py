"""
String Utils - column/string normalization helpers.
"""

import polars as pl


def fix_string(word: str) -> str:
    """Normalize a string for CTM keys: lowercase, spaces/dashes -> underscore."""
    if word is not None:
        return word.replace(' ', '_').replace('-', '_').lower()
    return ''


def fix_column(df: pl.DataFrame, col_name: str) -> pl.DataFrame:
    """Lowercase a column and replace spaces/dashes with underscores."""
    return df.with_columns(
        pl.col(col_name)
        .str.replace_all(" ", "_")
        .str.replace_all("-", "_")
        .str.to_lowercase()
    )


# ── Canonical value maps for free-text Cluster / Sector variants ──────────

CLUSTER_NAME_MAP = {
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

SECTOR_NAME_MAP = {
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


def normalize_sector_cluster_mapping(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize the 'Cluster' and 'Sector' columns to canonical CTM values."""
    return df.with_columns([
        pl.col("Cluster").replace(CLUSTER_NAME_MAP),
        pl.col("Sector").replace(SECTOR_NAME_MAP),
    ])
