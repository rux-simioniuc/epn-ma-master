import streamlit as st


def render_info_tab():
    st.title('ScenarioFlow')
    st.caption("Automation tool for the DSH → CTM → ETM workflow, plus visualization and regionalisation")

    st.markdown(
        """
        This tool automates and simplifies the workflow between
        **DataSafeHouse (DSH)**, the **Carbon Transition Model (CTM)**,
        and the **Energy Transition Model (ETM)** — and adds visualization
        and regionalisation on top of the pushed scenario data.

        It reduces manual data preparation and transfer while providing
        a consistent, reproducible workflow for scenario analysis.
        """
    )

    st.divider()

    # ── Workflow overview ────────────────────────────────────────────
    st.header("Workflow")

    col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([2, 1, 2, 1, 2, 1, 2, 1, 2])

    with col1:
        st.subheader("1. DSH")
        st.caption("Upload raw DSH CSVs, generate a per-plant Excel workbook.")
    with col2:
        st.markdown("### →")
    with col3:
        st.subheader("2. Mapping")
        st.caption("Map DSH plants to CTM sectors, clusters, and site types.")
    with col4:
        st.markdown("### →")
    with col5:
        st.subheader("3. CTM")
        st.caption("Aggregate scenario data and push it to CTM sessions.")
    with col6:
        st.markdown("### →")
    with col7:
        st.subheader("4. ETM")
        st.caption("Couple CTM sessions to ETM for scenario analysis.")
    with col8:
        st.markdown("### →")
    with col9:
        st.subheader("5. Beyond")
        st.caption("Visualize trends, or regionalise demand to site level.")

    st.divider()

    # ── What the tool does ───────────────────────────────────────────
    st.header("What can you do with the tool?")

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.subheader("Data Upload & Mapping")
            st.markdown(
                """
                - Upload plant-level Excel files
                - Validate uploaded data
                - Map DSH plants to CTM sectors and clusters
                - Check plant and mapping consistency
                """
            )

        with st.container(border=True):
            st.subheader("Data Processing & Aggregation")
            st.markdown(
                """
                - Process plant-level data
                - Handle scenarios and years
                - Aggregate data by plant, sector, and cluster
                - Prepare data in the required CTM structure
                """
            )

        with st.container(border=True):
            st.subheader("Production & Capacity")
            st.markdown(
                """
                - Extract production and CHP information
                - Process operating power and flexibility data
                - Combine data across plants
                - Maintain consistent scenario/year columns
                """
            )

    with col2:
        with st.container(border=True):
            st.subheader("Visualization")
            st.markdown(
                """
                Explore trends across:
                - Individual plants
                - Clusters
                - Sectors
                - Scenarios and years
                - Per-plant contribution within a cluster/sector
                """
            )

        with st.container(border=True):
            st.subheader("Regionalisation")
            st.markdown(
                """
                - Allocate electricity demand to site/neighbourhood level
                - Split by grid level (TSO/DSO)
                - Export a merged-header Excel matching the target format
                """
            )

    st.divider()

    # ── Per-tab documentation ────────────────────────────────────────
    st.header('How to use each tab')

    with st.expander("GENERAL INFO", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            Accepted sectors:
            - other_chemicals
            - aluminium
            - other_metals
            - non_metallic_minerals
            - transport_equipment
            - machinery
            - mining_and_quarrying
            - food
            - paper
            - central_ict
            - wood_and_wood_products
            - construction
            - textile_and_leather
            - other
            - refineries
            - steel
            - fertilizers
            - steam cracking
            """)

        with col2:
            st.markdown("""
            Accepted clusters:
            - noord_nederland
            - nzkg
            - rotterdam_moerdijk
            - zeeland_west_brabant
            - chemelot
            - cluster_6
            """)

    with st.expander("DSH Input & Output", expanded=False):
        st.write(
            'This tab has one function: receiving the raw `csv` files from DataSafeHouse and '
            'transforming them into user-friendly Excel files — one workbook per plant, with '
            'multiple sheets.'
        )
        st.subheader('Input')
        st.write('All 10 `csv` files must be uploaded for the program to run. These are:')

        st.markdown(
            """
            1. Plant details
            2. Reference emissions
            3. Reference utilities
            4. Forecast emissions
            5. Forecast utilities
            6. Project emissions
            7. Project utilities
            8. Electricity production
            9. Energy storage
            10. Flexibility options
            """
        )

        st.write(
            "Files can be uploaded in two ways: dump all 10 at once in the 'Upload all files' "
            "section (simplest), or use each individual uploader if that fails."
        )

        st.subheader('Output')

        st.markdown(""" 
        After uploading all DSH files, some options are available for customizing the resulting
        Excel files (_Scenario Settings_ section). These settings affect the _Emissies en
        energiebalansen_ sheet and the scenario sheets.

        _Number of scenarios_, _Scenario names_, and _Scenario years_ only affect the formatting
        of the scenario sheets. _Reference year_ picks which year is shown as the reference.

        Excels can be generated for all plants at once, or for a selected subset — choosing a
        subset significantly reduces processing time. Generated files can be downloaded
        individually or as a ZIP archive.
        """)

        st.subheader('Known issues and bugs')
        st.markdown(
            """
            - The script relies on a specific format for each CSV file fetched from DSH. Changes
              to this format need to be accounted for in the code.
            - The separator in the CSV files **must be a comma (,), not a semicolon (;)**.
            """
        )

    with st.expander("CTM/ETM Workflow", expanded=False):
        st.markdown(
            """
            This tab receives filled-in plant Excel files, a mapping file, and (optionally)
            sector/cluster demand curves, and transforms them into CTM inputs. These inputs are
            pushed to CTM sessions, which can then be coupled to ETM.
            """
        )
        st.subheader('Input')
        st.write("There are 3 categories of file inputs.")

        st.write("##### 1. Plant files")
        st.markdown(
            """
            - Format: `xlsx`
            - Optional: No
            - Contents: same format as generated by the DSH Input & Output tab.
            """
        )

        st.write("##### 2. Mapping")
        st.markdown(
            """
            - Format: `xlsx` or `csv`
            - Optional: No
            - Required columns: `Name`, `Name reformatted`, `Sector`, `Cluster`,
              `API input name`, `DSH plant name`, `DSH plant id`
            """
        )

        st.write("##### 3. Sector/Cluster curves")
        st.markdown(
            """
            - Format: `xlsx`
            - Optional: Yes — needed only for demand not tied to a specific plant
            """
        )

        st.subheader('Process')
        st.markdown(
            """
            **Step 1: Upload Data Files** — upload the required files. If no errors appear,
            proceed to Settings.

            **Step 2: Settings** — choose the CTM version (Beta by default), and whether to
            create fresh CTM sessions or reuse existing ones.

            Existing session IDs can be provided either as a pasted `JSON` file or as plain
            text, in the format `{('Scenario', 'Year'): 'SE-xxxx'}`.

            Reference year, scenario years, and scenario names are automatically extracted from
            the uploaded plant files. They can be removed here (to exclude a scenario/year from
            the push) but not edited — this step is mainly for double-checking that the right
            combinations are included before pushing.

            **Step 3: Push to CTM** — select which scenario/year combinations to push. Extra
            inputs can be added manually (e.g. coordinates for new sites, or transformation
            overrides). Press **Push to CTM** to start.

            **Step 4: Couple to ETM** — ETM session IDs can be pasted the same way as CTM
            session IDs. A different ETM version can also be selected. Coupling requires both
            the ETM **access token** (set in the sidebar) and matching CTM session IDs.
            """
        )

        st.subheader('Known issues and bugs')
        st.markdown(
            """
            - It's possible to start coupling to ETM without all prerequisites met (token + CTM
              session IDs) — this will simply error rather than being blocked upfront.
            - Once something is pushed to CTM, individual values can't be deleted, only
              overwritten. Creating a new session is the simplest way to start clean.
            - **Repeat pushes to the same session only send what's changed.** A local file per
              session tracks the last-known full state, so unchanged values aren't re-sent, and
              a value that dropped to zero is still explicitly pushed as `0` (not silently
              skipped) so the old nonzero value doesn't stay live in CTM. If a push looks stale
              or wrong, this local file may need clearing to force a full re-push.
            """
        )

    with st.expander("Visualization", expanded=False):
        st.markdown(
            """
            Available once plant data has been aggregated in the CTM/ETM Workflow tab
            (_"Aggregate the data"_ button in Step 1).

            A **scenario multiselect** at the top filters everything below it — every section
            respects the current selection.

            - **Individual plant viz** — pick one plant and one emission/utility metric, see it
              plotted by year, colored by scenario, dashed by flow type.
            - **Cluster-level aggregation** — pick a cluster and metric to see totals across all
              plants in that cluster, plus emissions/utilities bar charts for a chosen scenario.
            - **Sector-level aggregation** — same as cluster-level, but grouped by sector. An
              `all_chemicals` option combines the organic/inorganic/other chemicals sectors.
            - **Plant breakdown** (within cluster and sector views) — a stacked bar chart
              showing each plant's individual contribution, with the total overlaid as a line,
              for a chosen flow type.
            """
        )

    with st.expander("Regionalisation", expanded=False):
        st.markdown(
            """
            Allocates per-plant scenario **electricity demand** down to site/neighbourhood
            level, formatted to match a specific target Excel layout used downstream.

            **Inputs:**
            - The same aggregated plant scenario data used elsewhere in the app.
            - A location/provider mapping (plant identifier → buurtcode, buurtnaam, and
              grid level — TSO or DSO — per utility).
            - A `categories_overview.csv` file listing every valid
              (energy carrier, grid level, demand type, category) combination — every one of
              these becomes a column in the output, even if no plant data matches it yet.

            **Output:** an Excel file with merged header rows (Scenario, Year, Sector, PtH,
            Carrier, Level, Type, ID) and one row per site (Site, Buurtcode, Postcode).

            **Known gaps:**
            - Postcode isn't in the location mapping yet — the column is written blank.
            - There's no data source yet that splits demand into PtH vs. non-PtH, so PtH-flagged
              columns are always left blank rather than filled with a guess.
            - Only the `Demand` type is populated; `Flexibility` isn't wired up yet.
            - Currently electricity-only; other carriers aren't implemented yet.
            """
        )

    with st.expander("Sidebar options", expanded=False):
        st.markdown(
            """
            - **ETM Authorization Token** (top of sidebar) — required for Step 4 (Couple to
              ETM) in the CTM/ETM Workflow tab. Entered as a password field; not saved to disk.
            - **Memory usage** — shown for troubleshooting if the app feels slow.
            - **Download helper files** (bottom of sidebar) — once plant files, mapping, and/or
              DSH reference files are loaded:
                - *Master Energy Balance File* — combined emissions/utilities across all plants.
                - *Master Projects File* — combined project-level emissions/utilities.
                - *Power Units Overview* — per-plant generation units and their operating power.
            """
        )

    with st.expander("EXTRA: Debugging", expanded=False):
        st.write(
            "Most important logs are shown in the GUI. Checking the terminal / command line can "
            "also give valuable insight into why the program might be failing."
        )
        st.write(
            "If a CTM push looks stale or incorrect, check the persistent input-diffing file for "
            "that session (see the CTM/ETM Workflow known issues above) — clearing it forces a "
            "full re-push instead of a delta."
        )
        st.write(
            "If issues persist and Claude / Copilot / ChatGPT don't help, contact Rux at "
            "ruxandra.simioniuc@tennet.eu"
        )

    st.divider()

    # ── Why use it ────────────────────────────────────────────────────
    st.header("Why use this tool?")

    reasons = [
        "Reduce repetitive manual processing",
        "Standardize the DSH–CTM–ETM workflow",
        "Reduce the risk of manual data-entry errors",
        "Make scenario data easier to prepare and inspect",
        "Provide a reproducible workflow across multiple plants",
        "Make processed data easier to visualize, validate, and regionalise",
    ]

    for reason in reasons:
        st.markdown(f"- {reason}")

    st.divider()

    with st.expander("Data processing notes"):
        st.markdown(
            """
            The application performs validation and transformation steps before data is
            aggregated or pushed.

            Where possible, missing or invalid data is flagged during processing (via on-screen
            warnings and terminal logs) rather than silently ignored — but always double-check
            outputs against source data for anything business-critical.

            Make sure uploaded workbooks follow the expected structure before processing; an
            unexpected sheet layout is the most common cause of a silent or confusing failure.
            """
        )

    st.divider()

    st.caption("Developed to support the DSH–CTM–ETM scenario workflow.")