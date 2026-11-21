"""Source-qualified content summaries shared by Social and Decision reports.

Publication inventory is counted once per typed identity. Performance stays at
one latest compatible observation per identity, metric scope and measurement
type, with capture-day cohorts kept separate and unresolved evidence excluded.
"""
from __future__ import annotations

import pandas as pd

from stats_app.analysis_content import (
    METRICS, content_table_paths, identity_bridge_paths,
    conflicting_publication_identities, content_identity_inventory,
    load_content_observations, select_content_observations,
)

SUMMARY_KEYS = ["platform_selected", "identity_account_id_type", "identity_account_id",
                "metric_platform_scope", "measurement_type", "capture_cohort", "post_type", "author_scope"]
SUMMARY_METRICS = ["views", "reach", "interactions", "engagement_actions", "shares", "saves",
                   "comments", "profile_visits", "link_clicks"]


def content_source_paths(repo):
    return content_table_paths(repo) + identity_bridge_paths(repo)


def latest_summary_observations(observations):
    """Retain all selection statuses and add an explicitly UTC capture cohort."""
    selected = select_content_observations(observations)
    if not selected.empty:
        selected["capture_cohort"] = selected.capture_time_utc.map(
            lambda value: "Unknown capture time" if pd.isna(value) else value.strftime("%Y-%m-%d UTC"))
    return selected


def content_coverage(observations, selected=None):
    """Inventory coverage, independent of performance-group overlap."""
    selected = latest_summary_observations(observations) if selected is None else selected
    if observations.empty:
        return dict(identities=0, retained_observations=0, selected_observations=0, stories=0,
                    unknown_date_identities=0, conflicting_date_identities=0, unresolved_identity_observations=0,
                    unknown_capture_observations=0, conflicting_capture_observations=0, publication_start=None,
                    publication_end=None, identities_without_numeric_metrics=0, source_tables=[], by_platform=[])
    complete = observations.loc[observations.identity_complete]
    inventory = content_identity_inventory(complete, complete)
    known = inventory.loc[inventory.publication_date_status.eq("Known date"), "publication_dates"]
    return dict(identities=int(complete.identity_key.nunique()), retained_observations=len(observations),
                selected_observations=len(selected),
                stories=int(complete.loc[complete.post_type.str.contains("story", case=False), "identity_key"].nunique()),
                unknown_date_identities=int(inventory.publication_date_status.eq("Unknown date").sum()),
                conflicting_date_identities=len(conflicting_publication_identities(complete)),
                unresolved_identity_observations=int((~observations.identity_complete).sum()),
                unknown_capture_observations=int(selected.capture_time_utc.isna().sum()),
                conflicting_capture_observations=int(selected.selection_status.eq("same_time_conflict").sum()),
                identities_without_numeric_metrics=int(complete.identity_key.nunique()-complete.loc[complete[METRICS].notna().any(axis=1), "identity_key"].nunique()),
                publication_start=None if known.empty else known.min(), publication_end=None if known.empty else known.max(),
                source_tables=sorted(observations.source_table.unique().tolist()),
                by_platform=[dict(platform=platform, identities=int(group.identity_key.nunique()),
                                  stories=int(group.loc[group.post_type.str.contains("story", case=False), "identity_key"].nunique()))
                             for platform, group in complete.groupby("platform_selected", sort=True)])


def content_distribution_rows(observations, selected=None):
    """Describe distinct content in each compatible group; never total captures.

    Unknown capture times and same-time conflicts remain in population and
    missingness counts but supply no selected metric or age value.
    """
    selected = latest_summary_observations(observations) if selected is None else selected
    if selected.empty:
        return []
    selected = selected.loc[selected.identity_complete]
    date_conflicts = conflicting_publication_identities(observations)
    rows = []
    for key, group in selected.groupby(SUMMARY_KEYS, dropna=False, sort=True):
        identities = group.identity_key.nunique()
        eligible = group.loc[group.selection_status.eq("latest_compatible_capture")].copy()
        # Guard future selectors and contradictory duplicates; never choose an
        # arbitrary source row to make one identity appear twice in a median.
        eligible = eligible.loc[~eligible.identity_key.duplicated(keep=False)]
        excluded = identities - eligible.identity_key.nunique()
        age = eligible.loc[~eligible.identity_key.isin(date_conflicts), "post_age_days"].dropna()
        for metric in SUMMARY_METRICS:
            values = eligible[metric].dropna()
            rows.append(dict(zip(SUMMARY_KEYS, key), selected_account_id=key[2], metric=metric,
                posts=int(identities), retained_observations=len(group), observed=len(values),
                missing=int(identities-len(values)), excluded_metric_identities=int(excluded),
                median=values.median(), p25=values.quantile(.25), p75=values.quantile(.75), maximum=values.max(),
                youngest_days=age.min(), oldest_days=age.max(), age_observed=len(age),
                source_table="; ".join(sorted(group.source_table.unique())),
                measurement="lifetime_snapshot" if key[4] == "lifetime_content_snapshot" else key[4],
                limitation="Unequal post ages/exposure; latest compatible captures within each UTC capture-day cohort, format, author and metric scope. Groups may overlap in identities and must not be added; unknown chronology and same-time conflicts supply no selected metric."))
    return rows


def content_summary(repo):
    observations = load_content_observations(repo)
    selected = latest_summary_observations(observations)
    return observations, selected, content_coverage(observations, selected), content_distribution_rows(observations, selected)
