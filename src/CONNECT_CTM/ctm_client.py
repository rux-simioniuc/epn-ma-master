import requests
from .ctm_constants import CLUSTERS

# ── Config ─────────────────────────────────────────────────────────────────
CTM_LIVE = "https://carbontransitionmodel.com/api/"
CTM_BETA = "https://beta.carbontransitionmodel.com/api/"

HEADERS = {
    "Content-Type": "application/json",
    "Model": "CTM",
}


# ── Core API call ──────────────────────────────────────────────────────────

class CTMClient:
    def __init__(self, use_beta: bool = False):
        self.url            = CTM_BETA if use_beta else CTM_LIVE
        self.session_id     = None
        self.ms_graph_session = None
        self.all_args = None

    def _call(self, payload: dict) -> dict:
        """Make a raw API call, reusing MSGraphSession for speed."""
        if self.ms_graph_session:
            payload["MSGraphSession"] = self.ms_graph_session
        response = requests.post(self.url, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        # always update the graph session token
        self.ms_graph_session = data.get("MSGraphSession", self.ms_graph_session)
        if "warnings" in data:
            print(f"  [CTM warn] {data['warnings']}")
        return data
    
    def load_all_list(self):
        if self.all_args is None:
            print('Loading all arguments...')
            self.all_args = self._call({
                "SessionID": self.session_id,
                "outputs": [],
                "special": ["requestFullList"],
                }).get("output_values", {})
        # return self.all_args
    
    def find_sector_cluster_site(self, site_name: str) -> dict | None:
        """
        Find a site in the CTM API and return its sector/cluster.
        
        Returns:
            {
                "sector": "...",
                "cluster": "...",
                "site": "...",
            }
            or None if not found
        """
        self.load_all_list()

        # keys = self.all_args.keys()
        site_keys = {k:v for k, v in self.all_args.items() if site_name in k}

        # lookup = {}

        for key in site_keys:
            parts = key.split("&&")

            # sector&&cluster&&site&&column
            if len(parts) >= 4:
                if site_name == 'chemelot_other':
                    print('stop')
                # need this to handle cases when a plant name is a substring of another plant name
                if parts[2] == site_name or parts[3] == site_name:
                    idx = parts.index(site_name)
                # if idx == 2:
                # and parts[2] == site_name:
                
                # lookup[site_name] = {
                #     "sector": parts[idx-2],
                #     "cluster": parts[idx-1]
                #     }

                    return {
                        "sector": parts[idx-2],
                        "cluster": parts[idx-1],
                        "site": parts[idx],
                    }
                

        return None
    
    def build_site_lookup(self):
        """
        Returns:
            {
                site_name: {
                    "sector": "...",
                    "cluster": "..."
                }
            }
        """
        self.load_all_list()

        lookup = {}

        for key in self.all_args.keys():

            parts = key.split("&&")

            # sector&&cluster&&site&&column
            if len(parts) >= 4:
                sector, cluster, site, _ = parts

                if site not in lookup:
                    lookup[site] = {
                        "sector": sector,
                        "cluster": cluster,
                    }

        return lookup


    # ── Session management ─────────────────────────────────────────────────

    def load_session(self, session_id: str) -> str:
        """Load an existing CTM session by ID."""
        self.session_id = session_id
        
        # Verify the session exists by making a test call
        try:
            data = self._call({
                "SessionID": self.session_id,
                "outputs": [],
            })
            print(f"Session loaded: {self.session_id}")
            # Update MS graph session if returned
            self.ms_graph_session = data.get("MSGraphSession", self.ms_graph_session)
            return self.session_id
        except Exception as e:
            self.session_id = None
            print(f"Failed to load session {session_id}: {e}")
            raise Exception(f"Failed to load session {session_id}: {e}")


    def create_clean_sheet_session(self) -> str:
        """
        Create a session from base and immediately apply clean sheet settings.
        This disables all CTM built-in calculations so only explicitly set data
        is sent to the ETM.
        """
        # Step 1: create session from base
        data = self._call({"ScenarioID": "SC-38de635397b1e85f", "outputs": []})
        self.session_id = data["SessionID"]
        print(f"Session created: {self.session_id}")

        # Step 2: apply clean sheet settings (disable all built-in calculations)
        self.set_inputs({
            "other_settings_other_industry_disable_inputs_input": "1",
            "other_settings_ctm_bottom_up_sites_input":           "1",
            "other_settings_disable_waste_incineration_to_etm_input": "1",
            "other_settings_fertilizers_to_chemicals_etm_input": "1",
        })
        print("Clean sheet applied.")
        return self.session_id

    def delete_session(self):
        """Permanently delete the current session."""
        if not self.session_id:
            return
        # deleteSession returns plain text, not JSON
        response = requests.post(
            self.url,
            headers=HEADERS,
            json={"SessionID": self.session_id, "special": ["deleteSession"]},
        )
        print(f"Session deleted: {response.text}")
        self.session_id     = None
        self.ms_graph_session = None

    # ── Inputs ─────────────────────────────────────────────────────────────

    def set_inputs(self, inputs: dict, outputs: list = None) -> dict:
        """Set one or more input values. Returns output values if requested."""
        data = self._call({
            "SessionID": self.session_id,
            "inputs":    inputs,
            "outputs":   outputs or [],
        })
        return data.get("output_values", {})

    # ── Data level helpers ─────────────────────────────────────────────────

    def set_sector(self, sector: str, column: str, value: str,
                   disable_clusters: bool = True):
        """
        Set a value at sector level and optionally disable all clusters
        to avoid ambiguity (recommended per docs).
        """
        inputs = {
            f"{sector}&&sector&&enabled":    "1",
            f"{sector}&&sector&&{column}":   value,
        }
        if disable_clusters:
            for cluster in CLUSTERS:
                inputs[f"{sector}&&{cluster}&&cluster&&enabled"] = "0"
        self.set_inputs(inputs)

    def set_cluster(self, sector: str, cluster: str, column: str, value: str,
                    disable_sector: bool = True):
        """
        Set a value at cluster level and optionally disable the sector level.
        """
        inputs = {
            f"{sector}&&{cluster}&&cluster&&enabled": "1",
            f"{sector}&&{cluster}&&cluster&&{column}": value,
        }
        if disable_sector:
            inputs[f"{sector}&&sector&&enabled"] = "0"
        self.set_inputs(inputs)

    def set_site(self, sector: str, cluster: str, site: str,
                 column_values: dict,
                 disable_sector: bool = True,
                 disable_cluster: bool = True):
        """
        Enable a site and set one or more column values for it.
        Optionally disable sector and cluster levels to avoid ambiguity.

        column_values: dict of {column: value}, e.g.
            {"electricity_demand": "100", "natural_gas_demand": "200"}
        """
        inputs = {
            f"{sector}&&{cluster}&&{site}&&enabled": "1",
        }
        for column, value in column_values.items():
            inputs[f"{sector}&&{cluster}&&{site}&&{column}"] = value

        if disable_sector:
            inputs[f"{sector}&&sector&&enabled"] = "0"
        if disable_cluster:
            inputs[f"{sector}&&{cluster}&&cluster&&enabled"] = "0"

        self.set_inputs(inputs)

    def set_bottom_up_site(self, site: str, column_values: dict):
        """
        Set values for a bottom-up site (Shell Pernis, Tata Steel, etc.).
        These use a flat sitename&&column pattern with no sector/cluster prefix.
        """
        inputs = {f"{site}&&enabled": "1"}
        for column, value in column_values.items():
            inputs[f"{site}&&{column}"] = value
        self.set_inputs(inputs)

    # ── Outputs ────────────────────────────────────────────────────────────

    def get_outputs(self, output_ids: list) -> dict:
        """Read one or more output values."""
        data = self._call({
            "SessionID": self.session_id,
            "outputs":   output_ids,
        })
        return data.get("output_values", {})

    def get_all_outputs(self) -> dict:
        """Dump all available output values."""
        data = self._call({
            "SessionID": self.session_id,
            "outputs":   [],
            "special":   ["requestOutputList"],
        })
        return data.get("output_values", {})

    # ── ETM coupling (for later) ───────────────────────────────────────────

    def couple_etm(self, etm_scenario_id: str = None, etm_session_id: str = None,
                   auth_token: str = None):
        """
        Couple the CTM session to an ETM scenario.
        Provide either etm_scenario_id (saved) or etm_session_id (live).
        """
        inputs = {"etm_coupling_switch": "1"}
        if etm_scenario_id:
            inputs["etm_scenario_id"] = etm_scenario_id
        if etm_session_id:
            inputs["etm_session_id"] = etm_session_id
        if auth_token:
            inputs["etm_authorization_token"] = auth_token

        outputs = ["etm_session_id"] if etm_scenario_id else []
        result = self.set_inputs(inputs, outputs=outputs)
        if "etm_session_id" in result:
            print(f"ETM session: {result['etm_session_id']}")
        return result

    def get_available_sites(self) -> dict:
        """
        Returns all sites known to the CTM, grouped by category:
        - 'sector_cluster': regular sites under sector/cluster hierarchy
        - 'bottom_up': large industrial sites (Shell Pernis, Tata Steel etc.)
        - 'custom': ##new_cc_siteN## placeholder slots
        """

        print(f'sesh id: {self.session_id}')
        data = self._call({
            "SessionID": self.session_id,
            "outputs":   [],
            "special":   ["requestFullList"],
        })
        all_keys = data.get("output_values", {}).keys()

        sector_cluster, bottom_up, custom = set(), set(), set()

        for key in all_keys:
            if not key.endswith("&&enabled"):
                continue
            parts = key.split("&&")
            if key.startswith("##new_cc_site"):
                custom.add(parts[0])
            elif len(parts) == 2:
                # sitename&&enabled -> bottom-up
                bottom_up.add(parts[0])
            elif len(parts) == 4:
                # sector&&cluster&&site&&enabled -> regular site
                sector_cluster.add(parts[2])

        return {
            "sector_cluster": sorted(sector_cluster),
            "bottom_up":      sorted(bottom_up),
            "custom":         sorted(custom),
        }
    
    