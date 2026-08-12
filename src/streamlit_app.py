"""
Streamlit interface for CTM/ETM energy data pipeline.
Handles DSH data processing and CTM session management.
"""

import streamlit as st
from pathlib import Path
import json
from datetime import datetime
import zipfile
import io
import polars as pl
import ast
import copy
import gc
import psutil

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))


# from DSH2CTM.main import read_csv
from DSH2CTM.streamlit_utils import *
from CONNECT_CTM.utils import push_ctm_scenario_to_etm, get_master_emissions_utilities, get_master_projects, read_and_transform_mapping, normalize_sector_cluster_mapping
from CONNECT_CTM.push_to_ctm_modules import push_aggregated_by_scenario_year
from CONNECT_CTM.constants import EMISSION_COLS_ORDER, UTILITY_COLS_ORDER
from CONNECT_CTM.ctm_constants import TRANSFORMATION_OVERRIDES 

# Periodically clear memory
def clear_session_cache():
    """Clear unnecessary session state."""
    keys_to_clear = [
        'generated_files',  # Remove if not needed
        'excel_data',       # Remove after processing
        'dsh_logs',         # Keep only last N logs
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    gc.collect()

def show_memory_usage():
    process = psutil.Process()
    mem_mb = process.memory_info().rss / 1024 / 1024
    st.sidebar.metric("Memory Usage", f"{mem_mb:.0f} MB")

show_memory_usage()


# ── Page config ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DSH-CTM-ETM Pipeline",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state initialization ──────────────────────────────────────
if "etm_token" not in st.session_state:
    st.session_state.etm_token = ""

# if "etm_scenario_id" not in st.session_state:
#     st.session_state.etm_scenario_id = ""

if "ctm_sessions" not in st.session_state:
    st.session_state.ctm_sessions = {}

if "push_logs" not in st.session_state:
    st.session_state.push_logs = []

if "generated_files" not in st.session_state:
    st.session_state.generated_files = {}

if "dsh_logs" not in st.session_state:
    st.session_state.dsh_logs = []


# ── Sidebar: Cached credentials ────────────────────────────────────────
st.sidebar.markdown("### Credentials (Cached)")

with st.sidebar.expander("ETM Settings", expanded=False):
    etm_token = st.text_input(
        "ETM Authorization Token",
        # value=st.session_state.etm_token,
        value = 'etm_eyJraWQiOiJkODI5ZTk3YTU4ZDhhOTQyYjg3NGI5ZjNiZWI3ZDJlNGY0MTA5ZjIzNWE0Y2NhMDkzYmU5MzFiMzY1NTlkNGI2IiwiYWxnIjoiUlMyNTYifQ.eyJpc3MiOiJodHRwczovL215LmVuZXJneXRyYW5zaXRpb25tb2RlbC5jb20iLCJpYXQiOjE3ODUzMTI5NDUsImF1ZCI6Imh0dHBzOi8vZW5naW5lLmVuZXJneXRyYW5zaXRpb25tb2RlbC5jb20gaHR0cHM6Ly8yMDI1LTAxLmVuZ2luZS5lbmVyZ3l0cmFuc2l0aW9ubW9kZWwuY29tIiwic2NvcGVzIjoib3BlbmlkIHB1YmxpYyBzY2VuYXJpb3M6cmVhZCBzY2VuYXJpb3M6d3JpdGUiLCJqdGkiOiJjMjZkZWI5Zi05YTM3LTQ3OWQtYjUxYy0zZDM3M2Q3YjE4NmUiLCJzdWIiOjE2NzcyLCJ1c2VyIjp7ImlkIjoxNjc3MiwiYWRtaW4iOmZhbHNlLCJlbWFpbCI6InJ1eGFuZHJhLnNpbWlvbml1Y0B0ZW5uZXQuZXUiLCJuYW1lIjoiUnV4In0sImV4cCI6MTc4NzkwNDk0NX0.tpO0EXw7tFiRrySA3V9HPTw6EDEd2g7RCydM6VOTg2E3LLE3jq9dxRUziz6nZnFAQS_5DJniSAoABbePtDkY9qKOd-vmUTJEyM63COxUxlaJ5Q8NmISJNXVYnj-vsqcjXVO64CzByCx6WVUE9VJh2Gp228hehjjE_HzpLXvonFGQY3pNV92RnFw4rhJAwCE2uWs8_sn1r2Fs9lrAQXNeWKbTUjArmOTMYM-F1ZoqDjnCsdIeEhoKRMI1aNZqauDjH6eSSjy4ltK7dRivwRew0OO8bzfqd7QW6yyZjbhBEH6WzLICwZVQO1zOoH-sxYgmwwenFOYo218fifLZWH8UHg',
        # type="password",
        key="etm_token_input",

    )
    if etm_token:
        st.session_state.etm_token = etm_token
        st.success("Token cached")
    

# ── Main tabs ──────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["DSH Input & Output", "CTM/ETM Workflow"])


# ════════════════════════════════════════════════════════════════════════
# TAB 1: DSH Input & Output
# ════════════════════════════════════════════════════════════════════════

with tab1:

    (plant_export, reference_emissions, reference_utility,
    forecast_emission, forecast_utility, project_emission,
    project_utility, production, flexibility, storage) = (None,) * 10

    expand_all = True
    st.markdown("## DSH Data Processing")
    # st.info("Upload and process DSH files (plant data import)")
    # Initialize
    files = {
        'datasafehouse-plant-export': None,
        'reference_emission': None,
        'reference_utility': None,
        'datasafehouse-emission-forecast-export_all': None,
        'datasafehouse-forecast-export_all': None,
        'datasafehouse-projectdata-export_emissions': None,
        'datasafehouse-projectdata-export_utilities': None,
        'data-export_electricity_production': None,
        'data-export_flex_options': None,
        'data-export_energy_storage': None,
    }

    with st.expander("Upload All Files", expanded=True):
        
        st.markdown("### Upload DSH files")
        
        st.info('File categories are detected from names. If detection fails, use individual uploaders.')

        all_uploads = st.file_uploader(
            "Upload all 10 CSV files",
            type=["csv"],
            key="all_uploads",
            accept_multiple_files=True
        )
        
        
        
        unmatched_files = []
        
        # Process uploads
        for up in all_uploads:
            name = up.name.lower()
            matched = False
            
            for key in files.keys():
                if key.lower() in name:
                    files[key] = up
                    matched = True
                    break
            
            if not matched:
                unmatched_files.append(up.name)
        
        # Show results only if files uploaded
        if all_uploads:
            # Show unmatched files
            if unmatched_files:
                st.error(f"Could not detect category for: {', '.join(unmatched_files)}")
            
            # Check missing files
            missing = [name for name, f in files.items() if f is None]
            
            if missing:
                st.warning(f"Missing files: {', '.join(missing)}")
            else:
                st.success("All required files uploaded!")
                expand_all = False
                
                # Unpack for use
                (plant_export, reference_emissions, reference_utility,
                 forecast_emission, forecast_utility, project_emission,
                 project_utility, production, flexibility, storage) = files.values()
                               
        else:
            st.info("No files uploaded yet")
            expand_all = True
            selected_plants = []
    
    st.divider()
    # st.info('Uploading per category will overwrite the respective file from the batch uploader.')

    if not all([plant_export, 
                    reference_emissions, 
                    reference_utility, 
                    forecast_emission, 
                    forecast_utility, 
                    project_emission, 
                    project_utility, 
                    production, 
                    flexibility, 
                    storage]):

        with st.expander("Step 1: Upload Reference Files", expanded=expand_all):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("### Plant export")
                plant_export = st.file_uploader(
                    "Meta details of plants (plant-export)",
                    type=["csv"],
                    key="plant_export",
                )
                if plant_export:
                    st.success("✓ Plant details loaded")
            
            with col2:
                st.markdown("### Reference Emissions")
                reference_emissions = st.file_uploader(
                    "reference-emission-data",
                    type=["csv"],
                    key="reference_emissions",
                )
                if reference_emissions:
                    st.success("✓ Reference emissions loaded")
            
            with col3:
                st.markdown("### Reference Utility")
                reference_utility = st.file_uploader(
                    "reference-utility-data",
                    type=["csv"],
                    key="reference_utility",
                )
                if reference_utility:
                    st.success("✓ Reference utility loaded")

        with st.expander("Step 2: Upload Forecast Files", expanded=expand_all):
            col1, col2= st.columns(2)

            with col1:
                st.markdown("### Emission forecast")
                forecast_emission = st.file_uploader(
                    "emission-forecast",
                    type=["csv"],
                    key="forecast_emission",
                )
                if forecast_emission:
                    st.success("✓ Emission forecast loaded")
            
            with col2:
                st.markdown("### Utility forecast")
                forecast_utility = st.file_uploader(
                    "forecast-export_all",
                    type=["csv"],
                    key="forecast_utility",
                )
                if forecast_utility:
                    st.success("✓ Utility forecast loaded")
            
        with st.expander("Step 3: Upload Project Files", expanded=expand_all):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Project emissions")
                project_emission = st.file_uploader(
                    "projectdata-export_emissions",
                    type=["csv"],
                    key="project_emission",
                )
                if project_emission:
                    st.success("✓ Projects emissions loaded")
            
            with col2:
                st.markdown("### Project utilities")
                project_utility = st.file_uploader(
                    "projectdata-export_utilities",
                    type=["csv"],
                    key="project_utility",
                )
                if project_utility:
                    st.success("✓ Projects utilities loaded")

        with st.expander("Step 4: Upload production, storage, flexibility", expanded=expand_all):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("### Production")
                production = st.file_uploader(
                    "electricity_production",
                    type=["csv"],
                    key="production",
                )
                if production:
                    st.success("✓ Production loaded")
            
            with col2:
                st.markdown("### Storage")
                storage = st.file_uploader(
                    "energy_storage",
                    type=["csv"],
                    key="storage",
                )
                if storage:
                    st.success("✓ Storage loaded")
            
            with col3:
                st.markdown("### Flexibility")
                flexibility = st.file_uploader(
                    "flex_options",
                    type=["csv"],
                    key="flexibility",
                )
                if flexibility:
                    st.success("✓ Flexibility loaded")
    
        st.divider()

    with st.expander("Scenario Settings", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            scenario_amount = st.number_input(
                label='Number of scenarios',
                value=5,
                min_value=0,
                key='scenario_amount'
                )

            scenario_names = st.text_input(
                label='Scenario names',
                value='Elektrificatie, Midden, VT, Groen gas, Waterstof',
                help='Input the names separated by a comma',
                key='scenario_names'
                )
            try:
                scenario_names_list = [
                    name.strip()
                    for name in scenario_names.split(',')
                    if name.strip()
                ]
                if len(scenario_names_list) != scenario_amount:
                    raise Exception(f"Amount of names ({len(scenario_names_list)}) inconsistent with the number of scenarios ({scenario_amount}).")
            except Exception as e:
                st.error(f'[ERR] Error processing scenario names: {e}')

            
        with col2:
            reference_year = st.number_input(
                label='Reference year',
                value=2024,
                key='reference_year',
                min_value=2010,
                max_value=2100,
                help='must be between 2010 and 2100'
            )


            scenario_years = st.text_input(
                label='Scenario years',
                value='2030, 2035, 2040, 2050',
                help='Input the years separated by a comma',
                key='scenario_years'
                )

            try:
                scenario_years_list = [
                    year.strip()
                    for year in scenario_years.split(',')
                    if year.strip()
                ]
                test_int_list = [int(x) for x in scenario_years_list]
            except Exception as e:
                st.error(f'[ERR] parsing scenario years: {e}')

        st.divider()

    st.markdown("### Generate plant excels")   

    if not all([plant_export, 
                reference_emissions, 
                reference_utility, 
                forecast_emission, 
                forecast_utility, 
                project_emission, 
                project_utility, 
                production, 
                flexibility, 
                storage]):
        st.error('One or more files missing. Check all categories have a file uploaded.')

    else:
        st.success('All files uploaded successfully')

        # Extract plant list for selection
        if plant_export:
            plant_export_df = pl.read_csv(plant_export)
            plant_list = plant_export_df.select(pl.col('Plant name')).to_series().to_list()
            
            st.divider()
            st.markdown("### Select Plants to Process")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                select_all = st.checkbox("Process all plants", value=True)
            
            if select_all:
                selected_plants = plant_list
                st.info(f"Processing all {len(selected_plants)} plants")
            else:
                selected_plants = st.multiselect(
                    "Select plants to process",
                    options=plant_list,
                    default=plant_list,
                )
                if selected_plants:
                    st.info(f"Processing {len(selected_plants)} selected plants")
        
        # Generate plant excels button
        if st.button("Generate plant files", type="primary"):
            st.session_state.generated_files = {}
            st.session_state.dsh_logs = []
            st.markdown("### Generation Logs")
            log_container = st.container(border=True, height=200)
            
            with st.spinner("Loading data..."):
                try:
                    # Map uploaded files to function
                    uploaded_files = {
                        "plants": plant_export,
                        "emission_reference": reference_emissions,
                        "demand_reference": reference_utility,
                        "emission_forecast": forecast_emission,
                        "demand_forecast": forecast_utility,
                        "project_emissions": project_emission,
                        "project_utilities": project_utility,
                        "production": production,
                        "flexibility": flexibility,
                        "storage": storage,
                    }
                    
                    # Load all data
                    data = load_data_streamlit(uploaded_files)
                    print('Loaded data')
                    
                    # Now process plants
                    for plant_id in data["plants"]["Plant identifier"]:  
                        plant_name = get_plant_name(data["plants"], plant_id)
                        if plant_name in selected_plants:

                            print(f'doing {plant_id}')
                            excel_bytes, logs = process_plant_streamlit(
                                plant_id=plant_id,
                                data=data,
                                logs=st.session_state.dsh_logs,
                                n_scenarios=scenario_amount,
                                scenario_names=scenario_names_list,
                                scenario_years=scenario_years_list,
                                reference_year=reference_year,
                                log_container=log_container
                            )

                            if excel_bytes:
                                
                                file_name = f"{plant_name}.xlsx"
                                st.session_state.generated_files[file_name] = excel_bytes.getvalue()
                            
                                print(f'Done with {plant_name}')
                            else:
                                st.write(f"Failed for {plant_name}.")
                        
                    st.success(f"Generated {len(st.session_state.generated_files)} files!")
                
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.session_state.dsh_logs.append(f"ERROR: {e}")
                
        # Download options
        if st.session_state.generated_files:
            st.markdown("### Download Generated Files")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Individual Files")
                for file_name, file_data in st.session_state.generated_files.items():
                    st.download_button(
                        label=f"Download {file_name}",
                        data=file_data,
                        file_name=file_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            
            with col2:
                st.markdown("#### Download All as ZIP")
                
                import zipfile
                import io
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for file_name, file_data in st.session_state.generated_files.items():
                        zip_file.writestr(file_name, file_data)
                
                zip_buffer.seek(0)
                
                st.download_button(
                    label="Download all as ZIP",
                    data=zip_buffer.getvalue(),
                    file_name=f"plant_excels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip",
                )
        


# ════════════════════════════════════════════════════════════════════════
# TAB 2: CTM/ETM Workflow
# ════════════════════════════════════════════════════════════════════════

with tab2:

    if "mapping" not in st.session_state:
        st.session_state.mapping = None
    if 'main_curves_df' not in st.session_state:
        st.session_state.main_curves_df = None
    if 'production_curves_df' not in st.session_state:
        st.session_state.production_curves_df = None
    if 'ref_year' not in st.session_state:
        st.session_state.ref_year = None
    if 'scenario_years' not in st.session_state:
        st.session_state.scenario_years = None
    if 'production_curves_df' not in st.session_state:
        st.session_state.production_curves_df = None
    if 'ctm_sessions' not in st.session_state:
        st.session_state.ctm_sessions = None
    # if 'plant_files' not in st.session_state:
    #     st.session_state.plant_files = None

    len_plants = 0


    st.markdown("## CTM Session Management & ETM Coupling")
    with st.expander("Instructions and Details", expanded=True):
        st.markdown("##### File formats")
        
    
    # ── Step 1: Upload files ───────────────────────────────────────────
    with st.expander("Step 1: Upload Data Files", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### Plant Workbooks")
            plant_files = st.file_uploader(
                "Upload plant Excel files",
                type=["xlsx"],
                accept_multiple_files=True,
                key="plant_files",
            )
            if plant_files:
                st.success(f"✓ {len(plant_files)} files uploaded")  
                len_plants = len(plant_files)
                # st.session_state.plant_files = plant_files                    
        with col2:
            st.markdown("### Mapping File")
            mapping_file = st.file_uploader(
                "Upload DSH to CTM mapping file",
                type=["csv", "xlsx"],
                key="mapping_file",
                accept_multiple_files=False
                        )
            st.write('*Use the pre-processed csv mapping file when possible. The file is avl for download after uploading the excel.*')
            if mapping_file:
                if st.button('Load and process mapping file', type='primary'):
                    try:

                        if mapping_file.name.split('.')[-1] == 'csv':
                            st.session_state.mapping = read_csv_streamlit(mapping_file)
                            st.session_state.mapping = normalize_sector_cluster_mapping(st.session_state.mapping)
                        else:
                            import polars as pl
                            st.session_state.mapping = pl.read_excel(mapping_file)
                                                        
                            st.session_state.mapping = read_and_transform_mapping(
                                excel_path=None,
                                mapping_df=st.session_state.mapping,
                                save_file=False,
                                normalize_sector_cluster=True
                            )
                        st.success('Mapping processed successfully')
                        # st.session_state.push_logs.append('Mapping processed successfully')
                        if mapping_file.name.split('.')[-1] == 'xlsx':
                            st.download_button(
                                label=f"Download mapping.csv",
                                data=st.session_state.mapping.write_csv().encode('utf-8'),
                                file_name='mapping.csv',
                                mime="text/csv",
                            )
                    except Exception as e:
                        st.error(f'Error loading and processing mapping file: {e}')
        
        with col3:
            st.markdown("### Cluster/Sector Curves")
            curves_file = st.file_uploader(
                "Upload cluster curves",
                type=["xlsx"],
                key="curves_file",
                accept_multiple_files=False
            )
            if curves_file:
                col31, col32 = st.columns(2)
                with col31:
                    curve_sheet = st.text_input('Cluster/Sector sheet name', value='resultaat', width=200)
                with col32:
                    production_sheet = st.text_input('Production sheet name', value='wkk rest', width=200)

                if st.button('Load and process cluster/sector curves file', type='primary'):
                    try:
                        st.session_state.main_curves_df = pl.read_excel(curves_file, sheet_name=curve_sheet)
                        st.session_state.production_curves_df = pl.read_excel(curves_file, sheet_name=production_sheet)
                        st.success('Curves processed successfully')
                    except Exception as e:
                        st.error(f'Error loading and processing curve file: {e}')

    # ── Step 2: Session options ────────────────────────────────────────

    with st.expander("Step 2: Settings", expanded=False):
        col1, col2 = st.columns(2)
        
        with col2:
            with st.container(border=True):

                if plant_files:
                    example_file = copy.copy(plant_files[0])
                    (scenarios, years) = extract_scenario_years(example_file)
                    ref_year = years[0]
                    years = years[1:]
                else:
                    scenarios, years, ref_year = [], [], ''


                ref_year = st.text_input('Reference year', value = ref_year, width=200)
                st.session_state.ref_year = ref_year
                scenario_yrs = st.text_input('Scenario years', value = ', '.join(years), width=200)
                scenario_years = scenario_yrs.replace(' ', '').split(',')

                scenario_names = st.text_input('Scenario names', value = ', '.join(scenarios))
                scenario_names = scenario_names.strip(' ').split(',')
                scenario_names = [i.strip(' ') for i in scenario_names]

                st.write('*The years and scenarios are extracted from the uploaded plant excel files. If changed, they might yield errors.*')

        with col1:
            st.session_state.use_beta = st.checkbox("Use CTM Beta", value=True)
            create_new = st.checkbox("Create New Sessions", value=True)

            if not create_new:
                st.markdown("### Load Existing Sessions")
                st.markdown("##### Direct pasting has priority.")

                sessions = {}
                
                ctm_sessions_file = st.file_uploader(
                    "Upload ctm session mapping file",
                    type=["json"],
                    key="ctm_sessions_file",
                    accept_multiple_files=False
                    )

                # Option 1: Upload JSON file
                if ctm_sessions_file is not None:
                    try:
                        data = json.load(ctm_sessions_file)

                        sessions = {
                            ast.literal_eval(k): v
                            for k, v in data.items()
                        }

                        st.success(f"{len(sessions)} session IDs uploaded successfully!")

                    except Exception as e:
                        st.error(f"Could not read the file: {e}")


                # Option 2: Paste session IDs
                pasted_sessions = st.text_area(
                    "OR paste session IDs",
                    height=185,
                    # help="Accepts JSON or Python dict format",
                    help='{("Scenario", "Year"): "SE-xxxxx"} OR {\'("Scenario", "Year")\': "SE-xxxxx"}',
                )

                if pasted_sessions.strip():
                    try:
                        data = ast.literal_eval(pasted_sessions)

                        sessions = {
                            (k if isinstance(k, tuple) else ast.literal_eval(k)): v
                            for k, v in data.items()
                        }

                        st.success(f"{len(sessions)} session IDs pasted successfully!")

                    except Exception as e:
                        st.error(f"Could not process IDs: {e}")


                if sessions:
                    st.session_state.ctm_sessions = sessions


    # ── Step 3: Push to CTM ────────────────────────────────────────────
    if "result" not in st.session_state:
        st.session_state.result = None
    if "selected_scenarios" not in st.session_state:
        st.session_state.selected_scenarios = None
    if "selected_years" not in st.session_state:
        st.session_state.selected_years = None
    if "etm_session_json" not in st.session_state:
        st.session_state.etm_session_json = None

    with st.expander("Step 3: Push to CTM", expanded=False):
        #TODO add some curve + mapping validation here

        st.session_state.selected_scenarios = st.multiselect(
                            "Select scenarios",
                            options=scenario_names,
                            default=scenario_names,
                        )

        st.session_state.selected_years = st.multiselect(
                                    "Select years",
                                    options=scenario_years,
                                    default=scenario_years,
                                )

        if len(st.session_state.selected_scenarios) == 0 or len(st.session_state.selected_years) == 0:
            st.error('Select at least one year and one scenario to push to CTM.')
            disabled_button = True 
        else:
            disabled_button = False


        if st.button("Push to CTM", type="primary", disabled=disabled_button):
            log_container = st.container(border=True, height=300)
            # st.info("Push process would start here...")
            try:
                with st.spinner("Processing..."):

                    st.session_state.result = push_aggregated_by_scenario_year(
                        plants_workbook_dir=plant_files,
                        mapping_df=st.session_state.mapping,
                        emission_cols=EMISSION_COLS_ORDER,
                        energy_cols=UTILITY_COLS_ORDER,
                        transformation_overrides=TRANSFORMATION_OVERRIDES,
                        cluster_sector_file=st.session_state.main_curves_df,
                        cluster_sector_production=st.session_state.production_curves_df,
                        reuse_sessions=st.session_state.ctm_sessions,
                        selected_scenarios=st.session_state.selected_scenarios,
                        use_beta=st.session_state.use_beta,
                        reference_year=st.session_state.ref_year,
                        selected_years=st.session_state.selected_years,
                        log_container=log_container
                    )

                    # print(st.session_state.result)
            except Exception as e:
                st.error(f'Error: {e}')

        # Show logs    
        if st.session_state.result is not None:    
            st.markdown("### Sessions")
            with st.container(border=True, height=150):
                st.text('{')
                for k, v in st.session_state.result['sessions'].items():
                    st.text(f'{k}: \'{v}\',')
                st.text('}')
            # if st.button("Export Session IDs"):

            sessions = st.session_state.result["sessions"]

            session_json = json.dumps(
                {str(key): value for key, value in sessions.items()},
                indent=2
            )

            st.download_button(
                label="Download sessions.json",
                data=session_json,
                file_name=f"ctm_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

        
    # ── Step 4: Push to ETM ────────────────────────────────────────────
    with st.expander("Step 4: Couple to ETM", expanded=False):
        
        if not st.session_state.etm_token:
            st.warning("⚠️ ETM token not set. Add it in the sidebar first.")
        # elif not st.session_state.etm_scenario_id:
        #     st.warning("⚠️ ETM Scenario ID not set. Add it in the sidebar first.")
        else:
            st.success("✓ Credentials ready")

        st.info('Using ETM LIVE version (#latest)')
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Load ETM Sessions")

            sessions = {}
                            
            etm_sessions_file = st.file_uploader(
                "Upload etm session mapping file",
                type=["json"],
                key="etm_sessions_file",
                accept_multiple_files=False
                )

            # Option 1: Upload JSON file
            if etm_sessions_file is not None:
                try:
                    data = json.load(etm_sessions_file)

                    sessions = {
                        ast.literal_eval(k): v
                        for k, v in data.items()
                    }

                    st.success(f"{len(sessions)} ETM session IDs uploaded successfully!")

                except Exception as e:
                    st.error(f"Could not read the file: {e}")


            # Option 2: Paste session IDs
            pasted_etm_sessions = st.text_area(
                "OR paste session IDs",
                height=185,
                # help="Accepts JSON or Python dict format",
                help='{("Scenario", "Year"): "xxxxx"} OR {\'("Scenario", "Year")\': "xxxxx"}',
            )

            if pasted_etm_sessions.strip():
                try:
                    data = ast.literal_eval(pasted_etm_sessions)

                    sessions = {
                        (k if isinstance(k, tuple) else ast.literal_eval(k)): v
                        for k, v in data.items()
                    }

                    err = 0

                    for k, v in sessions.items():
                        if 'SE' in v or len(v) != 7:
                            st.error('IDs do not match the ETM pattern: must have 7 digits and must NOT contain SE')
                            err = 1
                            continue
                    if err == 0:
                        st.success(f"{len(sessions)} session IDs pasted successfully!")

                except Exception as e:
                    st.error(f"Could not process IDs: {e}")


            if sessions:
                st.session_state.etm_session_json = sessions

            # use_beta_etm = st.checkbox("Use CTM Beta for ETM coupling", value=True)
            retry_failed = st.checkbox("Retry failed sessions", value=False)
        
        with col2:
            max_retries = st.slider("Max retries per session", 1, 5, 3)

        success_push = 0
        failed_push = 0
        
        if st.button("Couple to ETM", type="primary"):
            st.session_state.push_logs = []
            if st.session_state.etm_token and st.session_state.etm_session_json:

                st.markdown("### Logs")
                log_container = st.container(border=True, height=300)

                for (scenario, year) in st.session_state.ctm_sessions.keys():
                    ctm_session = st.session_state.ctm_sessions[(scenario, year)]

                    etm_session = st.session_state.etm_session_json[(scenario, year)]

                    msg = f"Pushing {scenario} {year}; CTM {ctm_session} to ETM {etm_session}"
                    st.session_state.push_logs.append(msg)
                    log_container.text(msg)

                    # Retry loop
                    aux_result = None
                    for attempt in range(max_retries):
                        try:
                            aux_result = push_ctm_scenario_to_etm(
                                ctm_session, 
                                etm_session, 
                                st.session_state.etm_token,
                                log_container=log_container
                            )
                            
                            if aux_result is not None:
                                log_container.text(f"✓ Success on attempt {attempt + 1}")
                                # st.session_state.push_logs.append(f"✓ Success")
                                break  # Exit retry loop on success
                            else:
                                if attempt < max_retries - 1:  # Don't log on last attempt
                                    log_container.text(f"✗ Failed attempt {attempt + 1}, retrying...")
                                    import time
                                    time.sleep(1)  # ← Add delay between retries
                                else:
                                    log_container.text(f"✗ Failed after {max_retries} attempts")
                                    st.session_state.push_logs.append(f"✗ Failed after {max_retries} retries")
                        
                        except Exception as e:
                            if attempt < max_retries - 1:
                                log_container.text(f"[ERROR] Attempt {attempt + 1}: {e}, retrying...")
                                import time
                                time.sleep(1)
                            else:
                                log_container.text(f"[ERROR] Failed after {max_retries} attempts: {e}")
                                st.session_state.push_logs.append(f"[ERROR]: {e}")
                    
                    if aux_result is None:
                        log_container.text(f"✗ {scenario}/{year} FAILED")
                        fail_push += 1
                    else:
                        log_container.text(f"✓ {scenario}/{year} SUCCESS")
                        success_push += 1

            else:
                st.error("Missing credentials!")

    # ── Summary ────────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Plants Processed", len_plants)
    
    with col2:
        st.metric("CTM Sessions", len(st.session_state.ctm_sessions or {}))
    
    with col3:
        st.metric("ETM Coupled", f"{success_push}/{len(st.session_state.etm_session_json or {})}")
    
    with col4:
        st.metric("ETM Failed", f"{failed_push}/{len(st.session_state.etm_session_json or {})}")

    # ── Export results ─────────────────────────────────────────────────
    st.divider()
    st.markdown("### Export Results")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("Download Logs"):
            log_text = "\n".join(st.session_state.push_logs)
            st.download_button(
                label="Download push_logs.txt",
                data=log_text,
                file_name=f"push_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
            )
    
    with col2:

        if len(st.session_state.etm_session_json or {}) > 0:

            session_json = json.dumps(
                {str(key): value for key, value in st.session_state.etm_session_json.items()},
                indent=2
            )

            st.download_button(
                label="Download etm_sessions.json",
                data=session_json,
                file_name=f"etm_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )
    
    with col3:
        if st.button("Clear Cache"):
            # st.session_state.push_logs = []
            # st.session_state.ctm_sessions = {}
            # st.session_state.mapping = None
            # st.session_state.ref_year = None
            # st.session_state.ctm_sessions = {}
            clear_session_cache()
            st.success("Cache cleared")
            # gc.collect()

#''' Extra sidetab '''

st.sidebar.markdown("### Extra options")

disable_master = (not plant_files or st.session_state.mapping is None or st.session_state.mapping.is_empty())
disable_master_projects = not all([
    reference_emissions, 
    reference_utility,  
    project_emission, 
    project_utility, 
    ]) or st.session_state.mapping.is_empty()

with st.sidebar.expander("Download helper files", expanded=False):
    if st.button('Generate Master util/emission File', use_container_width=True, disabled=disable_master):
        try:
            master = None
            log_area = st.empty()
            
            # Process files ONE at a time
            for i, uploaded_file in enumerate(plant_files):
                log_area.text(f"Processing {i+1}/{len(plant_files)}: {uploaded_file.name}")
                
                file_bytes = uploaded_file.read()
                
                # Pass SINGLE file dict
                chunk = get_master_emissions_utilities(
                    mapping_df=st.session_state.mapping,
                    excel_files_dict={uploaded_file.name: file_bytes},  # ← Single file
                    reference_year=st.session_state.ref_year
                )
                
                # Combine results
                if chunk is not None and not chunk.is_empty():
                    if master is None:
                        master = chunk
                    else:
                        master = pl.concat([master, chunk], how="vertical_relaxed")
                
                # Clear memory
                del file_bytes
                del chunk
                gc.collect()
            
            if master is not None:
                buffer = io.BytesIO()
                master.write_excel(buffer)
                buffer.seek(0)
                
                st.download_button(
                    label="Download master_emission_utilities.xlsx",
                    data=buffer.getvalue(),
                    file_name="master_emission_utilities.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                
                # Clear
                del master
                del buffer
                gc.collect()
                log_area.text("✓ Complete!")
                
        except Exception as e:
            st.error(f'[ERROR]: {e}')

    if disable_master:
            st.warning('plant files and mapping', title='Upload files')  
    if st.button('Generate Master Projects File', use_container_width=True, disabled=disable_master_projects):
        st.write('Yey')
        try:
            master_projects = get_master_projects(
                mapping_df=st.session_state.mapping,
                reference_emission_df=read_csv_streamlit(reference_emissions),
                reference_utility_df=read_csv_streamlit(reference_utility),
                projects_emission_df=read_csv_streamlit(project_emission),
                projects_utility_df=read_csv_streamlit(project_utility),
                REF_YEAR = st.session_state.ref_year
                )
            if master_projects is not None:
                # Convert to bytes
                buffer = io.BytesIO()
                master_projects.write_excel(buffer)
                buffer.seek(0)
                excel_bytes_projects = buffer.getvalue()
                
                st.download_button(
                    label="Download master_project.xlsx",
                    data=excel_bytes_projects,
                    file_name="master_project.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        except Exception as e:
            st.error(f'[ERROR]: {e}')
        
    if disable_master_projects:
        st.warning('mapping, DSH files (reference + projects)', title='Upload files')  


# ── Footer ─────────────────────────────────────────────────────────────
st.divider()
st.caption("DSH-CTM-ETM Pipeline | v1.0")