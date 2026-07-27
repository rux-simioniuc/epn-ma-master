SCENARIO_NAMES_DICT = {
    1: 'Midden',
    2: 'VT',
    3: 'Elektrificatie',
    4: 'Waterstof',
    5: 'Groen gas'
}

SCENARIO_YEARS = ['2030', '2035', '2040', '2050']
REFERENCE_YEAR = '2024'

ALL_YEARS = [REFERENCE_YEAR] + SCENARIO_YEARS

ALL_SCENARIOS = [
    'Elektrificatie', 
    'Midden',
    'VT', 
    'Groen gas',
    'Waterstof'
]

STRATEGIES_ORDER = ['Reference', 'Preferred', 'Electrification', 'Hydrogen', 'CCS and (green) gas']

# ── Canonical flow type labels ─────────────────────────────────────────────
# Used in both energy balance and scenario sheets
FLOW_TYPES = ["demand", "captive use", "production", "supply"]

# Mapping from reference data column names to canonical flow type labels
REFERENCE_FLOW_COL_MAP = {
    "Annual demand":      "demand",
    "Annual supply":      "supply",
    "Annual production":  "production",
    "Captive use annual": "captive use",   
}

# Peak column equivalents for electricity
REFERENCE_PEAK_COL_MAP = {
    "Annual demand":      "Peak demand",
    "Annual supply":      "Peak supply",
    "Annual production":  "Peak production",
    "Captive use annual": "Peak Captive use",
}

# ── Canonical utility column order ─────────────────────────────────────────


META_COLS_ORDER = [
    'Year',
    'Strategy',
    'Flow type',]


STRICT_EMISSIONS_ORDER = ["CO2", "Methane", "N2O", "F-gases"]
EMISSION_COLS_ORDER =  STRICT_EMISSIONS_ORDER + ["CO2 (fossil) CCU/CCS", "CO2 (bio) CCU/CCS"]#, "other"]

# Single source of truth — used in both energy balance and project sheets
UTILITY_COLS_ORDER = [
    'Electricity',
    'Electricity_peak',
    'Natural Gas',
    'Hydrogen ( >98% vol.%) (LHV)',
    'Hydrogen ( <98% vol.%) (LHV)',
    'Heat',
    'Residual gases',
    'Coal and coal products',
    'Oil and oil products',
    'Biomass (liquid)',
    'Biomass (solid)',
    'Green gas',
    'Waste (fossil)',
    'Waste (bio)',
    'Ammonia',
    'Methanol',
    'Other syn fuel and raw materials',
    'Other',
]

# ENERGY_COLS_ORDER = ["Electricity", "Electricity_peak", "Natural Gas", "Hydrogen"]


# Greenhouse gas emission columns (project sheet)
greenhouse_cols = [
    'CO2 (fossil) CCU/CCS',
    'CO2 (bio) CCU/CCS',
]

# asking_cols now derived from UTILITY_COLS to guarantee same order
asking_cols = UTILITY_COLS_ORDER

EMISSIES_VRAAG_COLUMN_ORDER = META_COLS_ORDER + EMISSION_COLS_ORDER + UTILITY_COLS_ORDER

### PROJECT SHEET

PROJECT_DETAILS_COLS = [
    'Project name',
    'Project Type',
    'Description',
    'Project phase',
    'Prob. of success',
    'Year of operation',
    'Planned execute year',
    'Planned define year',
    'Part of Preferred Strategy', 
    'Associated Strategies',
    'Associated Scenarios']

# project_details_cols += [f'Part of {i} scenario' for i in STRATEGIES_ORDER[2:]] + ['Associated Strategies','Associated Scenarios',]

PROJECT_DETAILS_ORDER = PROJECT_DETAILS_COLS[:-2] + [f'Part of {i} scenario' for i in STRATEGIES_ORDER[2:]] +  PROJECT_DETAILS_COLS[-2:] #+ ['CO2']

value_rows = ['Delta demand', 'Delta captive use', 'Delta production', 'Delta supply']

value_to_cols_dict = {
    'Delta demand':      'Demand annual',
    'Delta captive use': 'Captive use annual',
    'Delta production':  'Production annual',
    'Delta supply':      'Supply annual',
}

value_to_cols_electricity_MW_dict = {
    'Delta demand':      'Offtake peak',
    'Delta captive use': 'Captive use peak',
    'Delta production':  'Production peak',
    'Delta supply':      'Feed-in peak',
}