

# Clusters as named in the API
CLUSTERS = [
    "noord_nederland",
    "nzkg",
    "rotterdam_moerdijk",
    "zeeland_west_brabant",
    "chemelot",
    "cluster_6",
]

# total of 14 sectors
SECTORS = [
    'other_chemicals', 
    'aluminium', 
    'other_metals', 
    'non_metallic_minerals', 
    'transport_equipment', 
    'machinery', 
    'mining_and_quarrying', 
    'food', 
    'paper', 
    'central_ict', 
    'wood_and_wood_products', 
    'construction', 
    'textile_and_leather', 
    'other'
]

EXTRA_SECTORS = [
    'refineries',
    'steel',
    'fertilizers',
    'steam cracking'
]

ALL_SECTORS = SECTORS + EXTRA_SECTORS

BOTTOM_UP_CATEGORIES = {
    # Refineries
    "shell_pernis": "Refineries",
    "bp": "Refineries",
    "exxonmobil": "Refineries",
    "gunvor": "Refineries",
    "vpr_energy": "Refineries",
    "zeeland_refinery": "Refineries",

    # Steel
    "tata_steel": "Steel",
    "arcelor_mittal": "Steel",

    # Fertilizers
    "oci": "Fertilizers",
    "yara": "Fertilizers",

    # Steam cracking
    "shell_moerdijk": "Steam cracking",
    "dow": "Steam cracking",
    "sabic": "Steam cracking",

    # Organic base chemicals
    "air_products": "Organic base chemicals",
    "air_products_merseyweg": "Organic base chemicals",
    "air_liquide": "Organic base chemicals",
    "air_liquide_boz": "Organic base chemicals",
    "biomcn": "Organic base chemicals",
    "anqore": "Organic base chemicals",
    "fibrant": "Organic base chemicals",
    "lyondellbasell": "Organic base chemicals",
    "chemelot_other": "Organic base chemicals",

    # Inorganic base chemicals
    "albemarle": "Inorganic base chemicals",
    "nobian_hengelo": "Inorganic base chemicals",
    "nobian_delfzijl": "Inorganic base chemicals",
    "nobian_botlek": "Inorganic base chemicals",
}


# list to have 'tranformation' set to 1

TRANSFORMATION_OVERRIDES = {
    # refineries
    # "shell_pernis": "1",
    # "exxonmobil": "1",
    # "zeeland_refinery": "1",
    
    # air separation
    "air_liquide": "1",
    "air_liquide_boz": "1",
    "air_products": "1",
    "air_products_merseyweg": "1",
    
    # steam cracking
    # "shell_moerdijk": "1",
    # "dow": "1",
    "sabic": "1",
}


OVERRIDES = {
    'shell_pernis&&transformation': 0,
    'bp&&transformation': 0,
    'exxonmobil&&transformation': 0,

    'gunvor&&transformation': 0,
    'vpr_energy&&transformation' : 0,
    'zeeland_refinery&&transformation': 0,
    
    'shell_moerdijk&&transformation': 0,
    'dow&&transformation': 0,

    'other_chemicals&&chemelot&&cluster_site_other_chemicals_chemelot&&transformation': 0
}


TRANSFORMATION_OVERRIDES_FULL = {
    "air_liquide&&transformation": "1",
    "air_liquide_boz&&transformation": "1",
    "air_products&&transformation": "1",
    "air_products_merseyweg&&transformation": "1",
    "sabic&&transformation": "1",
}


ALL_OVERRIDES = TRANSFORMATION_OVERRIDES_FULL | OVERRIDES


ALL_SCENARIOS = [
    'Elektrificatie',
    'Midden',
    'VT',
    'Groen gas',
    'Waterstof'
]


# Valid CTM column names for energy inputs
# Maps DSH column name -> CTM column name (without _demand/_production suffix)

CTM_ENERGY_COLUMN_MAP = {
    "Electricity": "electricity",
    "Natural Gas": "natural_gas",
    "Ammonia": "ammonia",
    "Methanol": "methanol",
    "Green gas": "green_gas",
    "Coal and coal products": "coal_and_coal_products",
    "Oil and oil products": "oil_and_oil_products",
    "Heat": "heat_(>_100_c)",
    "Residual gases": "waste_gases",
    "Hydrogen ( <98% vol.%) (LHV)": "hydrogen_(<98%_vol%)",
    "Hydrogen ( >98% vol.%) (LHV)": "hydrogen_(>98%_vol%)",
    "Biomass (liquid)": "biomass_(liquid)",
    "Biomass (solid)": "biomass_(solid)",
    "Waste (bio)": "waste_(biogenic)",
    "Waste (fossil)": "waste_(fossil)",
    "CO2 (bio)": "co2_bio",
    "CO2 (fossil)": "co2_fossil",
}

# LDSH (peak electricity in MWe) - always needs full hierarchy
# CTM_LDSH_PEAK_ELECTRICITY = "emissions_and_energy_elektriciteit_mw"

