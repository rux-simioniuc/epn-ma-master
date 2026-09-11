import streamlit as st
import polars as pl
import pandas as pd
import plotly.express as px

from .streamlit_utils import get_mapping_df, read_file_streamlit

from REGIONALIZATION.utils import *
from REGIONALIZATION.constants import PATH_PROVIDERS, PATH_COORDS
from CONNECT_CTM.ctm_push import push_aggregated_by_scenario_year


def render_regionalization_tab():
    if 'all_data_regio' not in st.session_state:
        st.session_state.all_data_regio = pd.DataFrame()
    df_regio = None
    with st.expander('1. Plant coordinates'):

        plant_data_regio = st.file_uploader(
            "Upload plant data (DSH)",
            type=["csv", "xlsx"],
            key="plant_data_regio",
            accept_multiple_files=False
        )
        if plant_data_regio is not None:
            # only (re)parse the upload once; afterwards work off session_state
            if "plant_data_regio_df" not in st.session_state:
                df_regio = read_file_streamlit(plant_data_regio)[['Plant identifier', 'Plant name','Latitude', 'Longitude', 'Address', 'Zip code', 'City', 'All EANs']]
                st.session_state["plant_data_regio_df"] = df_regio
                # st.session_state["plant_data_regio_name"] = plant_data_regio.name

            df_regio = st.session_state["plant_data_regio_df"]

            missing_plants = get_plants_missing_coords(df_regio)
            st.write(f"Missing coordinates: {len(missing_plants)} / {df_regio.height}")

            use_persistent_coords = st.toggle('Override with previously input data', value=True)
            done_generating = False
            if st.button('Fill in and fix coordinates', width='stretch'):
                log_container = st.container(border=True, height=200)
                if use_persistent_coords and file_exists(PATH_COORDS):
                    try:
                        persistent_coords = pl.read_csv(PATH_COORDS)
                        if not persistent_coords.is_empty():
                            df_regio = overwrite_df_with_persistent_vals(df_regio, data_type='coordinates')
                        else:
                            st.warning('Persistent coordinates file is either missing or empty')
                    except Exception as e:
                        st.error(f'[ERR]: {e}')
                with st.spinner("Geocoding..."):
                    df_fixed = fix_coords(df_regio, log_container)
                    df_regio = join_dfs(df_regio, df_fixed, data_type='coordinates')
                    st.session_state["plant_data_regio_df"] = df_regio
                st.success("Done")
                done_generating = True

            if st.button('Save generated coordinates', width='stretch', disabled= done_generating):
                append_to_persistent_file(df_regio, data_type='coordinates')

            with st.expander('View coordinates', expanded=False):
                st.dataframe(df_regio.select(['Plant name', 'Latitude', 'Longitude', 'Address', 'Zip code', 'City']))

            missing_plants_new = get_plants_missing_coords(df_regio)
            if len(missing_plants_new) > 0:

                st.write('### Manually fix missing coordinates')
                all_plants = df_regio["Plant name"].to_list()

                if "extra_manual_plants" not in st.session_state:
                    st.session_state["extra_manual_plants"] = []

                col_a, col_b = st.columns([3, 1])
                with col_a:
                    plant_to_add = st.selectbox(
                        "Add another plant to fix",
                        options=[p for p in all_plants if p not in missing_plants_new and p not in st.session_state["extra_manual_plants"]],
                        key="plant_to_add_select",
                    )
                with col_b:
                    st.write("")  # spacer to align button with selectbox
                    st.write("")
                    if st.button("+ Add", width='stretch'):
                        if plant_to_add:
                            st.session_state["extra_manual_plants"].append(plant_to_add)
                            st.rerun()

                all_rows_plants = missing_plants_new + st.session_state["extra_manual_plants"]

                edited_df = st.data_editor(
                    df_regio.filter(pl.col('Plant name').is_in(all_rows_plants)),
                    column_order=(
                        "Plant name", "Latitude", "Longitude"),
                    disabled=['Plant name'],
                    hide_index=True,
                    width='stretch',
                    key="manual_coords_editor",
                )

                if st.button('Save manual coordinates', width='stretch'):
                    append_to_persistent_file(edited_df, data_type='coordinates')
            else:
                st.write("No missing coordinates.")

            
            st.write('### Plant locations')

            map_df = df_regio.filter(
                pl.col("Latitude").is_not_null() & pl.col("Longitude").is_not_null()
            ).to_pandas()

            if len(map_df) > 0:
                fig = px.scatter_map(
                    map_df,
                    lat="Latitude",
                    lon="Longitude",
                    hover_name="Plant name",
                    hover_data={
                        # "Plant identifier": True,
                        "Address": True,
                        "Zip code": True,
                        "City": True,
                        "Latitude": ":.5f",
                        "Longitude": ":.5f",
                    },
                    zoom=6.25,
                    height=600,
                    title='Plant locations',
                )
                fig.update_traces(marker=dict(size=9, opacity=0.8, color="#3e7aea"))
                fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0},
                                map=dict(
                                    style='carto-positron',
                                    bearing=0,
                                    center=dict(
                                        lat=52.5,
                                        lon=5),
            ))
                st.plotly_chart(fig, width='stretch')
            else:
                st.write("No coordinates to display yet.")

    with st.expander("2. Check providers", expanded=False):
        if df_regio is  None:
            st.warning('Upload the DSH plant data file.')
        else:
            try:
                df_providers = add_grid_provider_types(df_regio).drop(['All EANs'])
                filter_missing = st.toggle('Show only plants with missing provider')

                if filter_missing:
                    df_providers_show = df_providers.filter(pl.col('provider_electricity').is_null() | pl.col('provider_gas').is_null())
                else:
                    df_providers_show = df_providers

                df_providers_edited = st.data_editor(df_providers_show, 
                                                     column_order=('Plant name', 'provider_electricity', 'provider_gas'),
                                                     disabled=['Plant name'])
                if st.button('Save providers'):
                    df_providers_edited.select(['Plant identifier', 'provider_electricity', 'provider_gas']).write_csv(PATH_PROVIDERS)

            except Exception as e:
                st.error(e)

    with st.expander("3. Map to buurten", expanded=False):
        buurt_mapping_dir = 'src/REGIONALIZATION/ref_data/buurt_mapping/'
        avl_files = get_available_mapping_versions()
        buurt_file_gpkg = None
        df_mapped = None
    
        buurt_mapping_version = st.selectbox(label='Select buurt mapping version',options= avl_files + ['Use other mapping'])
        if 'other' in buurt_mapping_version:
            col1, col2 = st.columns([3, 1])
            with col1:  
                manual_path = st.text_input('Paste local path to mapping file (files are too big to drag and drop)', placeholder='path/to/file.gpkg')   
            with col2:
                st.text("")
                st.text("")
                if st.button('Load file'):
                    buurt_file_gpkg = manual_path
        else:
            buurt_file_gpkg = buurt_mapping_dir + buurt_mapping_version

        if df_regio is not None:
            try:
                if buurt_file_gpkg is not None:
                    df_mapped = pd.DataFrame(add_buurtcode_to_plantcoords(df_regio, buurt_file_gpkg=buurt_file_gpkg))
                    st.dataframe(df_mapped[['Plant name', 'buurtcode', 'buurtnaam']])
                else:
                    st.warning('Could not complete the buurt mapping')
            except Exception as e:
                st.error(e)

    if df_mapped is not None and df_providers_edited is not None:
        with st.expander('Final mapping', expanded=True):
            mapped2 = pl.from_pandas(df_mapped[['Plant identifier', 'buurtcode', 'buurtnaam']])
            res = get_final_plant_mapping(df_providers_edited, mapped2)
            del mapped2
            st.dataframe(res)


    with st.expander("4. Upload plant files with scenario data"):

        # Plant files: reuse from CTM/ETM Workflow tab if already uploaded there
        if st.session_state.plant_files is not None:
            plant_files_regio = st.session_state.plant_files
            st.info(f'Using {len(plant_files_regio)} plant file(s) already uploaded in "CTM/ETM Workflow" tab')
        else:
            st.markdown("### Plant Workbooks")
            plant_files_regio = st.file_uploader(
                "Upload plant Excel files",
                type=["xlsx"],
                accept_multiple_files=True,
                key="plant_files_regio",
            )
            if plant_files_regio:
                st.success(f"✓ {len(plant_files_regio)} files uploaded")

        # Mapping: reuse from CTM/ETM Workflow tab if already uploaded there --
        # moved out from under the plant_files check, since it was previously
        # nested inside it and got skipped whenever plant_files was reused
        if st.session_state.mapping is not None:
            st.info('Mapping file already uploaded in "CTM/ETM Workflow" tab')
        else:
            st.markdown("### Mapping File")
            mapping_file_regio = st.file_uploader(
                "Upload DSH to CTM mapping file",
                type=["csv", "xlsx"],
                key="mapping_file_regio",
                accept_multiple_files=False,
            )
            if mapping_file_regio:
                try:
                    st.session_state.mapping = get_mapping_df(mapping_file_regio)
                    st.success('Mapping uploaded and processed successfully')
                except Exception as e:
                    st.error(f"[ERR] {e}")

        if plant_files_regio:
            if st.button(
                'Aggregate the data',
                width='stretch',
                key='get_only_data_regio',
                disabled=(st.session_state.mapping is None or st.session_state.mapping.is_empty()),
            ):
                only_scenario_data = push_aggregated_by_scenario_year(
                    plants_workbook_dir=plant_files_regio,
                    mapping_df=st.session_state.mapping,
                    only_load_scenario_data=True,
                    reference_year='0',
                )
                if 'all_data_regio' not in st.session_state:
                    st.session_state.all_data_regio = None
                st.session_state.all_data_regio = only_scenario_data['data']

                plant_dfs = [
                    v['df'].with_columns(pl.col(pl.Int64, pl.Float64, pl.Null).cast(pl.Float64))
                    for v in only_scenario_data['data'].values()
                    if not v['df'].is_empty()
                ]

                if plant_dfs:
                    pass
                else:
                    st.warning("No plant data available to aggregate.")
        # st.write(st.session_state.all_data_regio['48fb5231-1d91-4906-97e7-8c44332b0637']['mapping_row'])