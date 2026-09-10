"""
ETM Coupling - push a CTM session's outputs into an ETM (Energy Transition
Model) scenario.
"""

import time
from typing import Dict, List, Optional, Tuple

from .ctm_client import CTMClient


def push_ctm_scenario_to_etm(
    ctm_session: str,
    etm_session: str,
    etm_token: str,
    log_container=None,
) -> Optional[dict]:
    """
    Load a CTM session and couple it to a live ETM session.
    Returns the ETM coupling result dict, or None on failure.
    """

    def log_message(msg: str):
        print(msg)
        if log_container:
            log_container.write(msg)

    try:
        ctm = CTMClient(use_beta=True)
        ctm.load_session(session_id=ctm_session)
    except Exception as e:
        log_message(f"[ERROR] Loading CTM session {ctm_session}: {e}")
        return None

    try:
        etm_result = ctm.couple_etm(auth_token=etm_token, etm_session_id=etm_session)
        log_message(f"[SUCCESS] Pushed CTM {ctm_session} to ETM {etm_session}")
        return etm_result
    except Exception as e:
        log_message(f"[ERROR] Pushing CTM {ctm_session} to ETM {etm_session}: {e}")
        return None


def couple_all_sessions_to_etm(
    ctm_sessions: Dict[Tuple[str, str], str],
    etm_sessions: Dict[Tuple[str, str], str],
    etm_token: str,
    max_retries: int = 3,
    retry_delay_seconds: float = 1.0,
    log_container=None,
) -> Tuple[Dict[Tuple[str, str], dict], List[str]]:
    """
    Couple every (scenario, year) CTM session to its matching ETM session,
    retrying on failure. This replaces the retry loop that used to be
    written inline in the Streamlit app.

    Args:
        ctm_sessions: {(scenario, year): ctm_session_id, ...}
        etm_sessions: {(scenario, year): etm_session_id, ...}

    Returns:
        ({(scenario, year): etm_result, ...}, logs)
        Only successful couplings appear in the results dict.
    """
    logs: List[str] = []
    results: Dict[Tuple[str, str], dict] = {}

    def log(msg: str):
        logs.append(msg)
        if log_container:
            log_container.text(msg)

    for scenario, year in ctm_sessions.keys():
        ctm_session = ctm_sessions[(scenario, year)]
        etm_session = etm_sessions.get((scenario, year))

        if etm_session is None:
            log(f"[SKIP] {scenario}/{year}: no matching ETM session")
            continue

        log(f"Pushing {scenario} {year}; CTM {ctm_session} -> ETM {etm_session}")

        result = None
        for attempt in range(1, max_retries + 1):
            result = push_ctm_scenario_to_etm(ctm_session, etm_session, etm_token)

            if result is not None:
                log(f"  Success on attempt {attempt}")
                break

            if attempt < max_retries:
                log(f"  Attempt {attempt} failed, retrying...")
                time.sleep(retry_delay_seconds)
            else:
                log(f"  Failed after {max_retries} attempts")

        if result is not None:
            results[(scenario, year)] = result
            log(f"  {scenario}/{year} SUCCESS")
        else:
            log(f"  {scenario}/{year} FAILED")

    return results, logs
