"""Read-only display of a separately collected Meta evidence package."""
import hashlib
import pandas as pd
import streamlit as st

from stats_app.analysis_ui_common import download
from stats_app.meta_collection import PREFIX
from stats_app.meta_followup import PREFIX as FOLLOWUP_PREFIX
from stats_app.instagram_audio import PREFIX as AUDIO_PREFIX
from stats_app.instagram_story_owner import PREFIX as OWNER_PREFIX


def _key(repo, suffix):
    return "meta-" + hashlib.sha256(str(repo.db_path).encode()).hexdigest()[:10] + "-" + suffix


def _choice_key(repo, suffix, choices):
    # A dependent filter's available options can change within the same table.
    # Give that new option set fresh state instead of retaining invalid values.
    options_digest = hashlib.sha256(repr(list(choices)).encode()).hexdigest()[:10]
    return _key(repo, suffix + "-" + options_digest)


def _show(repo, path, data, suffix):
    st.dataframe(data, hide_index=True, width="stretch")
    download(data, path.split("/")[-1], _key(repo, suffix + "-filtered"))
    with st.expander("Source table and retained context"):
        st.caption("Source table: " + path + ". Source identity, raw fields, timestamps, reporting bounds and availability remain as supplied.")
        st.download_button("Download unchanged source table", repo.original_bytes(path), path.split("/")[-1],
                           "text/csv", key=_key(repo, suffix + "-original"))


def _filter(data, columns, repo, suffix):
    for column in columns:
        if column not in data:
            continue
        # Filtering does not replace missing source fields. None selects the
        # unknown group explicitly, rather than pretending it is another scope.
        known = sorted(data[column].dropna().astype(str).unique().tolist())
        choices = known + ([None] if data[column].isna().any() else [])
        if len(choices) > 1:
            chosen = st.multiselect(column.replace("_", " ").capitalize() + " · empty means all", choices,
                                    format_func=lambda value: "Unknown / not supplied" if value is None else value,
                                    key=_choice_key(repo, suffix + "-" + column, choices))
            if chosen:
                mask = data[column].astype("string").isin([value for value in chosen if value is not None])
                if None in chosen:
                    mask = mask | data[column].isna()
                data = data[mask]
    return data


def _ads(repo):
    _identity_scope_warning(repo)
    candidates = [path for path in repo.tables if path.startswith(PREFIX) and "ads" in path.rsplit("/", 1)[-1]
                  and "status" not in path and "catalog" not in path]
    st.warning("Ads Manager reporting has its own paid scope, account, currency, attribution settings and delivery levels. Campaign, ad-set and ad totals overlap. Reach, unique audiences and ratios are not additive; no total is manufactured across these rows.")
    if not candidates:
        st.info("No Ads reporting table was retained in this version. Consult collection status for access or export limits; missing spend and delivery are not zero.")
        return
    path = st.selectbox("Ads evidence table", candidates, format_func=lambda value:value.rsplit("/", 1)[-1],
                        key=_key(repo, "ads-table"))
    data = repo.table(path)
    if data.empty:
        st.info("The retained Ads report has no rows. This alone does not establish that all accounts or periods had no advertising.")
    columns = ["ad_account_id", "account_id", "reporting_level", "reporting_timezone", "currency", "attribution_setting",
               "reporting_start", "reporting_end", "metric_platform_scope", "scope", "breakdowns_json", "captured_at_utc", "source_file"]
    data = _filter(data, columns, repo, "ads-" + path)
    st.caption("Values are retained at the selected source grain. A current/lifetime reading is not assigned to a reporting period. Unknown report settings remain unknown, and this view applies no sums.")
    _show(repo, path, data, "ads")


