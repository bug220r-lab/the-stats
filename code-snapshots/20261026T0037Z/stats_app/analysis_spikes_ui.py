"""Select a Spotify increase and inspect source-qualified surrounding content."""
from datetime import date, timedelta
from hashlib import sha256
from urllib.parse import urlsplit

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from stats_app import dashboard_controls as controls
from stats_app.analysis_correlation import _observed
from stats_app.analysis_social_metrics import filtered_csv
from stats_app.analysis_spikes import rank_spotify_increases, publications_around_week, publication_capture_context
from stats_app.analysis_ui_common import chart, fmt

OUTCOMES = {"streams": "Streams", "mean_daily_listeners": "Average daily listeners"}
CONTENT_TYPES = {"facebook_posts": "Facebook posts", "instagram_stories": "Instagram Stories",
                 "instagram_feed": "Instagram feed posts"}
WINDOWS = {"Previous week + spike week": (1, 0), "Spike week only": (0, 0),
           "Previous + spike + following week": (1, 1)}
SPOTIFY_SOURCE = "spotify/cleaned/artist_daily.csv"
CAPTION_EVIDENCE_LABELS = {
    "native_no_text": "Native panel reports no text",
    "native_text_present": "Native panel text retained",
    "native_text_reported_but_not_retained": "Native text reported; text not retained",
    "conflicting_native_caption_evidence": "Native text status conflicts with retained caption",
    "retained_source_text": "Retained source text",
    "not_collected_or_unavailable": "Text not collected or unavailable",
}


def _shift(day, days):
    return pd.Timestamp(pd.Timestamp(day).date() + timedelta(days=days))


def _csv(label, frame, filename, key):
    st.download_button(label, filtered_csv(frame), filename, "text/csv", key=key)


def source_links(value):
    """One ordinary platform permalink per action; never a joined URL or embed."""
    links = []
    for candidate in str(value or "").splitlines():
        candidate = candidate.strip()
        try:
            parsed = urlsplit(candidate)
            valid = (parsed.scheme == "https" and parsed.hostname in {
                "facebook.com", "www.facebook.com", "m.facebook.com",
                "instagram.com", "www.instagram.com"} and not parsed.username
                and not parsed.password and parsed.port in {None, 443}
                and not any(c.isspace() for c in candidate))
        except ValueError:
            valid = False
        if valid and candidate not in links:
            links.append(candidate)
    return links


def ranking_figure(ranked, outcome, selected_week, limit=5):
    shown = ranked.head(limit)
    dates = pd.to_datetime(shown.week_start).dt.strftime("%Y-%m-%d")
    digits = 0 if outcome == "streams" else 1
    fig = go.Figure(go.Bar(
        x=shown.increase, y=pd.to_datetime(shown.week_start).dt.strftime("%b %d, %Y"),
        orientation="h", marker_color=["#6FD6AE" if d == selected_week else "#79AFFF" for d in dates],
        customdata=list(zip(dates, shown.prior, shown.current)),
        text=[f"+{v:,.{digits}f}" for v in shown.increase], textposition="auto",
        insidetextfont=dict(color="#142235", size=13), outsidetextfont=dict(color="#F5F4EE", size=13),
        hovertemplate="Week of %{customdata[0]}<br>Previous: %{customdata[1]:,.1f}<br>Selected: %{customdata[2]:,.1f}<br>Increase: %{x:,.1f}<extra></extra>",
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1))))
    fig.update_layout(height=max(150, 30 * len(shown) + 65), clickmode="event+select",
                      dragmode=False, margin=dict(t=10, l=10, r=20, b=30),
                      xaxis_title="Additional " + OUTCOMES[outcome].lower() + " vs previous week",
                      yaxis=dict(autorange="reversed", fixedrange=True),
                      xaxis=dict(rangemode="tozero", fixedrange=True), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _choose_bar(key, allowed):
    points = st.session_state.get(key, {}).get("selection", {}).get("points", [])
    if points:
        custom = points[-1].get("customdata", [])
        if custom and custom[0] in allowed:
            st.session_state["selection:spikes:week"] = custom[0]


def _toggle_ranking():
    key = "selection:spikes:expanded"
    st.session_state[key] = not st.session_state.get(key, False)


def _remember_week(widget, expected_week):
    if st.session_state.get("selection:spikes:week") == expected_week:
        st.session_state["selection:spikes:week"] = st.session_state[widget]


def daily_figure(daily, week):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.12)
    for row, column, label, color in [(1, "daily_streams", "Streams", "#6FD6AE"),
                                      (2, "daily_listeners", "Daily listeners", "#79AFFF")]:
        fig.add_trace(go.Scatter(x=daily.date, y=daily[column], mode="lines+markers", name=label,
                                line=dict(color=color, width=2), connectgaps=False,
                                hovertemplate="%{x|%b %d, %Y}<br>%{y:,.0f}<extra>%{fullData.name}</extra>"), row=row, col=1)
        fig.add_vrect(x0=week, x1=_shift(week, 7), fillcolor="#6FD6AE", opacity=.09,
                      line_width=0, row=row, col=1)
        fig.update_yaxes(title_text=label, rangemode="tozero", row=row, col=1)
    fig.update_layout(height=400, hovermode="x unified", showlegend=False)
    fig.update_xaxes(title_text="Spotify activity date · UTC", row=2, col=1)
    return fig


