"""
CTM Key Builders - single source of truth for every CTM input key.

Peak-electricity ("LDSH") keys were removed: CTM no longer accepts
peak-electricity as an input, so those builders and their callers are gone.
"""

from .utils.ctm_constants import CTM_ENERGY_COLUMN_MAP, CTM_EMISSION_COLUMN_MAP


# ═══════════════════════════════════════════════════════════════════════
# Regular Site Keys (full hierarchy: sector/cluster/site)
# ═══════════════════════════════════════════════════════════════════════

def build_site_enabled_key(sector: str, cluster: str, site: str) -> str:
    """sector&&cluster&&site&&enabled"""
    return f"{sector}&&{cluster}&&{site}&&enabled"


def build_site_transformation_key(sector: str, cluster: str, site: str) -> str:
    """sector&&cluster&&site&&transformation"""
    return f"{sector}&&{cluster}&&{site}&&transformation"


def build_site_data_key(sector: str, cluster: str, site: str, column: str) -> str:
    """sector&&cluster&&site&&column"""
    return f"{sector}&&{cluster}&&{site}&&{column}"


# ═══════════════════════════════════════════════════════════════════════
# Bottom-Up Site Keys (flat hierarchy: site only)
# ═══════════════════════════════════════════════════════════════════════

def build_bottom_up_enabled_key(site: str) -> str:
    """site&&enabled"""
    return f"{site}&&enabled"


def build_bottom_up_transformation_key(site: str) -> str:
    """site&&transformation"""
    return f"{site}&&transformation"


def build_bottom_up_data_key(site: str, column: str) -> str:
    """site&&column"""
    return f"{site}&&{column}"


# ═══════════════════════════════════════════════════════════════════════
# Custom Site Keys (##new_cc_siteN## format)
# ═══════════════════════════════════════════════════════════════════════

def build_custom_site_enabled_key(site_id: str) -> str:
    return f"{site_id}&&enabled"


def build_custom_site_sector_key(site_id: str) -> str:
    return f"{site_id}&&sector"


def build_custom_site_cluster_key(site_id: str) -> str:
    return f"{site_id}&&cluster"


def build_custom_site_latitude_key(site_id: str) -> str:
    return f"{site_id}&&latitude"


def build_custom_site_longitude_key(site_id: str) -> str:
    return f"{site_id}&&longitude"


def build_custom_site_data_key(site_id: str, column: str) -> str:
    return f"{site_id}&&{column}"


# ═══════════════════════════════════════════════════════════════════════
# Cluster / Sector Level Keys
# ═══════════════════════════════════════════════════════════════════════

def build_cluster_enabled_key(sector: str, cluster: str) -> str:
    return f"{sector}&&{cluster}&&cluster&&enabled"


def build_cluster_data_key(sector: str, cluster: str, column: str) -> str:
    return f"{sector}&&{cluster}&&cluster&&{column}"


def build_sector_enabled_key(sector: str) -> str:
    return f"{sector}&&sector&&enabled"


def build_sector_data_key(sector: str, column: str) -> str:
    return f"{sector}&&sector&&{column}"


# ═══════════════════════════════════════════════════════════════════════
# Valid-key-set helpers (for validating a built input dict against the
# schema for a given site). Moved here from ctm_constants.py since they
# build the same '&&' keys this module owns — previously they duplicated
# the key format by hand.
# ═══════════════════════════════════════════════════════════════════════

def get_valid_keys_for_site(sector: str, cluster: str, site: str) -> set:
    """All valid CTM input keys for a regular (sector/cluster/site) site."""
    valid = {
        build_site_enabled_key(sector, cluster, site),
        build_site_transformation_key(sector, cluster, site),
    }
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(build_site_data_key(sector, cluster, site, f"{ctm_col}_demand"))
        valid.add(build_site_data_key(sector, cluster, site, f"{ctm_col}_production"))
    for ctm_col in CTM_EMISSION_COLUMN_MAP.values():
        valid.add(build_site_data_key(sector, cluster, site, ctm_col))
    return valid


def get_valid_keys_for_bottom_up_site(site: str) -> set:
    """All valid CTM input keys for a bottom-up (flat) site."""
    valid = {
        build_bottom_up_enabled_key(site),
        build_bottom_up_transformation_key(site),
    }
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(build_bottom_up_data_key(site, f"{ctm_col}_demand"))
        valid.add(build_bottom_up_data_key(site, f"{ctm_col}_production"))
    for ctm_col in CTM_EMISSION_COLUMN_MAP.values():
        valid.add(build_bottom_up_data_key(site, ctm_col))
    return valid


def get_valid_keys_for_custom_site(site_id: str) -> set:
    """All valid CTM input keys for a custom (##new_cc_siteN##) site."""
    valid = {
        build_custom_site_enabled_key(site_id),
        build_custom_site_sector_key(site_id),
        build_custom_site_cluster_key(site_id),
        build_custom_site_latitude_key(site_id),
        build_custom_site_longitude_key(site_id),
    }
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(build_custom_site_data_key(site_id, f"{ctm_col}_demand"))
        valid.add(build_custom_site_data_key(site_id, f"{ctm_col}_production"))
    for ctm_col in CTM_EMISSION_COLUMN_MAP.values():
        valid.add(build_custom_site_data_key(site_id, ctm_col))
    return valid


def get_valid_keys_for_cluster(sector: str, cluster: str) -> set:
    """All valid CTM input keys for a cluster-level entry."""
    valid = {build_cluster_enabled_key(sector, cluster)}
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(build_cluster_data_key(sector, cluster, f"{ctm_col}_demand"))
        valid.add(build_cluster_data_key(sector, cluster, f"{ctm_col}_production"))
    return valid


def get_valid_keys_for_sector(sector: str) -> set:
    """All valid CTM input keys for a sector-level entry."""
    valid = {build_sector_enabled_key(sector)}
    for ctm_col in CTM_ENERGY_COLUMN_MAP.values():
        valid.add(build_sector_data_key(sector, f"{ctm_col}_demand"))
        valid.add(build_sector_data_key(sector, f"{ctm_col}_production"))
    return valid


# ═══════════════════════════════════════════════════════════════════════
# Key inspection utilities
# ═══════════════════════════════════════════════════════════════════════

def parse_key(key: str) -> dict:
    """Break a CTM key into its parts, with a few convenience flags."""
    parts = key.split("&&")
    return {
        "parts": parts,
        "depth": len(parts),
        "is_custom": parts[0].startswith("##new_cc_site"),
        "raw_key": key,
    }


def is_enabled_key(key: str) -> bool:
    return key.endswith("&&enabled")


def is_site_key(key: str) -> bool:
    """4-part key: sector&&cluster&&site&&column."""
    return len(key.split("&&")) == 4


def is_bottom_up_key(key: str) -> bool:
    """2-part key: site&&column (and not a custom site)."""
    parts = key.split("&&")
    return len(parts) == 2 and not parts[0].startswith("##")


def is_custom_key(key: str) -> bool:
    return key.split("&&")[0].startswith("##new_cc_site")
