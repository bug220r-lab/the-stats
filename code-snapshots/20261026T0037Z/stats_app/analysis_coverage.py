"""Current-facing coverage derived from the selected immutable analysis.

Historical assessment prose is retained separately. Counts describe saved
evidence, never complete account history or absent activity.
"""
from __future__ import annotations

import math
import pandas as pd

from stats_app.analysis_content import METRICS, load_content_observations

FOLLOW_REPAIR = "social/meta_collection/follows_daily_resolved.csv"
SP = "spotify/cleaned/"
COLUMNS = ["Dataset", "Saved coverage", "Reporting / publication dates", "Remaining limits", "Source"]


def _span(values):
    dates = pd.to_datetime(values, errors="coerce").dropna()
    return f"{dates.min():%Y-%m-%d} – {dates.max():%Y-%m-%d}" if not dates.empty else "Unknown"


def current_coverage(repo, youtube_keys=()):
    """Return source-qualified coverage without changing any package asset."""
    rows = []

    def add(dataset, coverage, dates, remaining, source):
        rows.append(dict(zip(COLUMNS, [dataset, coverage, dates, remaining, source])))

    tables = set(repo.tables)
    if SP + "artist_daily.csv" in tables:
        daily = repo.table(SP + "artist_daily.csv")
        add("Spotify artist history", f"{daily.date.nunique():,} retained dates", _span(daily.date),
            "Later completed days need a fresh export; daily listeners and rolling audiences are not additive.", SP + "artist_daily.csv")
    if SP + "recovery_coverage.csv" in tables:
        histories = repo.table(SP + "recovery_coverage.csv")
        complete = histories.complete.astype(str).str.casefold().eq("true").sum()
        remaining = repo.table(SP + "remaining_limits.csv") if SP + "remaining_limits.csv" in tables else None
        add("Spotify recording history", f"{complete:,}/{len(histories):,} complete recording/metric histories", "See artist dates and source-specific windows",
            f"{len(remaining):,} retained collection queue limits." if remaining is not None else "See recovery evidence for source-specific limits.", SP + "recovery_coverage.csv")

    observations = load_content_observations(repo)
    if not observations.empty:
        valid = observations.loc[observations.identity_complete].copy()
        labels = valid.platform_selected + " posts"
        instagram = valid.platform_selected.eq("Instagram")
        stories = valid.post_type.str.contains("story", case=False, na=False)
        labels = labels.mask(instagram & ~stories, "Instagram feed / Reels").mask(instagram & stories, "Instagram Stories")
        labels = labels.mask(valid.platform_selected.eq("Facebook") & stories, "Facebook Stories")
        for label, part in valid.groupby(labels, sort=True):
            by_id = part.groupby("identity_key")
            numeric = part[METRICS].notna().any(axis=1).groupby(part.identity_key).any()
            text = part.description.fillna("").str.strip().ne("").groupby(part.identity_key).any()
            conflicts = by_id.publication_date.agg(lambda s: s.loc[s.ne("")].nunique()).gt(1).sum()
            limits = f"{int((~numeric).sum()):,} without numeric content metrics; {int((~text).sum()):,} without retained text."
            if conflicts:
                limits += f" {conflicts:,} identities have conflicting publication dates."
            if label == "Instagram Stories":
                clicks = part.link_clicks.notna().groupby(part.identity_key).any().sum()
                limits += f" Link-click values: {clicks:,}/{len(by_id):,} identities."
            add(label, f"{len(by_id):,} distinct identities", _span(part.publication_date), limits,
                "; ".join(sorted(part.source_table.unique())))
        if "Facebook Stories" not in set(labels):
            add("Facebook Stories", "Uncollected in this version", "Unknown", "Owner history and available insights remain unverified; absence here does not mean no activity.", "No retained Facebook Story identities")

    if FOLLOW_REPAIR in tables:
        follows = repo.table(FOLLOW_REPAIR)
        partial = ~follows.partial_day.astype(str).str.casefold().isin({"false", "0"})
        values = pd.to_numeric(follows.value, errors="coerce")
        numeric = values.map(lambda value: pd.notna(value) and math.isfinite(float(value)) and value >= 0)
        observed = follows.value_status.isin(["observed", "observed_zero", "explicit_zero_observed"])
        unique_dates = ~follows.duplicated("date", keep=False)
        complete = follows.loc[~partial & numeric & observed & unique_dates]
        add("Instagram follows repair", f"{complete.date.nunique():,} complete dates with numeric evidence", _span(complete.date),
            "Supersedes inherited missing-date notices within this range. Later/partial days remain unresolved; follows are events, not net followers.", FOLLOW_REPAIR)
    elif "social/account_daily.csv" in tables:
        add("Instagram follows repair", "No reviewed repair in this version", "See account activity", "Inherited missing values remain missing; select a later saved version if available.", "social/account_daily.csv")

    if "youtube-daily-20261023" in youtube_keys:
        add("YouTube daily supplement", "Registered separately from the parent", "See YouTube collection", "Watch time, average duration and subscribers gained/lost have a later supplement. Parent-only gaps are historical; source blanks remain unavailable.", "youtube-daily-20261023")
    add("TikTok analytics", "No verified analytics exports in this version", "Unknown", "Account access and available reporting range have not been rechecked.", "Retained access receipts")
    add("Historical statistical results", "Original inputs retained", "See each saved analysis", "New descriptive content summaries do not rerun or extend the historical testing families.", "statistical_results.csv")
    return pd.DataFrame(rows, columns=COLUMNS)


def render_current_coverage(repo, youtube_keys=(), key="current-coverage"):
    import streamlit as st
    from stats_app.analysis_ui_common import download

    data = current_coverage(repo, youtube_keys)
    version = getattr(repo, "registered_key", repo.metadata.get("analysis_version", "selected saved version"))
    st.subheader("Current saved coverage")
    st.caption(f"Selected analysis: {version}. Counts describe retained evidence, not complete account history. Publication dates, activity dates and captures keep their own meanings.")
    st.dataframe(data.drop(columns="Source"), hide_index=True, width="stretch")
    with st.expander("Coverage sources and definitions"):
        st.dataframe(data, hide_index=True, width="stretch")
        download(data, "current_saved_coverage.csv", key + "-csv")
        st.caption("Distinct content identities use platform, verified account identity and native post ID. Field availability checks all retained captures; compatible lifetime snapshots remain separate. Original assessment documents below retain their historical source state.")
    return data
