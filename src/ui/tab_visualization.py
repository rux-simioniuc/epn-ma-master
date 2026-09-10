"""
Tab 3: Visualization — per-plant, per-cluster, per-sector emission/utility
trends across scenarios. Reads st.session_state.all_data, populated by
Tab 2's "Aggregate the data" button.
"""

import streamlit as st
import polars as pl
import plotly.express as px
from collections import defaultdict
from CONNECT_CTM.utils.constants import EMISSION_COLS_ORDER, UTILITY_COLS_ORDER


def render_visualization_tab():
    if st.session_state.get("all_data") is None or len(st.session_state.all_data) == 0:
        st.info('Upload plant files and mapping to see visualizations')
        return

    scenario_data = {}
    for _, v in st.session_state.all_data.items():
        scenario_data[v['name']] = v['df']

    with st.expander('Individual plant viz'):
        current_plant = st.selectbox(label='Select individual plant', options=scenario_data.keys())
        current_column = st.selectbox(
            label='Select emission / utility', options=EMISSION_COLS_ORDER + UTILITY_COLS_ORDER,
        )
        fig = px.line(scenario_data[current_plant], x='Year', y=current_column, color='Scenario', line_dash='Flow type')
        st.plotly_chart(fig)

    sector_dfs = defaultdict(list)
    cluster_dfs = defaultdict(list)

    for plant in st.session_state.all_data.values():
        sector = plant["mapping_row"]["Sector"]
        cluster = plant["mapping_row"]["Cluster"]
        sector_dfs[sector].append(plant["df"])
        cluster_dfs[cluster].append(plant["df"])

    sector_dfs['all_chemicals'] = (
        sector_dfs.get('organic_base_chemicals', [])
        + sector_dfs.get('other_chemicals', [])
        + sector_dfs.get('inorganic_base_chemicals', [])
    )

    # cast all numeric/null columns to float; otherwise concat yields errors
    sector_df = {
        sector: pl.concat(
            [df.with_columns(pl.col(pl.Int64, pl.Float64, pl.Null).cast(pl.Float64)) for df in dfs],
            how="vertical",
        )
        for sector, dfs in sector_dfs.items()
        if len(dfs) > 0  # guards the empty-list case pl.concat can't handle
    }

    cluster_df = {
        cluster: pl.concat(
            [df.with_columns(pl.col(pl.Int64, pl.Float64, pl.Null).cast(pl.Float64)) for df in dfs],
            how="vertical",
        )
        for cluster, dfs in cluster_dfs.items()
        if len(dfs) > 0
    }

    group_by_cols = ["Scenario", "Year", "Flow type"]

    with st.expander('Cluster-level aggregation'):
        cluster_df = {
            cluster: df.group_by(group_by_cols).agg(
                pl.col([c for c in df.columns if c not in group_by_cols and df[c].dtype.is_numeric()]).sum()
            ).sort('Year', 'Flow type')
            for cluster, df in cluster_df.items()
        }

        current_cluster = st.selectbox(label='Select cluster', options=sorted(cluster_dfs.keys()))
        current_column_cluster = st.selectbox(
            label='Select emission / utility', options=EMISSION_COLS_ORDER + UTILITY_COLS_ORDER, key='column_cluster',
        )

        fig2 = px.line(cluster_df[current_cluster], x="Year", y=current_column_cluster, color="Scenario", line_dash="Flow type")
        st.plotly_chart(fig2)

        current_scenario = st.selectbox(
            label='Select scenario',
            options=sorted(cluster_df[current_cluster].select(pl.col('Scenario')).unique().to_series().to_list()),
        )

        plot_df = cluster_df[current_cluster].filter(pl.col("Scenario") == current_scenario).with_columns(
            pl.when(pl.col("Flow type") == "production")
            .then(-pl.col(EMISSION_COLS_ORDER + UTILITY_COLS_ORDER))
            .otherwise(pl.col(EMISSION_COLS_ORDER + UTILITY_COLS_ORDER))
        )

        fig = px.bar(
            plot_df, x="Year", y=EMISSION_COLS_ORDER,
            title=f"Emissions for cluster {current_cluster}, scenario {current_scenario}", pattern_shape='Flow type',
        )
        st.plotly_chart(fig)

        fig = px.bar(
            plot_df, x="Year", y=UTILITY_COLS_ORDER,
            title=f"Utilities for cluster {current_cluster}, scenario {current_scenario}", pattern_shape='Flow type',
        )
        st.plotly_chart(fig)

    with st.expander('Sector-level aggregation'):
        sector_df = {
            sector: df.group_by(group_by_cols).agg(
                pl.col([c for c in df.columns if c not in group_by_cols and df[c].dtype.is_numeric()]).sum()
            ).sort(['Year', 'Flow type'])
            for sector, df in sector_df.items()
        }

        current_sector = st.selectbox(label='Select sector', options=sorted(sector_dfs.keys()))
        current_column_sector = st.selectbox(
            label='Select emission / utility', options=EMISSION_COLS_ORDER + UTILITY_COLS_ORDER, key='column_sector',
        )

        fig3 = px.line(sector_df[current_sector], x="Year", y=current_column_sector, color="Scenario", line_dash="Flow type")
        st.plotly_chart(fig3)

        current_scenario = st.selectbox(
            label='Select scenario',
            options=sorted(cluster_df[current_cluster].select(pl.col('Scenario')).unique().to_series().to_list()),
            key='scenario_sector',
        )

        plot_df = sector_df[current_sector].filter(pl.col("Scenario") == current_scenario).with_columns(
            pl.when(pl.col("Flow type") == "production")
            .then(-pl.col(EMISSION_COLS_ORDER + UTILITY_COLS_ORDER))
            .otherwise(pl.col(EMISSION_COLS_ORDER + UTILITY_COLS_ORDER))
        )

        fig = px.bar(
            plot_df, x="Year", y=EMISSION_COLS_ORDER,
            title=f"Emissions for cluster {current_sector}, scenario {current_scenario}", pattern_shape='Flow type',
        )
        st.plotly_chart(fig)

        fig = px.bar(
            plot_df, x="Year", y=UTILITY_COLS_ORDER,
            title=f"Utilities for cluster {current_sector}, scenario {current_scenario}", pattern_shape='Flow type',
        )
        st.plotly_chart(fig)
