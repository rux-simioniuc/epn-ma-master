import streamlit as st
import polars as pl
import plotly.express as px
import plotly.graph_objects as go

from CONNECT_CTM.utils.constants import (
    EMISSION_COLS_ORDER,
    UTILITY_COLS_ORDER,
)


METRIC_COLS = EMISSION_COLS_ORDER + UTILITY_COLS_ORDER
GROUP_BY_COLS = ["Scenario", "Year", "Flow type"]


def render_stacked_with_total(
    df: pl.DataFrame,
    plant_col: str,
    x_col: str,
    y_col: str,
    title: str,
):
    fig = px.bar(
        df,
        x=x_col,
        y=y_col,
        color=plant_col,
        barmode="stack",
        title=title,
    )

    totals = (
        df.group_by(x_col)
        .agg(pl.col(y_col).sum().alias("Total"))
        .sort(x_col)
    )

    fig.add_trace(
        go.Scatter(
            x=totals[x_col].to_list(),
            y=totals["Total"].to_list(),
            mode="lines+markers+text",
            text=[f"{v:,.0f}" for v in totals["Total"].to_list()],
            textposition="top center",
            name="Total",
            line=dict(color="black", width=2, dash="dot"),
        )
    )

    return fig


def _all_data_cache_key(all_data: dict) -> str:
    """Cheap fingerprint for all_data -- avoids hashing nested DataFrames
    every rerun, which is what @st.cache_data would otherwise do on the
    dict itself."""
    return ",".join(sorted(str(k) for k in all_data.keys()))


@st.cache_data(show_spinner=False)
def prepare_all_data(_all_data: dict, cache_key: str) -> pl.DataFrame:
    """
    Combine all plants once and add plant/sector/cluster metadata.
    _all_data is underscore-prefixed so Streamlit skips hashing it directly;
    cache_key (cheap, built from plant IDs) is the real cache identity.
    """
    dfs = []

    for plant in _all_data.values():
        dfs.append(
            plant["df"].with_columns(
                pl.lit(plant["name"]).alias("Plant name"),
                pl.lit(plant["mapping_row"]["Sector"]).alias("Sector"),
                pl.lit(plant["mapping_row"]["Cluster"]).alias("Cluster"),
            )
        )

    if not dfs:
        return pl.DataFrame()

    combined = pl.concat(dfs, how="vertical_relaxed")

    numeric_cols = [
        col
        for col in METRIC_COLS
        if col in combined.columns
        and combined[col].dtype.is_numeric()
    ]

    if numeric_cols:
        combined = combined.with_columns(
            pl.col(numeric_cols).cast(pl.Float64)
        )

    return combined.fill_null(0)


def filter_on_scenarios(combined_df: pl.DataFrame, selected_scenarios: list[str]) -> pl.DataFrame:
    """
    Deliberately NOT cached: this is a cheap boolean-mask filter, and caching
    it would mean hashing the full combined_df on every call anyway -- which
    happens on every multiselect change, defeating the point.
    """
    return combined_df.filter(pl.col('Scenario').is_in(selected_scenarios))


@st.cache_data(show_spinner=False)
def aggregate_data(_df: pl.DataFrame, group_col: str, cache_key: str) -> pl.DataFrame:
    """
    Aggregate either by Sector or Cluster. _df underscored for the same
    reason as prepare_all_data; cache_key should encode both which plants
    are loaded AND which scenarios are currently selected, so this only
    recomputes when either actually changes (see call sites below).
    """
    return (
        _df.group_by([group_col] + GROUP_BY_COLS)
        .agg(pl.col(METRIC_COLS).sum())
        .sort([group_col, "Year", "Flow type"])
    )


