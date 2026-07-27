from push_to_ctm import push_plant_to_ctm
from utils import read_and_transform_mapping
from constants import EMISSION_COLS_ORDER, UTILITY_COLS_ORDER

path = '/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm/input/Sprint 2 CTM upload/ADM Europoort.xlsx'

mapping = read_and_transform_mapping("/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm/input/CTM-DSH site mapping.xlsx", save_file=True)

result = push_plant_to_ctm(
    plant_id="527be9a2-5258-4cda-89cb-b485207a42d0",
    plant_name="ADM Europoort",
    workbook_path=path,
    mapping_df=mapping,
    emission_cols=EMISSION_COLS_ORDER,
    energy_cols=UTILITY_COLS_ORDER,
    use_beta=True,
)

# Print logs
print("\n".join(result["logs"]))