def _period(weekly):
    low, high = weekly.index.min().date(), _shift(weekly.index.max(), 6).date()
    years = [str(y) for y in range(low.year, high.year + 1)]
    chosen = controls.selectbox("Spike period", ["All Spotify history", *years, "Custom"], key="spikes:period")
    if chosen == "Custom":
        return controls.date_range("Spike comparison dates", low, high, (low, high), key="spikes:dates")
    if chosen in years:
        return date(int(chosen), 1, 1), date(int(chosen), 12, 31)
    return low, high


def _content(items, captures=None):
    captures = pd.DataFrame() if captures is None else captures
    missing = int((~items.caption_available).sum()) if len(items) else 0
    st.caption(f"{len(items):,} retained posts and Stories match this content window and filters · {missing:,} without a saved caption. Each platform/account/post identity appears once.")
    if items.empty:
        st.info("No retained posts or Stories match these filters. This does not establish that nothing was published.")
    else:
        page_size = 15
        pages = list(range(1, (len(items) + page_size - 1) // page_size + 1))
        page = controls.selectbox("Content page", pages, key="spikes:page",
                                  format_func=lambda p: f"{p} of {len(pages)}") if len(pages) > 1 else 1
        for item in items.iloc[(page - 1) * page_size:page * page_size].itertuples():
            relation = "Spike week" if item.week_offset == 0 else "Previous week" if item.week_offset == -1 else "Following week"
            caption = str(item.description or "")
            snippet = " ".join(caption.split())[:100] or "Caption unavailable"
            label = f"{item.dates} · {CONTENT_TYPES.get(item.exposure, item.platform)} · {relation} · {snippet}"
            with st.expander(label):
                st.caption(f"Post ID: {item.post_id} · {item.post_type} · Publication dates: {item.dates}")
                if item.date_conflict:
                    st.warning("Saved sources disagree on the publication day. All retained dates are shown; no exact day was chosen.")
                if item.caption_available:
                    st.text(caption)
                else:
                    st.info("No caption was retained for this item. Its content or song cannot be inferred from the date alone.")
                links = source_links(item.permalink)
                for number, link in enumerate(links, 1):
                    st.link_button("Open original " + ("Story" if item.exposure == "instagram_stories" else "post") +
                                   (f" · link {number}" if len(links) > 1 else ""), link)
                if not links:
                    st.caption("No usable original permalink was retained.")
                context = captures.loc[captures.identity_key.eq(item.identity_key)] if not captures.empty else captures
                if not context.empty:
                    st.caption("Retained lifetime content metrics · each capture and metric scope stays separate. These values are not daily activity or attributed Spotify streams.")
                    if context.selection_status.ne("latest_compatible_capture").any():
                        st.warning("Some capture times or same-time values are unresolved. These observations remain separate and do not establish a newest lifetime value.")
                    shown = context.drop(columns=["identity_key", "post_id", "observation_id"]).copy()
                    # Presentation order only: retain each capture's metric
                    # order while showing recent evidence before older rows.
                    shown["_capture_order"] = pd.to_datetime(shown.snapshot_timestamp, errors="coerce", utc=True, format="mixed")
                    shown = shown.sort_values("_capture_order", ascending=False, kind="stable", na_position="last").drop(columns="_capture_order")
                    shown["caption_evidence"] = shown.caption_evidence.map(CAPTION_EVIDENCE_LABELS).fillna(shown.caption_evidence)
                    column_order = ["metric", "value", "value_status", "snapshot_timestamp", "caption_evidence",
                                    "published_local", "publication_date", "metric_platform_scope", "measurement_type",
                                    "selection_status", "publication_timezone", "source_value", "source_table",
                                    "source_file", "source_url", "source_record"]
                    st.dataframe(shown[column_order], hide_index=True, width="stretch", column_config={
                        "metric": "Metric", "value": "Value", "value_status": "Metric status",
                        "snapshot_timestamp": "Captured (UTC)", "caption_evidence": "Caption evidence",
                        "published_local": "Native publication label", "publication_date": "Source publication date",
                        "metric_platform_scope": "Metric scope", "measurement_type": "Measurement type",
                        "selection_status": "Capture selection", "publication_timezone": "Publication timezone",
                        "source_value": "Raw metric value", "source_table": "Source table", "source_file": "Source file",
                        "source_url": "Source URL", "source_record": "Source record",
                    })
                else:
                    st.caption("No content metric was supplied in the retained captures for this identity.")
    _csv("Download surrounding posts & Stories · CSV", items, "spotify_spike_content.csv", "spikes-content-csv")
    if not captures.empty:
        _csv("Download surrounding content metric captures · CSV", captures,
             "spotify_spike_content_captures.csv", "spikes-content-captures-csv")


def _chart_help():
    with st.expander("How to read this chart", expanded=False):
        st.caption("Compare publishing cadence with listening activity over time, then inspect the content behind each week.")
        st.caption("Largest absolute increases between consecutive Monday–Sunday weeks. Average daily listeners is the mean of seven daily unique-listener counts, not weekly unique people. The preceding week supplies the baseline even when it falls outside the selected period.")
        st.caption("Click an increase to inspect its week, or open Edit filters and use Inspect Spotify week to choose any rising week. The chart starts with up to five increases; expand it to see up to 12, and use Show fewer to collapse it. Changing the chart size keeps your selected week and its surrounding content.")


def _weekly_summary(row, week, outcome):
    st.html("""
        <style>
        .st-key-spike-week-summary [data-testid="stMetric"] {
            border: 0; padding: 0;
        }
        .st-key-spike-week-summary [data-testid="stMetric"] > div {
            display: flex; flex-wrap: wrap; align-items: center;
            gap: 0.15rem 0.6rem;
        }
        .st-key-spike-week-summary [data-testid="stMetricLabel"] {
            flex-basis: 100%; margin-bottom: 0;
        }
        .st-key-spike-week-summary [data-testid="stMetricValue"],
        .st-key-spike-week-summary [data-testid="stMetricValue"] p {
            font-size: 1.5rem; font-weight: 600; line-height: 1.25;
        }
        .st-key-spike-week-summary [data-testid="stMetricDelta"] {
            background: none; padding: 0; border-radius: 0;
        }
        .st-key-spike-week-summary [data-testid="stMetricDelta"] p {
            white-space: normal; font-size: 0.875rem;
        }
        .st-key-spike-week-summary [data-testid="stVerticalBlock"] {
            gap: 0.2rem;
        }
        .st-key-spike-week-summary [data-testid="stColumn"] + [data-testid="stColumn"] {
            border-left: 1px solid #333330; padding-left: 1rem;
        }
        @media (max-width: 640px) {
            .st-key-spike-week-summary [data-testid="stColumn"] + [data-testid="stColumn"] {
                border-left: 0; padding-left: 0;
                border-top: 1px solid #333330; padding-top: 0.6rem;
            }
        }
        </style>
    """)
    st.caption(f"{week:%b %d}–{_shift(week, 6):%b %d, %Y} · vs {_shift(week, -7):%b %d}–{_shift(week, -1):%b %d, %Y}")
    with st.container(border=True, key="spike-week-summary"):
        cards = st.columns(2)
        for col, metric, label, precision in [(cards[0], "streams", "Weekly streams", 0),
                                             (cards[1], "mean_daily_listeners", "Average daily listeners", 1)]:
            increase = row[metric + "_increase"]
            delta = f"{increase:+,.{precision}f}" if pd.notna(increase) else None
            help_text = None
            if metric == outcome and delta is not None:
                pct = row["pct_change"]
                delta += f" ({pct:+.1f}%)" if pd.notna(pct) else " (% unavailable)"
                if pd.isna(pct):
                    help_text = "Percentage change is unavailable because the preceding value is zero."
            col.metric(label, fmt(row[metric + "_current"], precision), delta, help=help_text,
                       delta_arrow="off")
            col.caption("Previous " + fmt(row[metric + "_prior"], precision))


def render_spikes(repo, bundle):
    weekly = bundle["weekly"]
    if weekly.empty or SPOTIFY_SOURCE not in repo.tables:
        st.info("Spotify spike comparisons need consecutive complete weeks of daily Spotify data.")
        return
    with st.container(border=True, horizontal=True, vertical_alignment="center", key="spike-filters"):
        summary = st.empty()
        with st.popover("Edit filters", key="spikes-filter-editor"):
            outcome = controls.selectbox("Rank increases by", list(OUTCOMES), format_func=OUTCOMES.get, key="spikes:outcome")
            period = _period(weekly)
            ranked = rank_spotify_increases(weekly, outcome, *period) if period is not None else pd.DataFrame()
            chosen = None
            digits = 0 if outcome == "streams" else 1
            if not ranked.empty:
                weeks = pd.to_datetime(ranked.week_start).dt.strftime("%Y-%m-%d").tolist()
                lookup = ranked.set_index(pd.to_datetime(ranked.week_start).dt.strftime("%Y-%m-%d"))
                signature = sha256((outcome + ranked[["week_start", "increase"]].to_csv(index=False)).encode()).hexdigest()[:12]
                saved = "selection:spikes:week"
                chosen = st.session_state.get(saved, weeks[0])
                week_label = lambda w: f"{pd.Timestamp(w):%b %d, %Y} · +{lookup.loc[w, 'increase']:,.{digits}f} {OUTCOMES[outcome].lower()}"
                if chosen not in weeks:
                    chosen = weeks[0]
                    st.caption("Inspect Spotify week: the earlier selection is unavailable in this source; showing " + week_label(chosen) + ".")
                st.session_state[saved] = chosen
                # Closed popovers do not mount their widgets in the browser. A new
                # ID prevents an old hidden dropdown from replaying a stale week
                # after a chart selection on the next interaction.
                widget = f"control:spikes:week:{signature}:{chosen}"
                chosen = st.selectbox("Inspect Spotify week", weeks, index=weeks.index(chosen), key=widget,
                                      format_func=week_label, on_change=_remember_week, args=(widget, chosen))
                st.session_state[saved] = chosen
        period_choice = st.session_state.get("selection:spikes:period", "All Spotify history")
        if period is None:
            period_label, week_label = "Custom dates incomplete", "Choose both dates"
        else:
            period_label = (f"{period[0]:%b %d, %Y} – {period[1]:%b %d, %Y}" if period_choice == "Custom"
                            else "All history" if period_choice == "All Spotify history" else period_choice)
            week_label = (f"{pd.Timestamp(chosen):%b %d, %Y} (+{lookup.loc[chosen, 'increase']:,.{digits}f})"
                          if chosen is not None else "No rising weeks")
        summary.markdown(f"{OUTCOMES[outcome]} · {period_label} · {week_label}", width="stretch")
    if period is None:
        return
    if ranked.empty:
        st.info("No positive increases with a complete preceding week are available in this period.")
        return
    # A distinct ranking or chart size gets a fresh selection widget. Only an actual
    # chart click writes the chosen week; resizing cannot replay an old selection.
    expanded = st.session_state.get("selection:spikes:expanded", False)
    shown_count = min(12 if expanded else 5, len(ranked))
    shown_weeks = weeks[:shown_count]
    key = f"spikes-ranking-{signature}-{shown_count}"
    st.caption(f"{shown_count} largest weekly {'increase' if shown_count == 1 else 'increases'}")
    st.plotly_chart(ranking_figure(ranked, outcome, chosen, shown_count), width="stretch", key=key,
                    on_select=lambda: _choose_bar(key, shown_weeks), selection_mode="points",
                    config={"displayModeBar": False, "displaylogo": False})
    if chosen not in shown_weeks:
        st.caption(f"Selected week is #{weeks.index(chosen) + 1}, outside the top {shown_count}.")
    if len(ranked) > 5:
        st.button("Show fewer" if expanded else f"Show {min(12, len(ranked))} spikes",
                  key="spikes-toggle-ranking", on_click=_toggle_ranking, width="stretch")
    _chart_help()
    row, week = lookup.loc[chosen], pd.Timestamp(chosen)
    _weekly_summary(row, week, outcome)
    window = controls.selectbox("Content window", list(WINDOWS), key="spikes:window")
    before, after = WINDOWS[window]
    start, end = _shift(week, -7 * before), _shift(week, 6 + 7 * after)
    daily = repo.table(SPOTIFY_SOURCE, raw=True).copy()
    daily["date"] = pd.to_datetime(daily.date)
    daily = daily.loc[daily.date.between(start, end)].copy()
    for column in ["daily_streams", "daily_listeners"]:
        daily[column] = _observed(daily, column)
    # Preserve missing dates as gaps on both plots and in the inspected export.
    daily = daily.set_index("date").reindex(pd.date_range(start, end, name="date")).reset_index()
    st.subheader("Daily Spotify activity around this increase")
    st.caption("Shading marks the selected Spotify week. Social dates retain their source calendar; exact within-day ordering against UTC activity is unknown.")
    chart(daily_figure(daily, week), "spikes-daily")
    st.subheader("Surrounding posts & Stories")
    st.caption(f"{start:%b %d}–{end:%b %d, %Y}. Content filters below affect this list and its CSV; Spotify values keep the selected week and window.")
    exposures = controls.multiselect("Content types", list(CONTENT_TYPES), default=list(CONTENT_TYPES),
                                     format_func=CONTENT_TYPES.get, key="spikes:content-types")
    query = controls.text_input("Search surrounding captions, IDs or links", key="spikes:search")
    items = publications_around_week(bundle["identities"], week, before, after, exposures, query)
    captures = publication_capture_context(bundle.get("observations", pd.DataFrame()), items)
    _content(items, captures)
    with st.expander("Comparison data, coverage and sources"):
        st.write("These outcome-selected examples describe alignment, not post effectiveness or causation. A post in the same week can follow the initial Spotify increase; adjacent spike weeks can be part of one episode.")
        st.write("Older Instagram feed history and 2026 export tails are incomplete. Facebook Stories are unavailable. Missing captions remain unknown, and saved Story links may have expired. Only retained band-authored identities with a known publication week are included; cross-week date disputes are excluded.")
        st.caption("Sources from the selected saved version: Spotify artist_daily.csv; social/posts_latest.csv; instagram_stories_manual.csv; content_snapshots.csv and identity_bridges.csv. No lifetime engagement is allocated to these dates.")
        st.caption("Saved source version: " + str(getattr(repo, "registered_key", None) or "selected analysis repository"))
        st.dataframe(ranked, hide_index=True, width="stretch")
        _csv("Download ranked Spotify increases · CSV", ranked, "spotify_spike_rankings.csv", "spikes-ranking-csv")
        _csv("Download displayed daily Spotify activity · CSV", daily, "spotify_spike_daily.csv", "spikes-daily-csv")