def render_plant_breakdown(
    df: pl.DataFrame,
    metric: str,
    scenario: str,
    key_prefix: str,
    title_suffix: str,
):
    filtered = df.filter(
        (pl.col("Scenario") == scenario)
        & pl.col(metric).is_not_null()
    )

    if filtered.is_empty():
        st.info("No data available for this scenario.")
        return

    flow_types = (
        filtered
        .get_column("Flow type")
        .unique()
        .sort()
        .to_list()
    )

    if not flow_types:
        st.info("No data available for this scenario.")
        return

    default_idx = flow_types.index("demand") if "demand" in flow_types else 0

    current_flow_type = st.selectbox(
        "Select flow type",
        options=flow_types,
        index=default_idx,
        key=f"{key_prefix}_flow_type",
    )

    plot_df = filtered.filter(
        pl.col("Flow type") == current_flow_type
    )

    if plot_df.is_empty():
        st.info("No data for this scenario/flow type combination.")
        return

    fig = render_stacked_with_total(
        plot_df,
        plant_col="Plant name",
        x_col="Year",
        y_col=metric,
        title=(
            f"{metric} by plant ({current_flow_type}) — "
            f"{title_suffix}, {scenario}"
        ),
    )

    st.plotly_chart(fig, key=f"{key_prefix}_chart")