def _identity_scope_warning(repo):
    scope_path = FOLLOWUP_PREFIX + "ad_identity_scope.csv"
    if scope_path not in repo.tables:
        return
    message = "This ad account is mixed-use. Earlier account-wide totals include nonband and unresolved ads. "
    totals_path = FOLLOWUP_PREFIX + "ad_identity_totals.csv"
    if totals_path in repo.tables:
        totals = repo.table(totals_path)
        required = {"source_file", "identity_scope", "spend_usd"}
        if required.issubset(totals.columns):
            selected = totals[totals.source_file.eq("raw/ads_daily_maximum.csv")]
            if not selected.identity_scope.duplicated().any() and {"band", "nonband", "unknown"}.issubset(set(selected.identity_scope)):
                values = selected.set_index("identity_scope").spend_usd
                message += (f"The historical maximum export separates into USD {float(values['band']):,.2f} for band-identified ads, "
                            f"USD {float(values['nonband']):,.2f} for nonband ads and USD {float(values['unknown']):,.2f} with unresolved identities. ")
    message += "See Follow-up evidence → ad_identity_scope.csv. These identity links use current configuration; historical creative revisions remain unavailable."
    st.warning(message)


def _repairs(repo):
    st.info("Newly retained evidence is separate from historical canonical rows. Missing Follows need directly observed daily values; a follower stock or period total cannot fill them. Original malformed Stories and their quarantine remain preserved.")
    candidates = [path for path in repo.tables if path.startswith(PREFIX) and
                  ({"repair", "follows", "stories", "story"} &
                   set(path.rsplit("/", 1)[-1].rsplit(".", 1)[0].split("_")) or
                   path.rsplit("/", 1)[-1].startswith("manual_evidence"))]
    if not candidates:
        st.info("No repair evidence table was supplied. Historical coverage gaps remain unresolved.")
        return
    path = st.selectbox("Repair evidence table", candidates, format_func=lambda value:value.rsplit("/", 1)[-1],
                        key=_key(repo, "repair-table"))
    data = repo.table(path)
    data = _filter(data, ["dataset", "platform_selected", "selected_account_id", "status", "value_status"], repo, "repair-" + path)
    _show(repo, path, data, "repair")


def _mapping(repo):
    st.warning("Caption/link references do not verify audio use, paid exposure, stream conversion or causal effects. A post may reference several songs; bridge rows must never multiply lifetime metrics. Event mentions do not confirm an event occurred.")
    candidates = [path for path in repo.tables if path.startswith(PREFIX + "mapping/")]
    if not candidates:
        st.info("No post/song/event mapping was retained in this version.")
        return
    preferred = PREFIX + "mapping/post_song_references.csv"
    index = candidates.index(preferred) if preferred in candidates else 0
    path = st.selectbox("Mapping evidence table", candidates, index=index,
                        format_func=lambda value:value.rsplit("/", 1)[-1], key=_key(repo, "mapping-table"))
    data = repo.table(path)
    platforms = data.platform_selected.dropna().unique().tolist() if "platform_selected" in data else []
    if platforms:
        chosen = st.multiselect("Mapping platforms · empty means all", platforms,
                                key=_choice_key(repo, "mapping-platforms-" + path, platforms))
        if chosen:
            data = data[data.platform_selected.isin(chosen)]
    for column in ("status", "event_date_status", "event_kind", "song_cardinality"):
        if column in data:
            choices = sorted(data[column].dropna().astype(str).unique())
            chosen = st.multiselect(column.replace("_", " ").capitalize() + " · empty means all", choices,
                                    key=_choice_key(repo, "mapping-" + column + "-" + path, choices))
            if chosen:
                data = data[data[column].astype("string").isin(chosen)]
    st.caption("Unknown mappings remain unknown. Publication/promotion dates and claimed event dates are separate fields; no event year or relative date is invented. JSON originals preserve exact text where CSV export protection adds an apostrophe.")
    _show(repo, path, data, "mapping")


