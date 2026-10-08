



PATH_MANUAL_FILES = 'src/REGIONALIZATION/ref_data/persistent_manual_input/'

FILE_NAME_PROVIDERS = 'manual_providers.csv'
PATH_PROVIDERS = PATH_MANUAL_FILES + FILE_NAME_PROVIDERS


FILE_NAME_COORDS = 'manual_coords.csv'
PATH_COORDS = PATH_MANUAL_FILES  + FILE_NAME_COORDS

PATH_PERSISTENTS = {
    'coordinates': PATH_COORDS,
    'providers': PATH_PROVIDERS
}

CTM_TO_REGIO_SECTOR = {

    "other_chemicals":          "chemicals",
    "aluminium":                "aluminium",
    "other_metals":             "metals",
    "non_metallic_minerals":    "other",
    "transport_equipment":      "other",
    "machinery":                "other",
    "mining_and_quarrying":     "other",
    "food":                     "food",
    "paper":                    "paper",
    "central_ict":              None,
    "wood_and_wood_products":   "other",
    "construction":             "other",
    "textile_and_leather":      "other",
    "other":                    "other",
    "refineries":               "refineries",
    "steel":                    "steel",
    "fertilizers":              "chemicals",
    "steam_cracking":           "chemicals",
    "other":                    "other",
    "organic_base_chemicals":   "chemicals",
    "inorganic_base_chemicals": "chemicals"
}