# Valid CTM emission columns (production only)
CTM_EMISSION_COLUMN_MAP = {
    "CO2": "co2_emissions_production",
    "Methane": "methane_emissions_production",
    "N2O": "n2o_emissions_production",
    "F-gases": "f_gas_emissions_production",
    "Other greenhouse gas emissions": "other_greenhouse_gas_emissions_production",
}


BOTTOM_UP_SITES = [
    'shell_pernis', 
    'bp', 
    'exxonmobil', 
    'gunvor', 
    'vpr_energy', 
    'zeeland_refinery',
    'tata_steel',
    'arcelor_mittal',
    'oci',
    'yara',
    'shell_meordijk',
    'dow',
    'sabic',
    'air_products', 
    'air_products_merseyweg', 
    'air_liquide', 
    'air_liquide_boz', 
    'biomcn', 
    'anqore', 
    'fibrant', 
    'lyondellbasell', 
    'chemelot_other',
    'albemarle', 
    'nobian_hengelo', 
    'nobian_delfzijl', 
    'nobian_botlek'
]


def get_valid_ctm_inputs(sector: str, cluster: str, site: str) -> set:
    """Return set of valid CTM input keys for a given site hierarchy."""
    valid = set()
    
    valid.add(f"{sector}&&{cluster}&&{site}&&enabled")
    valid.add(f"{sector}&&{cluster}&&{site}&&transformation")

    # Energy columns (demand and production)
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(f"{sector}&&{cluster}&&{site}&&{ctm_col}_demand")
        valid.add(f"{sector}&&{cluster}&&{site}&&{ctm_col}_production")
    
    # LDSH peak electricity
    # valid.add(f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_demand_future")
    # valid.add(f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_production_future")
    
    # Emission columns (production only)
    for ctm_col in CTM_EMISSION_COLUMN_MAP.values():
        valid.add(f"{sector}&&{cluster}&&{site}&&{ctm_col}")
    
    return valid


def get_valid_ctm_inputs_bottom_up(sector: str, cluster: str, site: str) -> set:
    """
    Return set of valid CTM input keys for a bottom-up site.
    Bottom-up sites need sector/cluster context for LDSH fields.
    """
    valid = set()
    
    valid.add(f"{site}&&enabled")
    valid.add(f"{site}&&transformation")
    
    # Energy columns (flat pattern for bottom-up)
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(f"{site}&&{ctm_col}_demand")
        valid.add(f"{site}&&{ctm_col}_production")
    
    # LDSH peak electricity (uses hierarchy even for bottom-up)
    # valid.add(f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_demand_future")
    # valid.add(f"ldsh&&{sector}&&{cluster}&&{site}&&{CTM_LDSH_PEAK_ELECTRICITY}_production_future")
    
    # Emissions
    for ctm_col in CTM_EMISSION_COLUMN_MAP.values():
        valid.add(f"{site}&&{ctm_col}")
    
    return valid


def get_valid_ctm_inputs_custom(sector: str, cluster: str, custom_site: str) -> set:
    """Return set of valid CTM input keys for a custom site."""
    valid = set()
    
    valid.add(f"{custom_site}&&enabled")

    # add cluster and sector
    valid.add(f"{custom_site}&&cluster")
    valid.add(f"{custom_site}&&sector")

    
    valid.add(f"{custom_site}&&latitude")
    valid.add(f"{custom_site}&&longitude")
    
    
    # Energy columns (flat pattern)
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(f"{custom_site}&&{ctm_col}_demand")
        valid.add(f"{custom_site}&&{ctm_col}_production")
    
    # LDSH peak electricity (FLAT format for custom sites: ldsh&&##new_cc_site1##&&...)
    # valid.add(f"ldsh&&{custom_site}&&{CTM_LDSH_PEAK_ELECTRICITY}_demand_future")
    # valid.add(f"ldsh&&{custom_site}&&{CTM_LDSH_PEAK_ELECTRICITY}_production_future")
    
    # Emissions
    for ctm_col in CTM_EMISSION_COLUMN_MAP.values():
        valid.add(f"{custom_site}&&{ctm_col}")
    
    return valid


def get_valid_ctm_inputs_cluster(sector: str, cluster: str) -> set:
    """Return set of valid CTM input keys for cluster level."""
    valid = set()
    valid.add(f"{sector}&&{cluster}&&cluster&&enabled")
    
    # Energy columns at cluster level
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(f"{sector}&&{cluster}&&cluster&&{ctm_col}_demand")
        valid.add(f"{sector}&&{cluster}&&cluster&&{ctm_col}_production")
    
    return valid


def get_valid_ctm_inputs_sector(sector: str) -> set:
    """Return set of valid CTM input keys for sector level."""
    valid = set()
    valid.add(f"{sector}&&sector&&enabled")
    
    # Energy columns at sector level
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(f"{sector}&&sector&&{ctm_col}_demand")
        valid.add(f"{sector}&&sector&&{ctm_col}_production")
    
    return valid