def _followup(repo):
    st.caption("Recent Story song/link evidence and Ads coverage checks are retained as a later collection. Earlier tables remain unchanged.")
    st.warning("A visible song reference or destination URL does not establish an audio match, click, paid delivery or Spotify conversion. An empty report only describes the account, dates and reporting scope actually inspected.")
    status = FOLLOWUP_PREFIX + "collection_status.csv"
    if status in repo.tables:
        _show(repo, status, repo.table(status), "followup-status")
    candidates = [path for path in repo.tables if path.startswith(FOLLOWUP_PREFIX) and path != status]
    if not candidates:
        st.info("No further validated evidence table was supplied. Review collection status for unresolved access or source limits.")
        return
    preferred = FOLLOWUP_PREFIX + "story_song_map.csv"
    if preferred not in candidates:
        preferred = FOLLOWUP_PREFIX + "story_song_mapping.csv"
    index = candidates.index(preferred) if preferred in candidates else 0
    path = st.selectbox("Follow-up evidence table", candidates, index=index,
                        format_func=lambda value: value.removeprefix(FOLLOWUP_PREFIX), key=_key(repo, "followup-table"))
    data = _filter(repo.table(path), ["dataset", "platform_selected", "ad_account_id", "account_id", "post_id",
                   "mapping_status", "status", "value_status", "reporting_start", "reporting_end"], repo, "followup-" + path)
    if path == FOLLOWUP_PREFIX + "story_song_map.csv":
        leading = [column for column in ("published_local", "post_id", "mapping_status", "candidate_song_title",
                                         "audio_use_verified", "visual_evidence") if column in data]
        data = data[leading + [column for column in data if column not in leading]]
    _show(repo, path, data, "followup")


def _instagram_audio(repo):
    st.caption("Later Instagram post inspections are separate from the six retained October Stories and all earlier evidence. Native labels are current at capture; historical audio revisions remain unknown.")
    st.warning("Verified native audio labels apply only to the inspected feed post or Reel. They do not confirm audio on a separate Story, even when imagery or dates look similar. The six Story matches remain unresolved.")
    status = AUDIO_PREFIX + "collection_status.csv"
    if status in repo.tables:
        _show(repo, status, repo.table(status), "instagram-audio-status")
    candidates = [path for path in repo.tables if path.startswith(AUDIO_PREFIX) and path != status]
    if not candidates:
        st.info("No post audio evidence table was supplied in this version.")
        return
    preferred = AUDIO_PREFIX + "post_audio_evidence.csv"
    path = st.selectbox("Instagram audio evidence table", candidates,
                        index=candidates.index(preferred) if preferred in candidates else 0,
                        format_func=lambda value: value.removeprefix(AUDIO_PREFIX), key=_key(repo, "instagram-audio-table"))
    data = _filter(repo.table(path), ["platform_selected", "account_handle", "post_id", "content_kind",
                   "mapping_status", "status", "audio_evidence_status", "native_audio_label_verified", "audio_use_verified"], repo, "instagram-audio-" + path)
    leading = [column for column in ("published_local", "post_id", "content_kind", "native_audio_label",
               "audio_evidence_status", "native_audio_label_verified", "spotify_recording_identity_verified",
               "mapping_status", "audio_use_verified", "assigned_song_id", "source_url") if column in data]
    data = data[leading + [column for column in data if column not in leading]]
    _show(repo, path, data, "instagram-audio")
    st.caption("A title/artist catalog match is a candidate, not verified exact Spotify recording identity. Post evidence is not transferred to Story metrics or Spotify results. No click, stream conversion or causal effect is inferred.")


