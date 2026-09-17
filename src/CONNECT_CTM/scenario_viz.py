"""
Visualization helpers - extract scenario data for charts/dashboards.
"""

import polars as pl
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════
# Extract data for visualizations
# ═══════════════════════════════════════════════════════════════════════

def get_plant_summary(
    scenario_data: pl.DataFrame,
    plant_name: str,
) -> pl.DataFrame:
    """
    Get all data for a single plant across all scenarios/years.
    
    Usage: Feed to Streamlit dataframe or chart
    """
    return scenario_data.filter(
        pl.col("Plant name") == plant_name
    ).sort(["Scenario", "Year"])


def get_scenario_summary(
    scenario_data: pl.DataFrame,
    scenario: str,
) -> pl.DataFrame:
    """Get all data for a single scenario across all plants/years."""
    return scenario_data.filter(
        pl.col("Scenario") == scenario
    ).sort(["Plant name", "Year"])


def get_year_comparison(
    scenario_data: pl.DataFrame,
    plant_name: str,
    metric: str,  # e.g., "CO2" or "Electricity"
) -> pl.DataFrame:
    """
    Get metric values across scenarios and years for one plant.
    
    Perfect for line chart: Year on X-axis, Scenario as series
    """
    return scenario_data.filter(
        pl.col("Plant name") == plant_name
    ).select([
        "Plant name",
        "Scenario",
        "Year",
        "Flow type",
        metric,
    ]).sort(["Year", "Scenario"])


def get_metric_by_flow_type(
    scenario_data: pl.DataFrame,
    plant_name: str,
    scenario: str,
    metric: str,
) -> pl.DataFrame:
    """
    Get metric across flow types (demand, supply, production, etc).
    
    Perfect for bar chart comparing flow types
    """
    return scenario_data.filter(
        (pl.col("Plant name") == plant_name) &
        (pl.col("Scenario") == scenario)
    ).select([
        "Plant name",
        "Year",
        "Flow type",
        metric,
    ]).sort(["Year", "Flow type"])


def get_sector_metrics(
    scenario_data: pl.DataFrame,
    metric: str,
    scenario: Optional[str] = None,
    year: Optional[str] = None,
) -> pl.DataFrame:
    """
    Aggregate metric by sector (across all plants).
    
    Perfect for sector comparison chart
    """
    df = scenario_data.select([
        "Sector",
        "Scenario",
        "Year",
        metric,
    ])
    
    if scenario:
        df = df.filter(pl.col("Scenario") == scenario)
    if year:
        df = df.filter(pl.col("Year") == str(year))
    
    # Sum by sector/scenario/year
    return df.group_by(
        ["Sector", "Scenario", "Year"]
    ).agg(
        pl.col(metric).sum().alias(f"{metric}_total")
    ).sort(["Sector", "Scenario", "Year"])


def get_cluster_metrics(
    scenario_data: pl.DataFrame,
    metric: str,
    scenario: Optional[str] = None,
) -> pl.DataFrame:
    """Aggregate metric by cluster."""
    df = scenario_data.select([
        "Cluster",
        "Scenario",
        "Year",
        metric,
    ])
    
    if scenario:
        df = df.filter(pl.col("Scenario") == scenario)
    
    return df.group_by(
        ["Cluster", "Scenario", "Year"]
    ).agg(
        pl.col(metric).sum().alias(f"{metric}_total")
    ).sort(["Cluster", "Scenario", "Year"])


def get_all_metrics_one_plant(
    scenario_data: pl.DataFrame,
    plant_name: str,
) -> Dict[str, float]:
    """
    Get all metric values for one plant (latest scenario/year).
    
    Perfect for KPI cards
    """
    data = scenario_data.filter(
        pl.col("Plant name") == plant_name
    ).sort(["Scenario", "Year"], descending=[False, True])
    
    if data.is_empty():
        return {}
    
    # Get latest row
    latest = data.row(0, named=True)
    
    # Extract all numeric columns
    metrics = {}
    for col in data.columns:
        val = latest.get(col)
        if isinstance(val, (int, float)) and col not in ["Year"]:
            metrics[col] = val
    
    return metrics


def get_scenario_timeline(
    scenario_data: pl.DataFrame,
    plant_name: str,
    metric: str,
) -> pl.DataFrame:
    """
    Get metric timeline for one plant across all scenarios.
    
    Perfect for area chart or line chart showing transition paths
    """
    return scenario_data.filter(
        pl.col("Plant name") == plant_name
    ).select([
        "Scenario",
        "Year",
        metric,
    ]).sort(["Scenario", "Year"])


def compare_scenarios(
    scenario_data: pl.DataFrame,
    scenarios: List[str],
    plant_name: str,
    metric: str,
) -> pl.DataFrame:
    """
    Compare metric across selected scenarios for one plant.
    
    Perfect for side-by-side scenario comparison
    """
    return scenario_data.filter(
        (pl.col("Plant name") == plant_name) &
        (pl.col("Scenario").is_in(scenarios))
    ).select([
        "Scenario",
        "Year",
        metric,
    ]).pivot(
        index="Year",
        columns="Scenario",
        values=metric,
    ).sort("Year")


# ═══════════════════════════════════════════════════════════════════════
# Utilities for chart preparation
# ═══════════════════════════════════════════════════════════════════════

def get_available_plants(scenario_data: pl.DataFrame) -> List[str]:
    """Get list of all unique plants."""
    return scenario_data.select("Plant name").unique().sort("Plant name").to_series().to_list()


def get_available_scenarios(scenario_data: pl.DataFrame) -> List[str]:
    """Get list of all unique scenarios."""
    return scenario_data.select("Scenario").unique().sort("Scenario").to_series().to_list()


def get_available_years(scenario_data: pl.DataFrame) -> List[str]:
    """Get list of all unique years."""
    return scenario_data.select("Year").unique().sort("Year").to_series().to_list()


def get_available_metrics(scenario_data: pl.DataFrame) -> List[str]:
    """Get list of all numeric columns (metrics)."""
    numeric_cols = []
    for col in scenario_data.columns:
        if scenario_data[col].dtype in [pl.Float64, pl.Int64]:
            numeric_cols.append(col)
    return sorted(numeric_cols)


def get_sectors(scenario_data: pl.DataFrame) -> List[str]:
    """Get list of all unique sectors."""
    return scenario_data.select("Sector").unique().sort("Sector").to_series().to_list()


def get_clusters(scenario_data: pl.DataFrame) -> List[str]:
    """Get list of all unique clusters."""
    return scenario_data.select("Cluster").unique().sort("Cluster").to_series().to_list()