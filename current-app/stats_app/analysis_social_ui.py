"""Social presentation over immutable cleaned analysis tables."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from stats_app.dashboard_controls import selectbox, radio, multiselect, date_range
from stats_app.analysis_content_ui import render_content_library
from stats_app.analysis_content import (
    CONTENT_PATH, conflicting_publication_identities, content_identity_inventory,
    load_content_observations, publication_inventory, search_content,
)
from stats_app.content_summaries import content_coverage, latest_summary_observations

from stats_app.analysis_social_metrics import (
    ADDITIVE, compare_daily, daily_grid, filtered_csv, prepare_daily, prepare_posts, publication_series, truth,
    canonical_social_series,
)


def _title(value):
    return str(value).replace("_", " ").capitalize()


def _number(value):
    return "Unavailable" if value is None or pd.isna(value) else f"{value:,.2f}".rstrip("0").rstrip(".")


def _table(repo, path):
    return repo.table(path) if path in repo.tables else pd.DataFrame()


def _download(data, name, key):
    st.download_button("Download filtered records · CSV", filtered_csv(data), name, "text/csv", key=key)


def _evidence(repo, data, path, key):
    with st.expander("Records, source lineage and definitions"):
        st.caption(f"Source table: {path}. Native source files, record numbers, reporting bounds and retrieval timestamps remain attached to these rows.")
        st.dataframe(data, hide_index=True, width="stretch")
        _download(data, path.rsplit("/", 1)[-1], key + "-records")
        st.download_button("Download unchanged source table", repo.original_bytes(path), path.rsplit("/", 1)[-1],
                           "text/csv", key=key + "-original")
        if "snapshot_timestamp" in data:
            timestamps = sorted(data.snapshot_timestamp.dropna().astype(str).unique())
            st.caption("Retrieval timestamp(s), UTC: " + ("; ".join(timestamps) if timestamps else "Unknown"))
        dictionary = _table(repo, "social/data_dictionary.csv")
        if not dictionary.empty:
            table_name = path.rsplit("/", 1)[-1].removesuffix(".csv")
            selected = dictionary[dictionary.table.isin([table_name, "shared/post tables"])]
            if "metric" in data and table_name == "account_daily":
                selected = selected[selected.field.isin([*data.metric.unique(), "value_status", "snapshot_timestamp",
                    "metric_platform_scope", "date", "partial_day", "source_file/source_record"])]
            st.dataframe(selected, hide_index=True, width="stretch")


def _activity(repo, platform):
    if "social/account_daily.csv" not in repo.tables:
        st.info("Account activity is unavailable. The canonical social/account_daily.csv export is needed.")
        return
    selected_sources = []
    for source_path, source_data in canonical_social_series(repo):
        selected_sources.append(source_data.assign(selected_source_table=source_path))
    data = pd.concat(selected_sources, ignore_index=True)
    if data.empty:
        st.info("Account activity is unavailable. The canonical social/account_daily.csv export is needed.")
        return
    data = data.loc[data.platform_selected.eq(platform)].copy()
    account = selectbox("Selected social account", data.selected_account_id.unique().tolist(), key="social-activity-account")
    data = data[data.selected_account_id.eq(account)]
    metrics = sorted(data.metric.unique())
    metric = selectbox("Social activity metric", metrics, index=metrics.index("views") if "views" in metrics else 0,
                          format_func=_title, key="social-activity-metric")
    data = data[data.metric.eq(metric)]
    vintage = selectbox("Activity evidence", data.snapshot_class.unique().tolist(),
                          format_func=lambda value: "Reviewed daily follows repair" if value == "reviewed_follows_repair_canonical_selection" else "Inherited daily export",
                          key="social-activity-vintage")
    data = data[data.snapshot_class.eq(vintage)]
    scope = selectbox("Measured platform scope", data.metric_platform_scope.unique().tolist(), key="social-activity-scope")
    data = data[data.metric_platform_scope.eq(scope)].copy()
    paths = data.selected_source_table.unique().tolist()
    if len(paths) != 1:
        raise ValueError("Select one source table before comparing daily activity.")
    path = paths[0]
    if path.endswith("follows_daily_resolved.csv"):
        st.info("Reviewed daily evidence replaces the inherited Instagram follows gaps in this view. Follows are gross follow events, not net follower growth; historical statistical inputs remain unchanged.")
    if "combined" in scope.lower():
        st.info("These Views measure Facebook and Instagram combined. Standalone Facebook Page views are a different scope; do not add them or subtract them to manufacture Instagram-only daily views.")
    include_partial = st.checkbox("Include partial source days", value=False, key="social-partial")
    eligible = data if include_partial else data.loc[~data.partial_day]
    if eligible.empty:
        st.info("No complete source days are available for this selection.")
        return
    first, latest = date.fromisoformat(eligible.date.min()), date.fromisoformat(eligible.date.max())
    window = radio("Activity window", ["Latest 28 days", "Latest 90 days", "All available", "Custom"],
                      horizontal=True, key="social-window")
    days = {"Latest 28 days": 28, "Latest 90 days": 90}.get(window)
    start, end = max(first, latest - timedelta(days=days - 1)) if days else first, latest
    if window == "Custom":
        selected = date_range("Social reporting dates", first, latest, (start, end), key="social-dates")
        if selected is None:
            return
        start, end = selected
    comparison = compare_daily(data, start.isoformat(), end.isoformat())
    current, previous = comparison["current"], comparison["previous"]
    st.caption(f"{start:%b %d, %Y} – {end:%b %d, %Y} · native Pacific source dates · count · {scope}")
    st.caption("Source retrieval timestamps remain attached to the records. Activity through October 20 does not backdate these snapshots. Aggregated Pacific dates are not shifted to UTC.")
    if data.reporting_timezone.isna().any() or data.reporting_timezone.fillna("").eq("").any():
        st.caption("Some source rows omit timezone metadata. The delivered canonical table contract specifies Pacific dates; those original blank source fields remain unchanged in the evidence.")
    cards = st.columns(3)
    cards[0].metric("Period activity" if metric in ADDITIVE else "Period unique audience", _number(current.total))
    cards[1].metric("Observed dates / selected dates", f"{current.observed_days} / {current.calendar_days}")
    cards[2].metric("Median observed daily value", _number(current.median_daily))
    st.caption(current.reason + " Daily medians exclude missing dates.")
    if current.missing_days:
        st.warning(f"Coverage gap: {current.missing_days} selected date(s) are missing. No full-period total or comparison is inferred.")
    if current.partial_days:
        st.warning("Partial-period view: October 21 was incomplete at retrieval. Complete-window comparisons are disabled.")
    if comparison["delta"] is not None:
        delta_text = f"{comparison['percent_change']:+.1f}%" if comparison["percent_change"] is not None else "Percentage unavailable from a zero prior value"
        st.write(f"Previous equal window, {previous.start} – {previous.end}: **{_number(previous.total)}**. "
                 f"Change: **{_number(comparison['delta'])}** ({delta_text}).")
    else:
        st.caption(f"Previous equal window: {previous.start} – {previous.end}; {previous.observed_days}/{previous.calendar_days} observed dates. {comparison['reason']}")
    grid = daily_grid(data, start.isoformat(), end.isoformat())
    fig = go.Figure(go.Scatter(x=grid.date, y=grid.value, mode="lines", connectgaps=False,
                              name=_title(metric), line={"color": "#D7BA65", "width": 2},
                              customdata=grid.value_status, hovertemplate="%{x}<br>%{y:,.2f}<br>%{customdata}<extra></extra>"))
    fig.update_layout(height=350, title=f"Daily {_title(metric).lower()} · {scope}",
                      xaxis_title="Native Pacific reporting date", yaxis_title="Count", margin={"l": 10, "r": 10, "t": 55, "b": 10})
    st.plotly_chart(fig, width="stretch", key="social-activity-chart")
    selected = data.loc[data.date.between(start.isoformat(), end.isoformat())]
    _evidence(repo, selected, path, "social-activity")
    with st.expander("Audited historical comparisons and methods"):
        audited = _table(repo, "social/account_period_comparisons.csv")
        if not audited.empty:
            audited = audited[audited.platform_selected.eq(platform) & audited.metric.eq(metric)
                              & audited.metric_platform_scope.eq(scope)]
            st.caption("Historical delivered results use the inherited source version, before separately reviewed repairs. They are retained evidence and may differ from the current selection above. Daily unique audiences are never summed.")
            st.dataframe(audited, hide_index=True, width="stretch")
        st.caption("The dashboard follows code/social_pipeline.py: sum only complete additive daily intervals, compare adjacent equal windows, retain nulls, and exclude partial days by default.")


def _legacy_content(repo, platform):
    path = "social/posts_latest.csv"
    data = prepare_posts(_table(repo, path))
    if data.empty:
        st.info("Content snapshots are unavailable. The verified social/posts_latest.csv table is needed.")
        return
    data = data[data.platform_selected.eq(platform)]
    st.info("Lifetime as captured October 22 UTC. Publication dates select content; they do not identify when lifetime views or engagement occurred. Post ages differ, so this view cannot establish fixed-age format winners.")
    authors = sorted(data.author_scope.dropna().unique())
    selected_authors = multiselect("Content author scope", authors, default=["band_authored"] if "band_authored" in authors else [],
                                     format_func=_title, key="social-authors")
    types = sorted(data.post_type.dropna().unique())
    selected_types = multiselect("Post formats", types, default=[kind for kind in types if "story" not in kind.lower()], key="social-formats")
    data = data[data.author_scope.isin(selected_authors) & data.post_type.isin(selected_types)].copy()
    query = st.text_input("Find a post · caption, ID or link", value=st.session_state.get("selection:social-content-search", ""), key="social-content-search").strip()
    st.session_state["selection:social-content-search"] = query
    if data.empty:
        st.info("No retained posts match the selected author scopes and formats.")
        return
    first = date.fromisoformat(data.publication_date.min())
    end = date.fromisoformat(data.publication_date.max())
    population_key = platform + "|" + ",".join(sorted(selected_authors)) + "|" + ",".join(sorted(selected_types))
    selected = date_range("Publication date range", first, date.fromisoformat(data.publication_date.max()), (first, end),
                          key="social-publications-" + population_key)
    if selected is None:
        return
    data = data[data.publication_date.between(selected[0].isoformat(), selected[1].isoformat())]
    if data.empty:
        st.info("No retained publications match this date range. Missing inventory is not proof of zero publishing.")
        return
    max_age = max(1, int(pd.to_numeric(data.post_age_days, errors="coerce").max()) + 1)
    age = st.slider("Post age at capture · days", 0, max_age, (0, max_age),
                    key="social-age-" + population_key + "|" + str(selected))
    data = data[data.post_age_days.between(*age)]
    if data.empty:
        st.info("No retained posts match the selected age range.")
        return
    # Search intersects the selected population, dates and ages. It must not
    # redefine widget bounds or overwrite the user's remembered filters.
    if query:
        text_columns = [column for column in data if any(token in column.lower() for token in ("caption", "description", "title", "permalink")) or column == "post_id"]
        matches = pd.Series(False, index=data.index)
        for column in text_columns:
            matches |= data[column].astype("string").str.contains(query, case=False, regex=False, na=False)
        data = data.loc[matches]
        if data.empty:
            st.info("No retained posts match this search within the selected date and age filters. Clear the search to restore those results.")
            return
    if data.post_type.str.contains("story", case=False).any():
        st.warning("In this saved inherited version, 183 malformed records are quarantined as Story evidence. Its 126 valid retained Stories are a selected subset, not the full Story history; later versions retain separately recovered and expanded evidence.")
        with st.expander("Quarantined Story evidence"):
            quarantined = _table(repo, "social/excluded_records.csv")
            st.dataframe(quarantined, hide_index=True, width="stretch")
            _download(quarantined, "quarantined_stories.csv", "social-quarantine")
    cards = st.columns(3)
    cards[0].metric("Retained publications", f"{len(data):,}")
    cards[1].metric("Median post age at capture · days", _number(data.post_age_days.median()))
    cards[2].metric("Author populations selected", data.author_scope.nunique())
    st.caption("Counts describe captured publication inventory; deleted or omitted content is unknown. Paid exposure and creative/song mappings are not established for every post.")
    cadence = publication_series(data)
    fig = px.bar(cadence, x="publication_date", y="retained_posts", color="post_type", labels={
        "publication_date": "Publication date · Pacific", "retained_posts": "Retained publications", "post_type": "Format"},
        title="Publishing frequency · retained publication events only")
    fig.update_layout(height=330, margin={"l": 10, "r": 10, "t": 55, "b": 10})
    st.plotly_chart(fig, width="stretch", key="social-publication-chart")
    st.caption("Source: social/posts_latest.csv. This chart counts unique platform/post IDs; no lifetime performance is allocated to a publication day.")
    metric = selectbox("Lifetime metric by post age", ["views", "reach", "engagement_actions"], format_func=_title, key="social-post-metric")
    observed = data[data[metric].notna()]
    if observed.empty:
        st.info("This lifetime metric was not supplied for the selected posts.")
    else:
        fig = px.scatter(observed, x="post_age_days", y=metric, color="post_type", hover_data=["post_id", "author_scope", "publication_date"],
                         labels={"post_age_days": "Age at capture · days", metric: "Lifetime " + _title(metric).lower(), "post_type": "Format"},
                         title="Lifetime outcomes at unequal post ages")
        fig.update_layout(height=350)
        st.plotly_chart(fig, width="stretch", key="social-lifetime-chart")
    columns = ["post_id", "author_scope", "author_account_id", "post_type", "publication_date", "post_age_days",
               "views", "reach", "engagement_actions", "snapshot_timestamp", "permalink"]
    st.dataframe(data[[column for column in columns if column in data]].sort_values("publication_date", ascending=False), hide_index=True, width="stretch",
                 column_config={"permalink": st.column_config.LinkColumn("Open source post", display_text="Open post")})
    _evidence(repo, data, path, "social-content")


def _content(repo, platform):
    # Saved pre-expansion versions retain their original population and controls.
    if CONTENT_PATH not in repo.tables:
        return _legacy_content(repo, platform)
    observations = load_content_observations(repo)
    observations = observations.loc[observations.platform_selected.eq(platform)].copy()
    if observations.empty:
        st.info("No retained content observations exist for this platform in the selected analysis version.")
        return
    coverage = content_coverage(observations)
    # Establish newest observations and unresolved conflict statuses from the
    # full platform history. Presentation filters must never promote an older
    # matching caption/author/date or resolve a same-time disagreement.
    latest = latest_summary_observations(observations)
    st.caption(f"Retained {platform} library: {coverage['identities']:,} distinct content identities · {coverage['stories']:,} Stories · {coverage['retained_observations']:,} captures. Inventory is not proof of complete account history.")
    authors = sorted(observations.author_scope.unique())
    selected_authors = multiselect("Content author scope", authors, default=authors, format_func=_title, key="social-authors-expanded")
    types = sorted(observations.post_type.unique())
    selected_types = multiselect("Post formats", types, default=types, key="social-formats-expanded")
    selected = observations.loc[observations.author_scope.isin(selected_authors) & observations.post_type.isin(selected_types)].copy()
    query = st.text_input("Find a post · caption, ID or link", value=st.session_state.get("selection:social-content-search", ""), key="social-content-search").strip()
    st.session_state["selection:social-content-search"] = query
    if selected.empty:
        st.info("No retained posts match the selected author scopes and formats.")
        return
    # Conflict detection uses all retained captures, not just the newest row or
    # the date-filtered population. A filter cannot resolve disputed evidence.
    conflicts = conflicting_publication_identities(observations)
    known = selected.loc[selected.publication_date.ne("")]
    if not known.empty:
        first, last = date.fromisoformat(known.publication_date.min()), date.fromisoformat(known.publication_date.max())
        population_key = platform + "|" + ",".join(selected_authors) + "|" + ",".join(selected_types)
        period = date_range("Publication date range", first, last, (first, last), key="social-publications-expanded-" + population_key)
        if period is None:
            return
        include_undated = st.checkbox("Include undated captures", value=True, key="social-content-undated")
        selected = selected.loc[selected.publication_date.between(period[0].isoformat(), period[1].isoformat()) |
                                (include_undated & selected.publication_date.eq(""))]
    selected = search_content(selected, query)
    if selected.empty:
        st.info("No retained posts match this search within the selected publication filters. Clear the search to restore those results.")
        return
    inventory = content_identity_inventory(selected.loc[selected.identity_complete], observations)
    cards = st.columns(3)
    cards[0].metric("Distinct content identities", f"{len(inventory):,}")
    cards[1].metric("Stories in selected inventory", f"{selected.loc[selected.identity_complete & selected.post_type.str.contains('story', case=False), 'identity_key'].nunique():,}")
    cards[2].metric("Selected capture observations", f"{len(selected):,}")
    date_conflicts = conflicts.intersection(selected.identity_key)
    if date_conflicts:
        st.warning(f"{len(date_conflicts)} selected identities retain conflicting publication dates. They remain visible and are excluded from publishing frequency.")
    cadence = publication_inventory(selected.loc[~selected.identity_key.isin(conflicts)])
    if not cadence.empty:
        fig = px.bar(cadence, x="publication_date", y="retained_publications", color="post_type", labels={
            "publication_date": "Source publication date", "retained_publications": "Retained publications", "post_type": "Format"},
            title="Publishing frequency · distinct retained identities")
        fig.update_layout(height=330, margin={"l": 10, "r": 10, "t": 55, "b": 10})
        st.plotly_chart(fig, width="stretch", key="social-publication-chart")
    st.caption("One platform/account/post identity contributes at most once. Unknown and conflicting dates are excluded from this chart; source calendar dates are not shifted to a common timezone.")
    st.dataframe(inventory.drop(columns=["identity_key"]), hide_index=True, width="stretch",
                 column_config={"permalink": st.column_config.LinkColumn("Open source post", display_text="Open post"),
                                "description": st.column_config.TextColumn("Post text", width="large")})
    st.download_button("Download filtered post inventory · CSV", filtered_csv(inventory), "social_content_inventory.csv", "text/csv", key="social-content-inventory-download")
    with st.expander("Captured outcomes by age and scope"):
        _content_outcomes(latest.loc[latest.observation_id.isin(selected.observation_id)].copy(), conflicts)
    with st.expander("Source lineage and retained evidence"):
        _download(selected, "social_content_all_captures.csv", "social-content-all-records")
        columns = ["platform_selected", "identity_account_id_type", "identity_account_id", "post_id", "metric_platform_scope", "measurement_type", "author_scope", "source_table", "source_file", "source_sha256", "source_record", "snapshot_timestamp"]
        st.dataframe(selected[columns], hide_index=True, width="stretch")
        for path in sorted(selected.source_table.unique()):
            st.download_button("Download unchanged " + path.rsplit("/", 1)[-1], repo.original_bytes(path), path.rsplit("/", 1)[-1], "text/csv", key="social-content-original-" + path)
        st.caption("Original malformed export rows remain retained and quarantined. Later native and recovered observations expand the inventory; this summary does not claim the earlier quarantine is the remaining Story count.")


def _content_outcomes(data, conflicts):
    if data.empty:
        st.info("No latest captures match these presentation filters. Older matching captures remain in retained evidence; they are not promoted to latest outcomes.")
        return
    accounts = data.apply(lambda row: f"{row.identity_account_id_type} · {row.identity_account_id}", axis=1)
    account = selectbox("Content account", sorted(accounts.unique()), key="social-content-account")
    data = data.loc[accounts.eq(account)]
    scope = selectbox("Captured metric scope", sorted(data.metric_platform_scope.unique()), key="social-content-scope")
    data = data.loc[data.metric_platform_scope.eq(scope)]
    measurements = sorted(data.measurement_type.unique())
    measurement = selectbox("Content measurement type", measurements, index=measurements.index("lifetime_content_snapshot") if "lifetime_content_snapshot" in measurements else 0, key="social-content-measurement")
    data = data.loc[data.measurement_type.eq(measurement)]
    cohorts = sorted((value for value in data.capture_cohort.unique() if value != "Unknown capture time"), reverse=True)
    if data.capture_cohort.eq("Unknown capture time").any():
        cohorts.append("Unknown capture time")
    cohort = selectbox("Capture cohort", cohorts, key="social-content-cohort")
    data = data.loc[data.capture_cohort.eq(cohort)]
    unknown = ~data.selection_status.eq("latest_compatible_capture") | ~data.identity_complete
    if unknown.any():
        st.caption(f"{data.loc[unknown, 'identity_key'].nunique():,} identities have unresolved identity or capture chronology; their metrics are excluded from this outcome view.")
    data = data.loc[~unknown & ~data.identity_key.duplicated(keep=False)].copy()
    metric = selectbox("Lifetime metric by post age", ["views", "reach", "interactions", "engagement_actions", "link_clicks"], format_func=_title, key="social-post-metric")
    st.caption("Latest compatible observation per identity within this metric scope and measurement type. UTC capture-day cohorts stay separate; lifetime values are never added across captures or assigned to publication-day activity. Ages/exposure differ.")
    observed = data.loc[data[metric].notna() & data.post_age_days.notna() & ~data.identity_key.isin(conflicts)]
    if observed.empty:
        st.info("No observations supply both this outcome and a supported post age. Available metrics remain in the capture records below; missing ages are not inferred from unlabelled timezones.")
    else:
        fig = px.scatter(observed, x="post_age_days", y=metric, color="post_type", hover_data=["post_id", "author_scope", "publication_date"],
                         labels={"post_age_days": "Age at capture · days", metric: "Captured " + _title(metric).lower(), "post_type": "Format"}, title="Captured outcomes at unequal post ages")
        fig.update_layout(height=350)
        st.plotly_chart(fig, width="stretch", key="social-lifetime-chart")
    st.dataframe(data.drop(columns=["capture_time_utc"]), hide_index=True, width="stretch")
    _download(data, "social_content_captures.csv", "social-content-records")


def _audience(repo, platform):
    path = "social/audience_snapshots.csv"
    data = _table(repo, path)
    if data.empty:
        st.info("Audience distributions are unavailable. Native audience snapshot exports are needed.")
        return
    data = data[data.platform_selected.eq(platform)].copy()
    st.info("Lifetime-labelled follower distribution, captured October 22 UTC. Percentages retain source display precision. Top countries and cities are not an exhaustive partition; no follower counts are reconstructed.")
    dimension = selectbox("Audience distribution", data.dimension.unique().tolist(), key="social-audience-dimension")
    data = data[data.dimension.eq(dimension)].copy()
    snapshots = data.snapshot_timestamp.dropna().unique().tolist()
    if len(snapshots) > 1:
        chosen = selectbox("Audience retrieval", snapshots, key="social-audience-snapshot")
        data = data[data.snapshot_timestamp.eq(chosen)]
    data["value"] = pd.to_numeric(data.value, errors="coerce")
    data.loc[~data.value_status.isin(["observed", "observed_zero"]), "value"] = float("nan")
    fig = px.bar(data, x="category", y="value", color="subgroup" if data.subgroup.fillna("").ne("").any() else None,
                 barmode="group", labels={"category": "Reported category", "value": "Displayed percent", "subgroup": "Subgroup"},
                 title=f"{platform} · {dimension}")
    fig.update_layout(height=380)
    st.plotly_chart(fig, width="stretch", key="social-audience-chart")
    _evidence(repo, data, path, "social-audience")


def _native_evidence(repo, platform):
    path = "social/manual_period_and_current_snapshots.csv"
    data = _table(repo, path)
    if data.empty:
        st.info("No native period summaries or follower-stock snapshots are available.")
        return
    data = data[data.platform_selected.eq(platform)]
    st.info("Native period readings, follower stocks and rounded displays remain separate evidence. A stock is not new-follower activity; rounded text is not an exact count. Unknown windows stay unknown.")
    metrics = multiselect("Native snapshot metrics", sorted(data.metric.unique()), key="social-native-metrics")
    if metrics:
        data = data[data.metric.isin(metrics)]
    _evidence(repo, data, path, "social-native")


def render_social(repo):
    st.subheader("Facebook & Instagram")
    st.caption("[REDACTED] / @redactedbandoh · retained Meta evidence with individual capture dates · local analysis")
    section = radio("Social view", ["Collected posts & Stories", "Account activity", "Content & publishing", "Audience distribution", "Native period & stock evidence"],
                       horizontal=True, key="analysis-social-view")
    if section == "Collected posts & Stories":
        render_content_library(repo)
        return
    platform = selectbox("Social platform", ["Instagram", "Facebook", "TikTok"], key="analysis-social-platform")
    if platform == "TikTok":
        st.info("TikTok data unavailable in this saved analysis. Open TikTok in Explore for the current collection checklist and preparation status. New collection work does not change this historical package.")
        return
    renderers = {"Account activity": _activity, "Content & publishing": _content,
                 "Audience distribution": _audience, "Native period & stock evidence": _native_evidence}
    try:
        renderers[section](repo, platform)
    except ValueError as exc:
        st.error(f"This selection cannot be calculated safely: {exc}")
