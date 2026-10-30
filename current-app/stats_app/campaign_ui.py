"""Content and campaign metadata log, separate from performance observations."""
import hashlib

import pandas as pd
import plotly.express as px
import streamlit as st
from stats_app import dashboard_controls as controls

from stats_app.campaign_log import CampaignLogRepository, editable_csv, export_csv, parse_campaign_csv, template_bytes


def render_campaigns(local_repo, principal, analysis=None):
    controls.jump("Open the 14-day content plan", "Content plan", key="campaigns:open-content-plan")
    repo = CampaignLogRepository(local_repo.db_path)
    st.subheader("Content & campaign log")
    notice = st.session_state.pop("campaign-import-notice", None)
    if notice:
        st.success(notice)
    st.caption("One latest metadata revision per platform, account and post/event ID. Earlier revisions and exact imported CSVs are retained in the writable library.")
    st.info("This log records publication and promotion context. It does not establish paid exposure, measured clicks, streams or conversion. Existing performance exports retain their own account, period and metric definitions.")
    st.download_button("Download content/campaign CSV template", template_bytes(), "content_campaign_log.csv", "text/csv", key="campaign-template")
    with st.expander("CSV field guide and revision rules"):
        st.write("Required: platform, account_id, post_id, revision_timestamp and source_reference. Keep exact platform IDs as text. For non-post events, use a stable manual: ID and an event_type of show, release, playlist or campaign; use Offline only for offline events.")
        st.write("Publication timestamps need an explicit offset and matching IANA publication_timezone, such as America/Los_Angeles. Leave an unknown publication time blank; date-only evidence belongs in notes. revision_timestamp is the time you recorded or corrected this metadata, with an explicit offset.")
        st.write("Unknown metadata stays unknown. Creative tags require tag_status (verified or inferred) and tag_provenance; one status applies to all assigned creative tags in that row. Use inferred if any assigned tag is inferred and explain individual qualifications in notes. Spend is optional and requires a currency code when supplied.")
        st.write("The latest revision_timestamp wins independent of import order. A conflicting row at the same revision time is rejected. New revisions are complete replacements, so carry forward metadata you still know. Original exports and registered analyses are unchanged.")
        st.write("Destination links and UTM tags describe intended tracking. Record observed clicks or landing-page sessions through Import data with the original metric, reporting window and source; a link in this log is not evidence that it was clicked.")
    current = repo.current()
    if current.empty:
        st.info("No content/campaign metadata has been imported. Download the empty template and add source-backed records. Existing post/song references remain available below; no hooks or song assignments are invented.")
    else:
        data = current.copy()
        for field, label in [("platform", "Log platform"), ("campaign_id", "Campaign"), ("tag_status", "Creative tag evidence")]:
            choices = sorted(data[field].unique())
            chosen = st.multiselect(label + " · empty means all", choices, key="campaign-filter-" + field)
            if chosen:
                data = data[data[field].isin(chosen)]
        a, b, c = st.columns(3)
        a.metric("Current log records", len(data))
        b.metric("Known publication timestamps", int(data.publication_timestamp_utc.notna().sum()))
        c.metric("Inferred creative tags", int(data.tag_status.eq("inferred").sum()))
        timeline = data[data.publication_timestamp_utc.notna()].copy()
        if not timeline.empty:
            timeline["publication_utc"] = pd.to_datetime(timeline.publication_timestamp_utc, utc=True)
            fig = px.scatter(timeline, x="publication_utc", y="platform", color="tag_status",
                symbol="event_type", hover_data=["account_id", "post_id", "song_title", "campaign_id", "opening_hook", "publication_timestamp", "publication_timezone"],
                labels={"publication_utc": "Publication/event timestamp · UTC display", "tag_status": "Creative tag evidence"})
            st.plotly_chart(fig, width="stretch", key="campaign-timeline")
            st.caption("Only explicitly timestamped events are plotted. Native publication timestamp and timezone remain in each row; date-only and unknown events are retained in the table. Positions show timing, not estimated effects.")
        st.dataframe(data, hide_index=True, width="stretch")
        st.download_button("Download current log · spreadsheet-safe CSV", export_csv(data), "campaign_log_current.csv", "text/csv", key="campaign-current")
        st.download_button("Download editable current log · template columns", editable_csv(data), "campaign_log_editable.csv", "text/csv", key="campaign-editable")
        st.caption("The editable CSV keeps exact text and template columns for reimport. Edit it as text or import spreadsheet columns as text. Give corrected rows a later revision_timestamp; unchanged rows are safe to reimport.")
        with st.expander("Revision history and source files"):
            history = repo.history()
            st.dataframe(history, hide_index=True, width="stretch")
            st.caption("History can contain multiple source receipts for one revision; it is provenance, not a count of distinct posts or events.")
            hashes = history.source_hash.drop_duplicates().tolist()
            selected = st.selectbox("Original campaign source", hashes,
                format_func=lambda value: str(history.loc[history.source_hash.eq(value), "source_name"].iloc[0]) + " · " + value[:12], key="campaign-source")
            st.download_button("Download unchanged campaign source", repo.source_bytes(selected), "campaign_source_" + selected[:12] + ".csv", "text/csv", key="campaign-original")
    if analysis is not None:
        paths = [path for path in analysis.tables if path.startswith("social/meta_collection/mapping/")
                 or path.endswith("story_song_map.csv") or path.endswith("post_audio_evidence.csv")]
        if paths:
            with st.expander("Existing post/song/event evidence · separate source tables"):
                st.caption("These retained observations have their original qualifications. Caption mentions and candidate matches do not establish verified audio, exposure or attribution. They are not automatically copied into the editable log.")
                path = st.selectbox("Existing mapping evidence", paths, key="campaign-existing")
                st.dataframe(analysis.table(path), hide_index=True, width="stretch")
    st.subheader("Import a metadata revision")
    if principal.role != "admin":
        st.info("Your viewer permission allows browsing and downloads. An approved admin must import campaign metadata.")
        return
    upload = st.file_uploader("Content/campaign CSV · UTF-8, maximum 5 MiB", type=["csv"], key="campaign-upload")
    if upload is None:
        return
    raw = upload.getvalue()
    try:
        preview = parse_campaign_csv(raw)
    except ValueError as exc:
        st.error(str(exc))
        return
    digest = hashlib.sha256(raw).hexdigest()
    st.caption(f"Validated {len(preview):,} source records · SHA-256 {digest}. The import is atomic; equal-time conflicts reject the entire file.")
    st.dataframe(preview, hide_index=True, width="stretch")
    if st.button("Save campaign preview to SQLite", type="primary", key="campaign-save-" + digest):
        try:
            result = repo.import_csv(raw, upload.name, principal)
            st.session_state["campaign-import-notice"] = ("This exact source was already imported; nothing changed." if result["duplicate_import"] else f"Saved {result['added']:,} new metadata revision(s). The log is refreshed below.")
            st.rerun()
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
