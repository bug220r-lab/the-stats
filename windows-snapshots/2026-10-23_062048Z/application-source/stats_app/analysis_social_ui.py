"""Social presentation over immutable cleaned analysis tables."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from stats_app.analysis_social_metrics import (
    ADDITIVE, compare_daily, daily_grid, filtered_csv, prepare_daily, prepare_posts, publication_series, truth,
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
    path = "social/account_daily.csv"
    data = prepare_daily(_table(repo, path))
    if data.empty:
        st.info("Account activity is unavailable. The canonical social/account_daily.csv export is needed.")
        return
    data = data.loc[data.platform_selected.eq(platform)].copy()
    account = st.selectbox("Selected social account", data.selected_account_id.unique().tolist(), key="social-activity-account")
    data = data[data.selected_account_id.eq(account)]
    vintage = st.selectbox("Activity snapshot class", data.snapshot_class.unique().tolist(), key="social-activity-vintage")
    data = data[data.snapshot_class.eq(vintage)]
    metrics = sorted(data.metric.unique())
    metric = st.selectbox("Social activity metric", metrics, index=metrics.index("views") if "views" in metrics else 0,
                          format_func=_title, key="social-activity-metric")
    data = data[data.metric.eq(metric)]
    scope = st.selectbox("Measured platform scope", data.metric_platform_scope.unique().tolist(), key="social-activity-scope")
    data = data[data.metric_platform_scope.eq(scope)].copy()
    if "combined" in scope.lower():
        st.info("These Views measure Facebook and Instagram combined. Standalone Facebook Page views are a different scope; do not add them or subtract them to manufacture Instagram-only daily views.")
    include_partial = st.checkbox("Include partial source days", value=False, key="social-partial")
    eligible = data if include_partial else data.loc[~data.partial_day]
    if eligible.empty:
        st.info("No complete source days are available for this selection.")
        return
    first, latest = date.fromisoformat(eligible.date.min()), date.fromisoformat(eligible.date.max())
    window = st.radio("Activity window", ["Latest 28 days", "Latest 90 days", "All available", "Custom"],
                      horizontal=True, key="social-window")
    days = {"Latest 28 days": 28, "Latest 90 days": 90}.get(window)
    start, end = max(first, latest - timedelta(days=days - 1)) if days else first, latest
    if window == "Custom":
        selected = st.date_input("Social reporting dates", (start, end), min_value=first, max_value=latest, key="social-dates")
        if len(selected) != 2:
            st.info("Select both reporting dates.")
            return
        start, end = selected
    comparison = compare_daily(data, start.isoformat(), end.isoformat())
    current, previous = comparison["current"], comparison["previous"]
    st.caption(f"{start:%b %d, %Y} – {end:%b %d, %Y} · native Pacific source dates · count · {scope}")
    st.caption("October 22 UTC retrievals are later supplements. Activity through October 20 does not backdate these snapshots. Aggregated Pacific dates are not shifted to UTC.")
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
            st.caption("Delivered descriptive results. Empty period totals remain unavailable; daily unique audiences are not summed. No sampling p-value or causal marketing effect is implied.")
            st.dataframe(audited, hide_index=True, width="stretch")
        st.caption("The dashboard follows code/social_pipeline.py: sum only complete additive daily intervals, compare adjacent equal windows, retain nulls, and exclude partial days by default.")


def _content(repo, platform):
    path = "social/posts_latest.csv"
    data = prepare_posts(_table(repo, path))
    if data.empty:
        st.info("Content snapshots are unavailable. The verified social/posts_latest.csv table is needed.")
        return
    data = data[data.platform_selected.eq(platform)]
    st.info("Lifetime as captured October 22 UTC. Publication dates select content; they do not identify when lifetime views or engagement occurred. Post ages differ, so this view cannot establish fixed-age format winners.")
    authors = sorted(data.author_scope.dropna().unique())
    selected_authors = st.multiselect("Content author scope", authors, default=["band_authored"] if "band_authored" in authors else [],
                                     format_func=_title, key="social-authors")
    types = sorted(data.post_type.dropna().unique())
    selected_types = st.multiselect("Post formats", types, default=[kind for kind in types if "story" not in kind.lower()], key="social-formats")
    data = data[data.author_scope.isin(selected_authors) & data.post_type.isin(selected_types)].copy()
    if data.empty:
        st.info("No retained posts match the selected author scopes and formats.")
        return
    first = date.fromisoformat(data.publication_date.min())
    end = min(date.fromisoformat(data.publication_date.max()), date(2026, 10, 20))
    population_key = platform + "|" + ",".join(sorted(selected_authors)) + "|" + ",".join(sorted(selected_types))
    selected = st.date_input("Publication date range", (first, end), min_value=first,
                             max_value=date.fromisoformat(data.publication_date.max()), key="social-publications-" + population_key)
    if len(selected) != 2:
        st.info("Select both publication dates.")
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
    if data.post_type.str.contains("story", case=False).any():
        st.warning("Stories are incomplete: 183 malformed records are quarantined. The 126 valid retained Stories are a selected subset, not the full Story history.")
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
    metric = st.selectbox("Lifetime metric by post age", ["views", "reach", "engagement_actions"], format_func=_title, key="social-post-metric")
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
    st.dataframe(data[[column for column in columns if column in data]].sort_values("publication_date", ascending=False), hide_index=True, width="stretch")
    _evidence(repo, data, path, "social-content")


def _audience(repo, platform):
    path = "social/audience_snapshots.csv"
    data = _table(repo, path)
    if data.empty:
        st.info("Audience distributions are unavailable. Native audience snapshot exports are needed.")
        return
    data = data[data.platform_selected.eq(platform)].copy()
    st.info("Lifetime-labelled follower distribution, captured October 22 UTC. Percentages retain source display precision. Top countries and cities are not an exhaustive partition; no follower counts are reconstructed.")
    dimension = st.selectbox("Audience distribution", data.dimension.unique().tolist(), key="social-audience-dimension")
    data = data[data.dimension.eq(dimension)].copy()
    snapshots = data.snapshot_timestamp.dropna().unique().tolist()
    if len(snapshots) > 1:
        chosen = st.selectbox("Audience retrieval", snapshots, key="social-audience-snapshot")
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
    metrics = st.multiselect("Native snapshot metrics", sorted(data.metric.unique()), key="social-native-metrics")
    if metrics:
        data = data[data.metric.isin(metrics)]
    _evidence(repo, data, path, "social-native")


def render_social(repo):
    st.subheader("Facebook & Instagram")
    st.caption("[REDACTED] / @redactedbandoh · October 22, 2026 retained Meta exports · local analysis, not live analytics")
    platform = st.selectbox("Social platform", ["Instagram", "Facebook", "TikTok"], key="analysis-social-platform")
    if platform == "TikTok":
        st.info("TikTok data unavailable. No verified analytics identity or collected analytics exists in this package. Access and collection remain deferred at your request.")
        return
    section = st.radio("Social view", ["Account activity", "Content & publishing", "Audience distribution", "Native period & stock evidence"],
                       horizontal=True, key="analysis-social-view")
    renderers = {"Account activity": _activity, "Content & publishing": _content,
                 "Audience distribution": _audience, "Native period & stock evidence": _native_evidence}
    try:
        renderers[section](repo, platform)
    except ValueError as exc:
        st.error(f"This selection cannot be calculated safely: {exc}")
