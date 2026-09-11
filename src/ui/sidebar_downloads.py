"""
Sidebar: "Extra options" — master file downloads. Reads plant_files and DSH
files from st.session_state, set by tab_ctm_workflow.py and tab_dsh_input.py
respectively, so this doesn't need them passed in directly.
"""

import streamlit as st
import polars as pl
import io
import gc

from ui.streamlit_utils import read_csv_streamlit
from CONNECT_CTM.utils.utils import (get_master_emissions_utilities, 
                               get_master_projects, 
                               get_units_per_plant, 
                               create_units_excel, 
                               )


def render_sidebar_downloads():
    plant_files = st.session_state.get("plant_files")
    dsh_files = st.session_state.get("dsh_files", {})
    reference_emissions = dsh_files.get("reference_emissions")
    reference_utility = dsh_files.get("reference_utility")
    project_emission = dsh_files.get("project_emission")
    project_utility = dsh_files.get("project_utility")

    mapping = st.session_state.get("mapping")
    mapping_ready = mapping is not None and not mapping.is_empty()

    disable_master = not plant_files or not mapping_ready
    disable_master_projects = not all([
        reference_emissions, reference_utility, project_emission, project_utility,
    ]) or not mapping_ready
    disable_units = not plant_files

    st.sidebar.markdown("### Extra options")

    with st.sidebar.expander("Download helper files", expanded=False):

        if st.button('Generate Master Energy Balance File', use_container_width=True, disabled=disable_master):
            try:
                master = None
                log_area = st.empty()

                for i, uploaded_file in enumerate(plant_files):
                    log_area.text(f"Processing {i + 1}/{len(plant_files)}: {uploaded_file.name}")

                    file_bytes = uploaded_file.read()
                    chunk = get_master_emissions_utilities(
                        mapping_df=st.session_state.mapping,
                        excel_files_dict={uploaded_file.name: file_bytes},
                        reference_year=st.session_state.ref_year,
                    )

                    if chunk is not None and not chunk.is_empty():
                        master = chunk if master is None else pl.concat([master, chunk], how="vertical_relaxed")

                    del file_bytes, chunk
                    gc.collect()

                if master is not None:
                    buffer = io.BytesIO()
                    master.write_excel(buffer)
                    buffer.seek(0)

                    st.download_button(
                        label="Download master_emission_utilities.xlsx", data=buffer.getvalue(),
                        file_name="master_emission_utilities.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                    del master, buffer
                    gc.collect()
                    log_area.text("✓ Complete!")

            except Exception as e:
                st.error(f'[ERROR]: {e}')

        if disable_master:
            st.warning('[Plant Workbooks](#plant-workbooks) and [mapping](#mapping-file) in CTM/ETM workflow tab', title='Upload files')

        if st.button('Generate Master Projects File', use_container_width=True, disabled=disable_master_projects):
            try:
                master_projects = get_master_projects(
                    mapping_df=st.session_state.mapping,
                    reference_emission_df=read_csv_streamlit(reference_emissions),
                    reference_utility_df=read_csv_streamlit(reference_utility),
                    projects_emission_df=read_csv_streamlit(project_emission),
                    projects_utility_df=read_csv_streamlit(project_utility),
                    REF_YEAR=st.session_state.ref_year,
                )
                if master_projects is not None:
                    buffer = io.BytesIO()
                    master_projects.write_excel(buffer)
                    buffer.seek(0)

                    st.download_button(
                        label="Download master_project.xlsx", data=buffer.getvalue(),
                        file_name="master_project.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            except Exception as e:
                st.error(f'[ERROR]: {e}')

        if disable_master_projects:
            st.warning(
                '[DSH files - reference + projects](#upload-dsh-files) in DSH Input tab and '
                '[mapping](#mapping-file) in CTM/ETM workflow tab',
                title='Upload files',
            )

        if st.button('Generate Power Units Overview', use_container_width=True, disabled=disable_units):
            try:
                master_units = None
                for uploaded_file in plant_files:
                    chunk = get_units_per_plant(plant_file_path=uploaded_file, plant_name=uploaded_file.name)

                    if chunk is not None and not chunk.is_empty():
                        master_units = chunk if master_units is None else pl.concat([master_units, chunk], how="vertical_relaxed")

                    del chunk
                    gc.collect()

                if master_units is not None:
                    units_excel = create_units_excel(master_units)
                    st.download_button(
                        label="Download power_units_overview.xlsx", data=units_excel,
                        file_name="power_units_overview.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

            except Exception as e:
                st.error(f'[ERROR]: {e}')

        if disable_units:
            st.warning('[Plant Workbooks](#plant-workbooks) in CTM/ETM workflow tab', title='Upload files')