def render_visualization_tab():

    all_data = st.session_state.get("all_data")

    if not all_data:
        st.info("Upload plant files and mapping to see visualizations")
        return

    # ---------------------------------------------------------
    # Prepare combined dataframe once (cached on plant identity only)
    # ---------------------------------------------------------
    all_data_key = _all_data_cache_key(all_data)
    combined_df_init = prepare_all_data(all_data, all_data_key)

    if combined_df_init.is_empty():
        st.info("No data available.")
        return

    # ---------------------------------------------------------
    # Scenario filter -- applied AFTER the cached combine step, so picking
    # scenarios never re-triggers the expensive concat/cast in prepare_all_data
    # ---------------------------------------------------------
    all_avl_scenarios = (
        combined_df_init.select('Scenario').unique().to_series().sort().to_list()
    )
    selected_scenarios = st.multiselect(
        label='Select scenarios to display',
        options=all_avl_scenarios,
        default=all_avl_scenarios,
    )

    if not selected_scenarios:
        st.info("Select at least one scenario to display.")
        return

    combined_df = filter_on_scenarios(combined_df_init, selected_scenarios)

    # Encodes both "which plants" and "which scenarios" -- aggregate_data
    # only recomputes when either of those actually changes, not on every
    # unrelated widget interaction elsewhere on the page.
    scenario_key = f"{all_data_key}|{','.join(sorted(selected_scenarios))}"

    # ---------------------------------------------------------
    # Individual plant visualization
    # ---------------------------------------------------------
    with st.expander("Individual plant viz"):

        plants = (
            combined_df
            .get_column("Plant name")
            .unique()
            .sort()
            .to_list()
        )

        current_plant = st.selectbox(
            "Select individual plant",
            options=plants,
        )

        current_column = st.selectbox(
            "Select emission / utility",
            options=METRIC_COLS,
        )

        plant_df = combined_df.filter(
            pl.col("Plant name") == current_plant
        )

        fig = px.line(
            plant_df,
            x="Year",
            y=current_column,
            color="Scenario",
            line_dash="Flow type",
        )

        st.plotly_chart(fig)

    # ---------------------------------------------------------
    # Cluster-level aggregation
    # ---------------------------------------------------------
    with st.expander("Cluster-level aggregation"):

        cluster_df = aggregate_data(combined_df, "Cluster", scenario_key)

        clusters = (
            cluster_df
            .get_column("Cluster")
            .unique()
            .sort()
            .to_list()
        )

        current_cluster = st.selectbox(
            "Select cluster",
            options=clusters,
        )

        cluster_data = cluster_df.filter(
            pl.col("Cluster") == current_cluster
        )

        current_column_cluster = st.selectbox(
            "Select emission / utility",
            options=METRIC_COLS,
            key="column_cluster",
        )

        fig = px.line(
            cluster_data,
            x="Year",
            y=current_column_cluster,
            color="Scenario",
            line_dash="Flow type",
        )

        st.plotly_chart(fig)

        scenarios = (
            cluster_data
            .get_column("Scenario")
            .unique()
            .sort()
            .to_list()
        )

        current_scenario = st.selectbox(
            "Select scenario",
            options=scenarios,
        )

        plot_df = (
            cluster_data
            .filter(pl.col("Scenario") == current_scenario)
            .with_columns(
                pl.when(pl.col("Flow type") == "production")
                .then(-pl.col(METRIC_COLS))
                .otherwise(pl.col(METRIC_COLS))
            )
        )

        fig = px.bar(
            plot_df,
            x="Year",
            y=EMISSION_COLS_ORDER,
            title=(
                f"Emissions for cluster {current_cluster}, "
                f"scenario {current_scenario}"
            ),
            pattern_shape="Flow type",
        )

        st.plotly_chart(fig)

        fig = px.bar(
            plot_df,
            x="Year",
            y=UTILITY_COLS_ORDER,
            title=(
                f"Utilities for cluster {current_cluster}, "
                f"scenario {current_scenario}"
            ),
            pattern_shape="Flow type",
        )

        st.plotly_chart(fig)

        st.markdown("#### Plant breakdown")

        breakdown_df = combined_df.filter(
            pl.col("Cluster") == current_cluster
        )

        render_plant_breakdown(
            breakdown_df,
            current_column_cluster,
            current_scenario,
            key_prefix="cluster_breakdown",
            title_suffix=f"cluster {current_cluster}",
        )

    # ---------------------------------------------------------
    # Sector-level aggregation
    # ---------------------------------------------------------
    with st.expander("Sector-level aggregation"):

        sector_df = aggregate_data(combined_df, "Sector", scenario_key)

        sectors = (
            sector_df
            .get_column("Sector")
            .unique()
            .sort()
            .to_list()
        )

        # Add combined chemical sector if needed
        chemical_sectors = {
            "organic_base_chemicals",
            "other_chemicals",
            "inorganic_base_chemicals",
        }

        if chemical_sectors.issubset(set(sectors)):
            sectors.append("all_chemicals")

        current_sector = st.selectbox(
            "Select sector",
            options=sectors,
        )

        if current_sector == "all_chemicals":
            sector_data = sector_df.filter(
                pl.col("Sector").is_in(chemical_sectors)
            ).group_by(GROUP_BY_COLS).agg(
                pl.col(METRIC_COLS).sum()
            ).sort(["Year", "Flow type"])
        else:
            sector_data = sector_df.filter(
                pl.col("Sector") == current_sector
            )

        current_column_sector = st.selectbox(
            "Select emission / utility",
            options=METRIC_COLS,
            key="column_sector",
        )

        fig = px.line(
            sector_data,
            x="Year",
            y=current_column_sector,
            color="Scenario",
            line_dash="Flow type",
        )

        st.plotly_chart(fig)

        scenarios = (
            sector_data
            .get_column("Scenario")
            .unique()
            .sort()
            .to_list()
        )

        current_scenario_sector = st.selectbox(
            "Select scenario",
            options=scenarios,
            key="scenario_sector",
        )

        plot_df = (
            sector_data
            .filter(pl.col("Scenario") == current_scenario_sector)
            .with_columns(
                pl.when(pl.col("Flow type") == "production")
                .then(-pl.col(METRIC_COLS))
                .otherwise(pl.col(METRIC_COLS))
            )
        )

        fig = px.bar(
            plot_df,
            x="Year",
            y=EMISSION_COLS_ORDER,
            title=(
                f"Emissions for sector {current_sector}, "
                f"scenario {current_scenario_sector}"
            ),
            pattern_shape="Flow type",
        )

        st.plotly_chart(fig)

        fig = px.bar(
            plot_df,
            x="Year",
            y=UTILITY_COLS_ORDER,
            title=(
                f"Utilities for sector {current_sector}, "
                f"scenario {current_scenario_sector}"
            ),
            pattern_shape="Flow type",
        )

        st.plotly_chart(fig)

        st.markdown("#### Plant breakdown")

        breakdown_df = combined_df

        if current_sector == "all_chemicals":
            breakdown_df = breakdown_df.filter(
                pl.col("Sector").is_in(chemical_sectors)
            )
        else:
            breakdown_df = breakdown_df.filter(
                pl.col("Sector") == current_sector
            )

        render_plant_breakdown(
            breakdown_df,
            current_column_sector,
            current_scenario_sector,
            key_prefix="sector_breakdown",
            title_suffix=f"sector {current_sector}",
        )