def _instagram_story_owner(repo):
    stories = repo.table(OWNER_PREFIX + "story_owner_review.csv")
    links = repo.table(OWNER_PREFIX + "story_source_links.csv")
    verified = stories.native_archive_identity_verified.astype(str).str.lower().eq("true").sum()
    songs = stories.audio_use_verified.astype(str).str.lower().eq("true").sum()
    columns = st.columns(3)
    columns[0].metric("Owner Story identities verified", str(verified))
    columns[1].metric("Story songs verified", str(songs))
    columns[2].metric("Source meme post links", str(len(links)))
    st.warning("The six owner archive Stories were inspected, but the web player displayed no native music labels. Their song/audio matches remain unverified. A missing label does not mean no music was used.")
    st.caption("Archive identities were matched using the owner account, calendar date and identical artwork. Archive, public Story and Meta IDs remain separate. Publication dates below retain the earlier export's Pacific time; captures are from October 23.")
    summary = pd.DataFrame({
        "Story date (Pacific)": stories.published_local.astype(str).str[:10],
        "Archive identity": stories.native_archive_identity_verified.astype(str).str.lower().map({"true": "Verified", "false": "Unverified"}),
        "Song audio": stories.audio_use_verified.astype(str).str.lower().map({"true": "Verified", "false": "Unverified"}),
        "Candidate only": stories.candidate_song_title,
        "Source meme post": stories.embedded_source_post_url,
    })
    st.dataframe(summary, hide_index=True, width="stretch",
                 column_config={"Source meme post": st.column_config.LinkColumn("Source meme post")})
    st.info("Four See Post links identify third-party meme provenance. They do not verify the Story soundtrack, Spotify destinations, clicks or conversions. The October 11 The Cut candidate remains unconfirmed.")
    st.caption("Audio listening and fingerprinting were not performed. A media download attempt was unsupported by the browser. A native music label in the mobile archive, or original Story audio with reliable identification, is still needed.")
    with st.expander("Retained owner evidence and provenance"):
        candidates = [path for path in repo.tables if path.startswith(OWNER_PREFIX)]
        preferred = OWNER_PREFIX + "story_owner_review.csv"
        path = st.selectbox("Owner archive evidence table", candidates, index=candidates.index(preferred),
                            format_func=lambda value: value.removeprefix(OWNER_PREFIX), key=_key(repo, "owner-table"))
        _show(repo, path, repo.table(path), "owner")


def render_meta_collection(repo):
    st.subheader("Meta collection")
    st.caption(repo.metadata.get("label", "Separately retained Meta collection"))
    st.caption("Historical Spotify, canonical social inputs and prior statistical results remain unchanged. TikTok access and collection are excluded.")
    _identity_scope_warning(repo)
    path = PREFIX + "collection_status.csv"
    if path not in repo.tables:
        st.info("This analysis version has no additional Meta collection.")
        return
    st.caption("Initial Meta collection coverage · retained source status")
    _show(repo, path, repo.table(path), "status")
    sections = ["Ads history", "Repairs status", "Post/song/event map", "All retained collection tables"]
    if any(path.startswith(FOLLOWUP_PREFIX) for path in repo.tables):
        sections.insert(0, "Follow-up evidence")
    if any(path.startswith(AUDIO_PREFIX) for path in repo.tables):
        sections.insert(0, "Instagram audio review")
    if any(path.startswith(OWNER_PREFIX) for path in repo.tables):
        sections.insert(0, "Instagram owner archive")
    section = st.radio("Collection view", sections,
                       horizontal=True, key=_key(repo, "view"))
    if section == "Instagram owner archive":
        _instagram_story_owner(repo)
    elif section == "Instagram audio review":
        _instagram_audio(repo)
    elif section == "Follow-up evidence":
        _followup(repo)
    elif section == "Ads history":
        _ads(repo)
    elif section == "Repairs status":
        _repairs(repo)
    elif section == "Post/song/event map":
        _mapping(repo)
    else:
        candidates = [path for path in repo.tables if path.startswith(PREFIX)]
        selected = st.selectbox("Collection evidence table", candidates, key=_key(repo, "evidence-table"))
        _show(repo, selected, repo.table(selected), "evidence")
    lineage = repo.metadata.get("input_lineage", {})
    st.info("Prior statistical results remain pinned to " + str(lineage.get("statistical_results", "their original input version"))
            + ". This collection does not add a new significance test or establish paid/social-to-streaming attribution.")
