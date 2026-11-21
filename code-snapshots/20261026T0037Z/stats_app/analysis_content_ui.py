"""Browse collected Meta content without combining lifetime captures."""
from datetime import date

import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_content import (
    CONTENT_PATH, MANUAL_PATH, PREFIX, conflicting_publication_identities, content_identity_inventory,
    load_content_observations, publication_inventory,
    search_content, select_content_observations,
)
from stats_app.analysis_social_metrics import filtered_csv


def render_content_library(repo):
    st.subheader("Collected posts & Stories")
    st.caption("Search native exports, inherited content and separately recovered Story observations. Lifetime values describe each capture; they are never added across captures or assigned to publication-day activity.")
    try:
        observations = load_content_observations(repo)
    except (ValueError, KeyError) as exc:
        st.error("Content identity or observation evidence could not be interpreted: " + str(exc))
        return
    if observations.empty:
        st.info("No retained content observations are available in this analysis version.")
        return
    platforms = sorted(observations.platform_selected.unique())
    selected_platforms = controls.multiselect("Content platforms", platforms, default=platforms, key="content-library-platforms")
    selected = observations.loc[observations.platform_selected.isin(selected_platforms)].copy()
    formats = sorted(selected.post_type.unique())
    chosen_formats = controls.multiselect("Content formats · Stories included", formats, default=formats, key="content-library-formats")
    selected = selected.loc[selected.post_type.isin(chosen_formats)]
    query = controls.text_input("Search collected posts · text, ID or link", key="content-library-query")
    modes = {"Latest compatible captures": "latest", "All retained captures": "all", "Unknown capture time": "unknown_capture"}
    display = controls.radio("Content display", ["One row per post", "Capture observations"], key="content-library-display", horizontal=True)
    view = controls.selectbox("Content observation view", list(modes), key="content-library-observations")
    with st.expander("Refine sources & scope", expanded=False):
        kinds = sorted(observations.source_kind.unique())
        kind_labels = {"native_export": "New native exports", "inherited_export": "Inherited exports", "manual_story_detail": "Recovered Story details"}
        selected_kinds = controls.multiselect("Content evidence sources", kinds, default=kinds, key="content-library-sources",
                                             format_func=lambda value: kind_labels.get(value, value.replace("_", " ")))
        selected = selected.loc[selected.source_kind.isin(selected_kinds)]
        account_labels = selected.apply(lambda r: f"{r.platform_selected} · {r.identity_account_id_type} · {r.identity_account_id}", axis=1) if not selected.empty else selected.identity_account_id
        accounts = sorted(account_labels.unique())
        chosen_accounts = controls.multiselect("Content accounts", accounts, default=accounts, key="content-library-accounts")
        selected = selected.loc[account_labels.isin(chosen_accounts)]
        authors = sorted(selected.author_scope.unique())
        chosen_authors = controls.multiselect("Content authors", authors, default=authors, key="content-library-authors")
        selected = selected.loc[selected.author_scope.isin(chosen_authors)]
        scopes = sorted(selected.metric_platform_scope.unique())
        chosen_scopes = controls.multiselect("Content metric scope", scopes, default=scopes, key="content-library-scopes")
        selected = selected.loc[selected.metric_platform_scope.isin(chosen_scopes)]
        st.caption("Account identities and measured platform scopes remain separate. Select multiple scopes to inspect them alongside each other; their lifetime metrics are never combined.")
    if selected.empty:
        st.info("Choose at least one available evidence source and platform, format, account, author and metric scope.")
        return
    st.caption(f"Active filters: {len(selected_platforms)} platform(s), {len(chosen_formats)} format(s), {len(selected_kinds)} evidence source(s), {len(chosen_accounts)} account(s). Refine sources & scope shows the detailed selections.")
    if len(selected_kinds) < len(kinds):
        st.caption("Some available evidence sources are excluded by your saved selection; expand Refine sources & scope to include them.")
    publication_conflicts = conflicting_publication_identities(selected)
    data = select_content_observations(selected, modes[view])
    date_mode = controls.radio("Publication dates", ["All, including unknown", "Known dates only", "Unknown dates only"],
                               key="content-library-date-mode", horizontal=True)
    if date_mode == "Unknown dates only":
        data = data.loc[data.publication_date.eq("")]
    elif date_mode == "Known dates only":
        data = data.loc[data.publication_date.ne("")]
        if not data.empty:
            low, high = date.fromisoformat(data.publication_date.min()), date.fromisoformat(data.publication_date.max())
            period = controls.date_range("Content publication range", low, high, (low, high), key="content-library-publications")
            if period is None:
                return
            data = data.loc[data.publication_date.between(period[0].isoformat(), period[1].isoformat())]
    data = search_content(data, query)
    if data.empty:
        st.info("No retained observations match these filters. Missing inventory does not establish zero publishing.")
        return
    if data.source_table.eq(MANUAL_PATH).any():
        manual = data.loc[data.source_table.eq(MANUAL_PATH)]
        bridge_note = ("A verified selected-account bridge is applied where supported; it does not establish authorship or supply missing publication dates."
                       if manual.identity_basis.str.startswith("verified_account_bridge:").any()
                       else "Account identities remain separate until an evidenced bridge is available.")
        st.info("Manual Story recovery preserves raw MBS asset IDs and yearless publication text. Original malformed export rows stay quarantined. " + bridge_note)
    if CONTENT_PATH not in repo.tables:
        st.caption("This saved version predates the new native content collection; it shows inherited and recovered evidence only.")
    conflicts = int(data.selection_status.eq("same_time_conflict").sum())
    unknown_capture = int(data.capture_time_utc.isna().sum())
    unresolved_identity = int((~data.identity_complete).sum())
    if conflicts:
        st.warning(f"{conflicts} observations have conflicting values at the same capture time. All remain available in Capture observations and retained history; no winner or combined value is inferred.")
    if unknown_capture:
        st.warning(f"{unknown_capture} observations have unknown capture time. They remain separate in Capture observations and cannot establish the newest lifetime value.")
    if unresolved_identity:
        st.warning(f"{unresolved_identity} observations have incomplete platform/account/post identity. They remain visible but are excluded from distinct-publication counts.")
    visible_date_conflicts = publication_conflicts.intersection(data.identity_key)
    if visible_date_conflicts:
        st.warning(f"{len(visible_date_conflicts)} distinct content identities have conflicting known publication dates across the selected retained evidence. The latest-capture view does not resolve those differences; these identities are excluded from the publication inventory below.")
    cards = st.columns(3)
    cards[0].metric("Distinct content identities", f"{data.loc[data.identity_complete, 'identity_key'].nunique():,}")
    cards[1].metric("Filtered capture observations", f"{len(data):,}")
    cards[2].metric("Identities with undated captures", f"{data.loc[data.publication_date.eq(''), 'identity_key'].nunique():,}")
    known = data.capture_time_utc.dropna()
    if not known.empty:
        st.caption(f"Known captures shown: {known.min().isoformat()} – {known.max().isoformat()} UTC. Different metric scopes remain separate even for the same content identity.")
    st.caption("Counts describe retained inventory, not statistical sample size or complete publishing history. Views, reach, link clicks and streams remain separate outcomes.")
    display_metrics = [metric for metric in ("views", "reach", "impressions", "interactions", "engagement_actions", "link_clicks") if data[metric].notna().any()]
    columns = ["platform_selected", "identity_account_id_type", "identity_account_id", "post_id", "post_type", "description",
               "publication_date", "published_local", "snapshot_timestamp", "source_kind", "metric_platform_scope", "selection_status", *display_metrics, "permalink"]
    shown = data.sort_values(["publication_date", "snapshot_timestamp", "post_id"], ascending=[False, False, True], na_position="last")
    config = {"permalink": st.column_config.LinkColumn("Open post", display_text="Open"),
              "description": st.column_config.TextColumn("Post text", width="large")}
    if display == "One row per post":
        inventory = content_identity_inventory(shown, selected)
        st.caption("One row represents one platform/account/post identity. Capture counts follow the current observation and date filters. Publication dates include all retained evidence within the selected sources and scopes; conflicting dates remain explicit. Metrics are available in Capture observations and retained history.")
        st.dataframe(inventory.drop(columns=["identity_key"]), hide_index=True, width="stretch", column_config=config)
        st.download_button("Download filtered post inventory · CSV", filtered_csv(inventory), "content_inventory_filtered.csv", "text/csv", key="content-library-inventory-download")
    else:
        st.dataframe(shown[columns], hide_index=True, width="stretch", column_config=config)
    st.download_button("Download filtered content observations · CSV", filtered_csv(shown), "content_observations_filtered.csv", "text/csv", key="content-library-download")
    with st.expander("Publication inventory · known dates only"):
        cadence = publication_inventory(data.loc[~data.identity_key.isin(publication_conflicts)])
        st.caption("Each content identity contributes at most one publication. Unknown or conflicting dates do not appear here. Lifetime views are never allocated to these dates.")
        st.dataframe(cadence, hide_index=True, width="stretch")
    with st.expander("Inspect a post and its retained capture history"):
        labels = {str(row.identity_key): f"{row.platform_selected} · {row.post_id} · {str(row.description)[:70]}" for row in data.itertuples()}
        identity = controls.selectbox("Content identity", list(labels), format_func=labels.get, key="content-library-inspect")
        history = observations.loc[observations.identity_key.eq(identity)].sort_values("snapshot_timestamp", ascending=False)
        st.caption("This history includes every retained source for this identity, including captures outside the current source/format filters. No lifetime change or causal attribution is calculated.")
        st.dataframe(history.drop(columns=["capture_time_utc"]), hide_index=True, width="stretch")
        st.download_button("Download this content's retained captures", filtered_csv(history), "content_capture_history.csv", "text/csv", key="content-library-history-download")
    with st.expander("Source details and original tables"):
        status_path = PREFIX + "collection_status.csv"
        if status_path in repo.tables:
            st.caption("Collection coverage and unresolved source limitations")
            st.dataframe(repo.table(status_path), hide_index=True, width="stretch")
        provenance = ["source_table", "source_table_sha256", "source_file", "source_sha256", "source_record", "table_record",
                      "source_url", "snapshot_timestamp", "account_id_type_raw", "selected_account_id", "identity_basis", "observation_id"]
        st.dataframe(shown[provenance], hide_index=True, width="stretch")
        for path in sorted(data.source_table.unique()):
            st.download_button("Download unchanged " + path.rsplit("/", 1)[-1], repo.original_bytes(path),
                               path.rsplit("/", 1)[-1], "text/csv", key="content-original-" + path)
