"""
Tab 1: DSH Input & Output — upload the 10 DSH CSV exports, set scenario
settings, generate one Excel workbook per plant.

Stores the uploaded DSH file objects into st.session_state.dsh_files so
sidebar_downloads.py (Generate Master Projects File) can use them without
needing them passed in directly.
"""

import streamlit as st
import polars as pl
import zipfile
import io
from datetime import datetime

from ui.streamlit_utils import (
    load_data_streamlit, get_plant_name, process_plant_streamlit,
)


def render_dsh_input_tab():
    if "generated_files" not in st.session_state:
        st.session_state.generated_files = {}
    if "dsh_logs" not in st.session_state:
        st.session_state.dsh_logs = []
    if "dsh_files" not in st.session_state:
        st.session_state.dsh_files = {}

    (plant_export, reference_emissions, reference_utility,
     forecast_emission, forecast_utility, project_emission,
     project_utility, production, flexibility, storage) = (None,) * 10

    expand_all = True
    st.markdown("## DSH Data Processing")

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
            accept_multiple_files=True,
        )

        unmatched_files = []
        selected_plants = []

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

        if all_uploads:
            if unmatched_files:
                st.error(f"Could not detect category for: {', '.join(unmatched_files)}")

            missing = [name for name, f in files.items() if f is None]

            if missing:
                st.warning(f"Missing files: {', '.join(missing)}")
            else:
                st.success("All required files uploaded!")
                expand_all = False

                (plant_export, reference_emissions, reference_utility,
                 forecast_emission, forecast_utility, project_emission,
                 project_utility, production, flexibility, storage) = files.values()
        else:
            st.info("No files uploaded yet")
            expand_all = True

    st.divider()

    all_files_ready = all([
        plant_export, reference_emissions, reference_utility, forecast_emission,
        forecast_utility, project_emission, project_utility, production, flexibility, storage,
    ])

    if not all_files_ready:
        with st.expander("Step 1: Upload Reference Files", expanded=expand_all):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("### Plant export")
                plant_export = st.file_uploader("Meta details of plants (plant-export)", type=["csv"], key="plant_export")
                if plant_export:
                    st.success("✓ Plant details loaded")
            with col2:
                st.markdown("### Reference Emissions")
                reference_emissions = st.file_uploader("reference-emission-data", type=["csv"], key="reference_emissions")
                if reference_emissions:
                    st.success("✓ Reference emissions loaded")
            with col3:
                st.markdown("### Reference Utility")
                reference_utility = st.file_uploader("reference-utility-data", type=["csv"], key="reference_utility")
                if reference_utility:
                    st.success("✓ Reference utility loaded")

        with st.expander("Step 2: Upload Forecast Files", expanded=expand_all):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### Emission forecast")
                forecast_emission = st.file_uploader("emission-forecast", type=["csv"], key="forecast_emission")
                if forecast_emission:
                    st.success("✓ Emission forecast loaded")
            with col2:
                st.markdown("### Utility forecast")
                forecast_utility = st.file_uploader("forecast-export_all", type=["csv"], key="forecast_utility")
                if forecast_utility:
                    st.success("✓ Utility forecast loaded")

        with st.expander("Step 3: Upload Project Files", expanded=expand_all):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### Project emissions")
                project_emission = st.file_uploader("projectdata-export_emissions", type=["csv"], key="project_emission")
                if project_emission:
                    st.success("✓ Projects emissions loaded")
            with col2:
                st.markdown("### Project utilities")
                project_utility = st.file_uploader("projectdata-export_utilities", type=["csv"], key="project_utility")
                if project_utility:
                    st.success("✓ Projects utilities loaded")

        with st.expander("Step 4: Upload production, storage, flexibility", expanded=expand_all):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("### Production")
                production = st.file_uploader("electricity_production", type=["csv"], key="production")
                if production:
                    st.success("✓ Production loaded")
            with col2:
                st.markdown("### Storage")
                storage = st.file_uploader("energy_storage", type=["csv"], key="storage")
                if storage:
                    st.success("✓ Storage loaded")
            with col3:
                st.markdown("### Flexibility")
                flexibility = st.file_uploader("flex_options", type=["csv"], key="flexibility")
                if flexibility:
                    st.success("✓ Flexibility loaded")

        st.divider()

    with st.expander("Scenario Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            scenario_amount = st.number_input(label='Number of scenarios', value=5, min_value=0, key='scenario_amount')
            scenario_names = st.text_input(
                label='Scenario names', value='Elektrificatie, Midden, VT, Groen gas, Waterstof',
                help='Input the names separated by a comma', key='scenario_names',
            )
            try:
                scenario_names_list = [n.strip() for n in scenario_names.split(',') if n.strip()]
                if len(scenario_names_list) != scenario_amount:
                    raise Exception(
                        f"Amount of names ({len(scenario_names_list)}) inconsistent with the "
                        f"number of scenarios ({scenario_amount})."
                    )
            except Exception as e:
                st.error(f'[ERR] Error processing scenario names: {e}')

        with col2:
            reference_year = st.number_input(
                label='Reference year', value=2024, key='reference_year',
                min_value=2010, max_value=2100, help='must be between 2010 and 2100',
            )
            scenario_years = st.text_input(
                label='Scenario years', value='2030, 2035, 2040, 2050',
                help='Input the years separated by a comma', key='scenario_years',
            )
            try:
                scenario_years_list = [y.strip() for y in scenario_years.split(',') if y.strip()]
                _ = [int(x) for x in scenario_years_list]
            except Exception as e:
                st.error(f'[ERR] parsing scenario years: {e}')

        st.divider()

    # Keep uploaded DSH files available to other tabs (e.g. sidebar downloads'
    # Generate Master Projects File) without needing them passed in directly.
    st.session_state.dsh_files = {
        "plant_export": plant_export,
        "reference_emissions": reference_emissions,
        "reference_utility": reference_utility,
        "forecast_emission": forecast_emission,
        "forecast_utility": forecast_utility,
        "project_emission": project_emission,
        "project_utility": project_utility,
        "production": production,
        "flexibility": flexibility,
        "storage": storage,
    }

    st.markdown("### Generate plant excels")

    if not all_files_ready:
        st.error('One or more files missing. Check all categories have a file uploaded.')
        return

    st.success('All files uploaded successfully')

    plant_list = []
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
            selected_plants = st.multiselect("Select plants to process", options=plant_list, default=plant_list)
            if selected_plants:
                st.info(f"Processing {len(selected_plants)} selected plants")

    if st.button("Generate plant files", type="primary"):
        st.session_state.generated_files = {}
        st.session_state.dsh_logs = []
        st.markdown("### Generation Logs")
        log_container = st.container(border=True, height=200)

        with st.spinner("Loading data..."):
            try:
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

                data = load_data_streamlit(uploaded_files)

                for plant_id in data["plants"]["Plant identifier"]:
                    plant_name = get_plant_name(data["plants"], plant_id)
                    if plant_name in selected_plants:
                        excel_bytes, logs = process_plant_streamlit(
                            plant_id=plant_id,
                            data=data,
                            logs=st.session_state.dsh_logs,
                            n_scenarios=scenario_amount,
                            scenario_names=scenario_names_list,
                            scenario_years=scenario_years_list,
                            reference_year=reference_year,
                            log_container=log_container,
                        )

                        if excel_bytes:
                            file_name = f"{plant_name}.xlsx"
                            st.session_state.generated_files[file_name] = excel_bytes.getvalue()
                        else:
                            st.write(f"Failed for {plant_name}.")

                st.success(f"Generated {len(st.session_state.generated_files)} files!")

            except Exception as e:
                st.error(f"Error: {e}")
                st.session_state.dsh_logs.append(f"ERROR: {e}")

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
