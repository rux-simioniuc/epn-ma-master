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
import pandas as pd
import ast
import copy

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))


# from DSH2CTM.main import read_csv
from DSH2CTM.streamlit_utils import *
from CONNECT_CTM.utils import push_ctm_scenario_to_etm, get_master_emissions_utilities, get_master_projects


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

if "etm_scenario_id" not in st.session_state:
    st.session_state.etm_scenario_id = ""

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
        value=st.session_state.etm_token,
        type="password",
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
                            )


                            if excel_bytes:
                                
                                file_name = f"{plant_name}.xlsx"
                                st.session_state.generated_files[file_name] = excel_bytes.getvalue()
                            
                                # st.write(f'Done with {plant_name}')
                                print(f'Done with {plant_name}')
                            else:
                                st.write(f"Failed for {plant_name}.")
                        
                    st.success(f"Generated {len(st.session_state.generated_files)} files!")
                
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.session_state.dsh_logs.append(f"ERROR: {e}")
                
        # Show logs if available
        if st.session_state.dsh_logs:
            st.markdown("### Generation Logs")
            with st.container(border=True, height=150):  
                for log_line in st.session_state.dsh_logs:
                    st.text(log_line)
                    
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
    if 'session_json' not in st.session_state:
        st.session_state.session_json = None
    # if 'plant_files' not in st.session_state:
    #     st.session_state.plant_files = None


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
                        from CONNECT_CTM.utils import read_and_transform_mapping, normalize_sector_cluster_mapping

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
                st.session_state.session_json = st.text_area(
                    "Paste session IDs (JSON format)",
                    height=185,
                    help='{("Scenario", "Year"): "SE-xxxxx", \n("Scenario", "Year"): "SE-xxxxx"}',
                )

                if len(st.session_state.session_json) > 0:
                    try:
                        st.session_state.session_json = ast.literal_eval(st.session_state.session_json)
                    except Exception as e:
                        st.error(f'Could not process IDs: {e}')

    # ── Step 3: Push to CTM ────────────────────────────────────────────
    if "result" not in st.session_state:
        st.session_state.result = None
    if "selected_scenarios" not in st.session_state:
            st.session_state.selected_scenarios = None
    if "selected_years" not in st.session_state:
            st.session_state.selected_years = None

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


        if st.button("Start CTM Push", type="primary", disabled=disabled_button):
            # st.info("Push process would start here...")
            try:
                from CONNECT_CTM.push_to_ctm_modules import push_aggregated_by_scenario_year
                from CONNECT_CTM.constants import EMISSION_COLS_ORDER, UTILITY_COLS_ORDER
                from CONNECT_CTM.ctm_constants import TRANSFORMATION_OVERRIDES 
                with st.spinner("Processing..."):

                    st.session_state.result = push_aggregated_by_scenario_year(
                        plants_workbook_dir=plant_files,
                        mapping_df=st.session_state.mapping,
                        emission_cols=EMISSION_COLS_ORDER,
                        energy_cols=UTILITY_COLS_ORDER,
                        transformation_overrides=TRANSFORMATION_OVERRIDES,
                        cluster_sector_file=st.session_state.main_curves_df,
                        cluster_sector_production=st.session_state.production_curves_df,
                        reuse_sessions=st.session_state.session_json,
                        selected_scenarios=st.session_state.selected_scenarios,
                        use_beta=st.session_state.use_beta,
                        reference_year=st.session_state.ref_year,
                        selected_years=st.session_state.selected_years
                    )

                    # print(st.session_state.result)
            except Exception as e:
                st.error(f'Error: {e}')
        
        # Show logs
    
        if st.session_state.result is not None:    
            st.markdown("### Logs")
            with st.container(border=True, height=150):
                for log_line in st.session_state.result['logs']:
                    st.text(log_line)
            st.markdown("### Sessions")
            with st.container(border=True, height=150):
                st.text('{')
                for k, v in st.session_state.result['sessions'].items():
                    st.text(f'{k}: \'{v}\',')
                st.text('}')
            st.markdown("### Errors")
            with st.container(border=True, height=150):
                for errors_log in st.session_state.result['errors']:
                    st.text(errors_log)

        
    # ── Step 4: Push to ETM ────────────────────────────────────────────
    with st.expander("Step 4: Couple to ETM", expanded=False):
        
        if not st.session_state.etm_token:
            st.warning("⚠️ ETM token not set. Add it in the sidebar first.")
        elif not st.session_state.etm_scenario_id:
            st.warning("⚠️ ETM Scenario ID not set. Add it in the sidebar first.")
        else:
            st.success("✓ Credentials ready")

        st.info('Using ETM LIVE version (#latest)')
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Load Existing Sessions")
            st.session_state.etm_session_json = st.text_area(
                "Paste session IDs (JSON format)",
                height=150,
                help='{("Scenario", "Year"): "XXXXXXX"}',
            )

            if len(st.session_state.etm_session_json) > 0:
                try:
                    st.session_state.etm_session_json = ast.literal_eval(st.session_state.etm_session_json)
                    st.success("Session IDs are formatted correctly.")
                except Exception as e:
                    st.error(f'Error processing the session IDs: {e}')


            # use_beta_etm = st.checkbox("Use CTM Beta for ETM coupling", value=True)
            retry_failed = st.checkbox("Retry failed sessions", value=False)
        
        with col2:
            max_retries = st.slider("Max retries per session", 1, 5, 3)
        
        if st.button("Couple to ETM", type="primary"):
            st.session_state.push_logs = []
            if st.session_state.etm_token and st.session_state.etm_session_json:

                st.markdown("### Logs")
                with st.container(border=True, height=150):

                    for (scenario, year) in st.session_state.session_json.keys():
                        # for year in []:
                        ctm_session = st.session_state.session_json[(scenario, year)]

                        etm_session = st.session_state.etm_session_json[(scenario, year)]

                        st.session_state.push_logs.append(f"Pushing {scenario} {year}; CTM {ctm_session} to ETM {etm_session}")
                        st.text(f"Pushing {scenario} {year}; CTM {ctm_session} to ETM {etm_session}")

                        try:
                            aux_result = push_ctm_scenario_to_etm(ctm_session, etm_session, st.session_state.etm_token)
                            st.text(f"Done")
                            st.write(aux_result)
                        except Exception as e:
                            st.text(f"[ERROR]: {e}")
                            st.session_state.push_logs.append(f"[ERROR]: {e}")
                
                st.markdown("### Logs")
                with st.container(border=True, height=150):
                    for log_line in st.session_state.push_logs:
                        st.text(log_line)

                # with st.spinner("Coupling sessions to ETM..."):
                #     # Placeholder for actual ETM coupling logic
                #     st.session_state.push_logs.append("Coupling to ETM...")
                #     st.session_state.push_logs.append("✓ 13/20 sessions coupled successfully")
                #     st.session_state.push_logs.append("✗ 7 sessions failed (502 errors)")
            else:
                st.error("Missing credentials!")
    
    # ── Summary ────────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Plants Processed", "92")
    
    with col2:
        st.metric("CTM Sessions", "20")
    
    with col3:
        st.metric("ETM Coupled", "13/20")
    
    with col4:
        st.metric("Status", "Pending")
    
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
        if st.button("Export Session IDs"):
            session_json = json.dumps(st.session_state.ctm_sessions, indent=2)
            st.download_button(
                label="Download sessions.json",
                data=session_json,
                file_name=f"sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )
    
    with col3:
        if st.button("Clear Cache"):
            st.session_state.push_logs = []
            st.session_state.ctm_sessions = {}
            st.success("Cache cleared")


#''' Extra sidetab '''

st.sidebar.markdown("### Extra options")

disable_master = (not plant_files or st.session_state.mapping.is_empty())
disable_master_projects = not all([
    reference_emissions, 
    reference_utility,  
    project_emission, 
    project_utility, 
    ]) or st.session_state.mapping.is_empty()

with st.sidebar.expander("Download helper files", expanded=False):
    if st.button('Generate Master util/emission File', use_container_width=True, disabled=disable_master):
        try:

            excel_files_dict = {}
            for uploaded_file in plant_files:
                file_name = uploaded_file.name
                file_bytes = uploaded_file.read()
                excel_files_dict[file_name] = file_bytes


            master = get_master_emissions_utilities(
                mapping_df=st.session_state.mapping,
                excel_files_dict = excel_files_dict,
                reference_year = st.session_state.ref_year
                )
            if master is not None:
                # Convert to bytes
                buffer = io.BytesIO()
                master.write_excel(buffer)
                buffer.seek(0)
                excel_bytes_master = buffer.getvalue()
                
                st.download_button(
                    label="Download master_emission_utilities.xlsx",
                    data=excel_bytes_master,
                    file_name="master_emission_utilities.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
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