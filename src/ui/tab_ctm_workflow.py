"""
Tab 2: CTM/ETM Workflow — upload plant workbooks + mapping + curves, push to
CTM (Step 3), couple to ETM (Step 4), plus a session-clearing utility.

Stores uploaded plant_files into st.session_state.plant_files so
sidebar_downloads.py (master energy balance / units overview) can use them
without needing them passed in directly.
"""

import streamlit as st
import polars as pl
import json
import ast
import zipfile
import io
from datetime import datetime

from ui.streamlit_utils import (
    extract_scenario_years_multi, parse_custom_inputs_string, get_mapping_df
)

from ui.sidebar_credentials import clear_session_cache

from CONNECT_CTM.connect_to_etm import couple_all_sessions_to_etm
from CONNECT_CTM.utils.utils import clear_session, check_plants_in_mapping
from CONNECT_CTM.utils.constants import EMISSION_COLS_ORDER, UTILITY_COLS_ORDER
from CONNECT_CTM.ctm_push import push_aggregated_by_scenario_year
from CONNECT_CTM.utils.models import DEFAULT_TRANSFORMATION_OVERRIDES


def _init_state():
    defaults = {
        "mapping": None, 
        "main_curves_df": None, 
        "production_curves_df": None,
        "ref_year": None, 
        "scenario_years": None, 
        "ctm_sessions": None,
        "all_data": None, 
        "result": None, 
        "selected_scenarios": None,
        "selected_years": None, 
        "etm_session_json": None, 
        "plant_files": None,
        "push_logs": [],
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def render_ctm_workflow_tab():
    """Renders Tab 2. Returns len(plant_files) for the sidebar plant-count metric."""
    _init_state()

    len_plants = 0
    success_push = 0
    failed_push = 0

    st.markdown("## CTM Session Management & ETM Coupling")
    # with st.expander("Instructions and Details", expanded=True):
    #     st.markdown("##### File formats")

    # ── Step 1: Upload files ───────────────────────────────────────────
    with st.expander("Step 1: Upload Data Files", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("### Plant Workbooks")
            plant_files = st.file_uploader(
                "Upload plant Excel files", 
                type=["xlsx"], 
                accept_multiple_files=True, 
                key="plant_files_uploader",
            )
            if plant_files:
                st.success(f"✓ {len(plant_files)} files uploaded")
                len_plants = len(plant_files)
                st.session_state.plant_files = plant_files  # exposed for sidebar downloads

                if st.button(
                    'Aggregate the data', use_container_width=True, key='get_only_data',

                    disabled=(st.session_state.mapping is None or st.session_state.mapping.is_empty()),
                ):
                    res = push_aggregated_by_scenario_year(
                        plants_workbook_dir=plant_files.copy(),
                        mapping_df=st.session_state.mapping,
                        only_load_scenario_data=True,
                        reference_year='0',
                    )
                    st.session_state.all_data = res['data']

        with col2:
            st.markdown("### Mapping File")
            mapping_file = st.file_uploader(
                "Upload DSH to CTM mapping file", 
                type=["csv", "xlsx"], 
                key="mapping_file", 
                accept_multiple_files=False,
            )
            st.write('*Use the pre-processed csv mapping file when possible. The file is avl for download after uploading the excel.*')
            if mapping_file:
                if st.button('Load and process mapping file', type='primary'):
                    try:
                        st.session_state.mapping = get_mapping_df(mapping_file)
                        st.success('Mapping processed successfully')

                        if mapping_file.name.split('.')[-1] == 'xlsx':
                            st.download_button(
                                label="Download mapping.csv",
                                data=st.session_state.mapping.write_csv().encode('utf-8'),
                                file_name='mapping.csv', mime="text/csv",
                            )
                    except Exception as e:
                        st.error(f'[ERR]: {e}')

        if st.session_state.plant_files is not None and st.session_state.mapping is not None:
            missing_plants = check_plants_in_mapping(plant_files, st.session_state.mapping)
            if len(missing_plants) > 0:
                st.warning(f'Plants missing from mapping: {missing_plants}')
            else:
                st.success('No plants missing from mapping')

            st.dataframe(st.session_state.mapping.filter(pl.col('Name').str.contains('Cargill')))

        with col3:
            st.markdown("### Cluster/Sector Curves")
            curves_file = st.file_uploader(
                "Upload cluster curves", 
                type=["xlsx"], 
                key="curves_file", 
                accept_multiple_files=False,
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
                        st.error(f'[ERR]: {e}')

    # ── Step 2: Session options ────────────────────────────────────────
    scenario_names, scenario_years = [], []

    with st.expander("Step 2: Settings", expanded=False):
        col1, col2 = st.columns(2)

        with col2:
            with st.container(border=True):
                if plant_files:
                    scenarios, years = extract_scenario_years_multi(plant_files)
                    ref_year = years[0]
                    years = years[1:]
                else:
                    scenarios, years, ref_year = [], [], ''

                ref_year = st.text_input('Reference year', value=ref_year, width=200)
                st.session_state.ref_year = ref_year
                scenario_yrs = st.text_input('Scenario years', value=', '.join(years), width=200)
                scenario_years = scenario_yrs.replace(' ', '').split(',')

                scenario_names = st.text_input('Scenario names', value=', '.join(scenarios))
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
                    accept_multiple_files=False,
                )

                if ctm_sessions_file is not None:
                    try:
                        data = json.load(ctm_sessions_file)
                        sessions = {ast.literal_eval(k): v for k, v in data.items()}
                        st.success(f"{len(sessions)} session IDs uploaded successfully!")
                    except Exception as e:
                        st.error(f"Could not read the file: {e}")

                pasted_sessions = st.text_area(
                    "OR paste session IDs", height=185,
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
                        st.error(f'[ERR]: {e}')

                if sessions:
                    st.session_state.ctm_sessions = sessions

    # ── Step 3: Push to CTM ────────────────────────────────────────────
    with st.expander("Step 3: Push to CTM", expanded=False):
        st.session_state.selected_scenarios = st.multiselect(
            "Select scenarios", options=scenario_names, default=scenario_names,
        )
        st.session_state.selected_years = st.multiselect(
            "Select years", options=scenario_years, default=scenario_years,
        )

        disabled_button = len(st.session_state.selected_scenarios) == 0 or len(st.session_state.selected_years) == 0
        if disabled_button:
            st.error('Select at least one year and one scenario to push to CTM.')

        extra_inputs_input = st.text_area(
            label='Enter additional inputs', 
            height=200, 
            key='extra_inputs',
            help='{api_name1: value1, api_name2: value2}',
            # FIX: ALL_OVERRIDES was removed from ctm_constants during the refactor,
            # replaced by DEFAULT_TRANSFORMATION_OVERRIDES in models.py
            value="{\n" + "\n".join(
                f"    {k}: {v}," for k, v in DEFAULT_TRANSFORMATION_OVERRIDES.items()
            ) + "\n}",
        )


        set_empty_to_zero = st.toggle('Set empty values to 0', value=False)
        st.write(set_empty_to_zero)

        extra_inputs = {}
        if extra_inputs_input:
            try:
                extra_inputs = parse_custom_inputs_string(extra_inputs_input)
            except Exception as e:
                st.error(f"[ERR] Error parsing the extra inputs: {e}")

        if st.button("Push to CTM", type="primary", disabled=disabled_button):
            log_container = st.container(border=True, height=300)
            try:
                with st.spinner("Processing..."):
                    st.session_state.result = push_aggregated_by_scenario_year(
                        plants_workbook_dir=plant_files,
                        mapping_df=st.session_state.mapping,
                        emission_cols=EMISSION_COLS_ORDER,
                        energy_cols=UTILITY_COLS_ORDER,
                        extra_inputs=extra_inputs,
                        cluster_sector_file=st.session_state.main_curves_df,
                        cluster_sector_production=st.session_state.production_curves_df,
                        reuse_sessions=st.session_state.ctm_sessions,
                        selected_scenarios=st.session_state.selected_scenarios,
                        selected_years=st.session_state.selected_years,
                        use_beta=st.session_state.use_beta,
                        reference_year=st.session_state.ref_year,
                        log_container=log_container,
                        set_empty_to_zero = set_empty_to_zero
                    )
            except Exception as e:
                st.error(f'[ERR]: {e}')

        if st.session_state.result is not None:
            st.markdown("### Sessions")
            with st.container(border=True, height=150):
                st.text('{')
                for k, v in st.session_state.result['sessions'].items():
                    st.text(f'{k}: \'{v}\',')
                st.text('}')

            sessions = st.session_state.result["sessions"]
            session_json = json.dumps({str(key): value for key, value in sessions.items()}, indent=2)

            st.download_button(
                label="Download sessions.json", data=session_json,
                file_name=f"ctm_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

            if st.session_state.result.get("all_inputs"):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for (scenario, year), inputs in st.session_state.result["all_inputs"].items():
                        file_name = f"{scenario}_{year}.json".replace(" ", "_")
                        zip_file.writestr(file_name, json.dumps(inputs, indent=2))
                zip_buffer.seek(0)

                st.download_button(
                    label="Download all pushed inputs (ZIP)", 
                    data=zip_buffer.getvalue(),
                    file_name=f"ctm_inputs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip",
                )

    # ── Step 4: Push to ETM ────────────────────────────────────────────
    with st.expander("Step 4: Couple to ETM", expanded=False):
            
        if not st.session_state.etm_token:
            st.warning("⚠️ ETM token not set. Add it in the sidebar first.")
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
            if st.session_state.etm_token and st.session_state.etm_session_json:

                st.markdown("### Logs")
                log_container = st.container(border=True, height=300)

                res_push, logs = couple_all_sessions_to_etm(
                    ctm_sessions=st.session_state.ctm_sessions, 
                    etm_sessions=st.session_state.etm_session_json,
                    etm_token=st.session_state.etm_token,
                    max_retries=max_retries,
                    retry_delay_seconds=1.0,
                    log_container=log_container
                )

            else:
                st.error("Missing credentials!")

    # ── Extra option: clear CTM sessions ────────────────────────────────
    with st.expander("Extra option: Clear CTM sessions.", expanded=False):
        st.write('IMPORTANT: not 100% tested. Should work, but the best option is to create new sessions.')
        scenarios_to_clear = st.text_area(
            label="Paste the CTM session IDs. Paste the IDs separated by a comma. Can be on new lines or on the same line.",
        )

        scenarios_clear_list = scenarios_to_clear.strip().replace('\n', '').replace(' ', '').replace("'", '').replace('"', '').split(',')
        if '' in scenarios_clear_list:
            scenarios_clear_list.remove('')

        if st.button('Clear sessions'):
            try:
                for s in scenarios_clear_list:
                    clear_session(session_id=s)
                    st.write(f'Done with {s}')
                st.success('All done')
            except Exception as e:
                st.error(f"[ERROR]: {e}")

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

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Download Logs"):
            log_text = "\n".join(st.session_state.push_logs)
            st.download_button(
                label="Download push_logs.txt", data=log_text,
                file_name=f"push_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", mime="text/plain",
            )

    with col2:
        if len(st.session_state.etm_session_json or {}) > 0:
            session_json = json.dumps(
                {str(key): value for key, value in st.session_state.etm_session_json.items()}, indent=2,
            )
            st.download_button(
                label="Download etm_sessions.json", data=session_json,
                file_name=f"etm_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", mime="application/json",
            )

    return len_plants
