
from read_DSH_files import *
from utils import *

from push_to_ctm_modules import *
from constants import EMISSION_COLS_ORDER, UTILITY_COLS_ORDER
from ctm_constants import TRANSFORMATION_OVERRIDES

xlsx_path = '/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm/input/test_input'
mapping_path = '/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm/input/CTM-DSH site mapping.xlsx'

# these are very old sessions
# sessions = {
#     ("Elektrificatie", "2030"): "SE-89f8540c58b9fc6a",
#     ("Elektrificatie", "2035"): "SE-19d830420db7f899",
#     ("Elektrificatie", "2040"): "SE-da08be308c9a4556",
#     ("Elektrificatie", "2050"): "SE-c5332b6227c5c4c2",

#     ("Midden", "2030"): "SE-8a908306100118e4",
#     ("Midden", "2035"): "SE-9803ea651d4b0624",
#     ("Midden", "2040"): "SE-1c5a78163215a601",
#     ("Midden", "2050"): "SE-48093e0f349a59a4",

#     ("Groen gas", "2030"): "SE-cc671dd37573c664",
#     ("Groen gas", "2035"): "SE-ce856785a8d4a023",
#     ("Groen gas", "2040"): "SE-52168f1bb3ea0e92",
#     ("Groen gas", "2050"): "SE-1d9b959dd009ac23",

#     ("VT", "2030"): "SE-cde60c34e93c8291",
#     ("VT", "2035"): "SE-3ede563331a92306",
#     ("VT", "2040"): "SE-1992a16c210555c9",
#     ("VT", "2050"): "SE-7cffed6e5c0c57f2",

#     ("Waterstof", "2030"): "SE-241292136d54292b",
#     ("Waterstof", "2035"): "SE-dc41aa7fc36b5131",
#     ("Waterstof", "2040"): "SE-bc28ad038daa5694",
#     ("Waterstof", "2050"): "SE-e2c3305ca0f9f95e",
# }


sessions = {
    ("Elektrificatie", "2030"): "SE-ad8f11f8e02c59cc",
    ("Elektrificatie", "2035"): "SE-30569a0bed67948d",
    ("Elektrificatie", "2040"): "SE-1baebb319fba5ba6",
    ("Elektrificatie", "2050"): "SE-5f2344f47588521f",

    ("Midden", "2030"): "SE-ffa162d5308c29bf",
    ("Midden", "2035"): "SE-7562a845fc791712",
    ("Midden", "2040"): "SE-752d12b7d4c050bb",
    ("Midden", "2050"): "SE-543d8ec4a87bfab7",

    ("Groen gas", "2030"): "SE-827492f3dc78c59d",
    ("Groen gas", "2035"): "SE-27308488ea42f3e7",
    ("Groen gas", "2040"): "SE-ae83f46207d384cc",
    ("Groen gas", "2050"): "SE-f36b215869cf13c7",

    ("VT", "2030"): "SE-16fa5e5a751cdb47",
    ("VT", "2035"): "SE-4630c0537179025e",
    ("VT", "2040"): "SE-818f593b41ac9c87",
    ("VT", "2050"): "SE-2fed91be8ca55119",

    ("Waterstof", "2030"): "SE-70fc26a187609ef2",
    ("Waterstof", "2035"): "SE-95758114a80f1d93",
    ("Waterstof", "2040"): "SE-3eaae100a90058e9",
    ("Waterstof", "2050"): "SE-ef1092beb13732e1",
}


SCENARIOS_iter = [
    ['Elektrificatie', 'Midden'],
    ['VT', 'Groen gas'],
    ['Waterstof']
]

# mapping_df = read_and_transform_mapping(excel_path='/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm/input/20260709 sprint 3 CTM-DSH site mapping.xlsx',
#                                         save_file=True,
#                                         save_path='',
#                                         normalize_sector_cluster=True)
mapping_df = pl.read_csv('/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm_sprint_3/mapping.csv')

i = 0
for scen_list in SCENARIOS_iter:
# for scen_list in ['Elektrificatie']:

    print(f'Processing {scen_list}')
i+=1

result = push_aggregated_by_scenario_year(
    plants_workbook_dir="/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm_sprint_3/Sprint 3 CTM upload_rest",
    # plants_workbook_dir="/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm/input/test_input2",
    mapping_df= mapping_df,
    emission_cols=EMISSION_COLS_ORDER,
    energy_cols=UTILITY_COLS_ORDER,
    transformation_overrides=TRANSFORMATION_OVERRIDES,
    cluster_sector_file="/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm_sprint_3/ctm format curves.xlsx",
    cluster_sector_curves_sheet_name='resultaat',
    cluster_sector_production_sheet_name='wkk rest',
    reuse_sessions=sessions,
    output_log_file=f'/home/307920@ontw.alfa.local/projects/epn-ma-master/src/CONNECT_CTM/logs/test_log_half{i}.txt',
    # selected_scenarios=scen_list,
    # selected_years=['2040'],
    session_path='/home/307920@ontw.alfa.local/projects/epn-ma-master/src/CONNECT_CTM/logs/sessions/07_08_r2'
)

files = write_push_logs(result, "/home/307920@ontw.alfa.local/projects/epn-ma-master/src/CONNECT_CTM/logs/")
print(f"Logs saved to: {files['folder']}")
print(f"  - {files['logs_file']}")
print(f"  - {files['sessions_file']}")
print(f"  - {files['errors_file']}")
print(f"  - {files['summary_file']}")

# Production inputs automatically included if available
print('x')


# maps = read_and_transform_mapping("/home/307920@ontw.alfa.local/projects/epn-ma-master/data/ctm/input/CTM-DSH site mapping.xlsx", 
#                                   save_file=True)



# coords for qemetica and Delfzijl nieuw
# lat = "53.30315087671532"
# lon = "6.986967610715365"

# qemetica_ctm_name = "##new_cc_site17##"
# delfzijl_ctm_name = "##new_cc_site9##"

# inputs = {}
# for site in [qemetica_ctm_name, delfzijl_ctm_name]:
#     inputs[f"{site}&&latitude"] = str(lat)
#     inputs[f"{site}&&longitude"] = str(lon)

# for k, v in sessions.items():
#     ctm = CTMClient(use_beta=True)
#     ctm.load_session(v)
#     ctm.set_inputs(inputs)





