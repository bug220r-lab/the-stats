"""Pure ranking and publication drill-down over a selected immutable data bundle.

No saved finding, active-version name, external lookup or source mutation enters
these calculations. Nearby publications establish timing context, not attribution.
"""
from __future__ import annotations

from datetime import timedelta
import json
import re

import numpy as np
import pandas as pd

from stats_app.analysis_correlation import EXPOSURES, OUTCOMES
from stats_app.analysis_content import METRICS, select_content_observations

CONTEXT_METRICS = ("streams", "mean_daily_listeners")
RANK_COLUMNS = ["week_start", "week_end", "previous_week_start", "prior", "current", "increase", "pct_change",
                *[f"{metric}_{field}" for metric in CONTEXT_METRICS for field in ("prior", "current", "increase", "pct_change")]]
PUBLICATION_COLUMNS = ["identity_key", "post_id", "platform", "exposure", "strict_band", "band_authored", "dates", "week",
                       "date_conflict", "text", "description", "post_type", "permalink", "author_evidence",
                       "publication_week", "week_offset", "relation", "caption_available", "caption_availability",
                       "timing_status", "timing_note"]
CAPTURE_CONTEXT_COLUMNS = ["identity_key", "post_id", "snapshot_timestamp", "metric_platform_scope", "measurement_type",
                           "selection_status", "publication_date", "published_local", "publication_timezone",
                           "caption_evidence", "metric", "value", "value_status", "source_value", "source_table",
                           "source_file", "source_url", "source_record", "observation_id"]


def _text(value):
    return "" if value is None or pd.isna(value) else str(value)


def _true(value):
    return _text(value).strip().lower() in {"true", "1"}


def _date(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is not None or stamp != stamp.normalize():
        raise ValueError("Use a known calendar date without an inferred timezone or time of day.")
    return stamp


def _monday(value):
    stamp = _date(value)
    return pd.Timestamp(stamp.date() - timedelta(days=stamp.weekday()))


def _offset(index, days):
    return index + np.timedelta64(days * 86_400_000_000_000, "ns")


def _weekly_frame(weekly):
    frame = weekly.copy()
    if "week_start" in frame:
        supplied = pd.DatetimeIndex(pd.to_datetime(frame.week_start, errors="raise"))
        if isinstance(frame.index, pd.DatetimeIndex) and not frame.index.equals(supplied):
            raise ValueError("Conflicting weekly index and week_start column.")
        frame = frame.drop(columns="week_start")
        frame.index = supplied
    elif not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Weekly activity needs a DatetimeIndex or explicit week_start column.")
    index = frame.index
    if index.tz is not None or index.hasnans or index.has_duplicates or (index.dayofweek != 0).any() or not index.equals(index.normalize()):
        raise ValueError("Weekly activity requires unique timezone-naive Monday dates.")
    if "spotify_days" not in frame:
        raise ValueError("Spotify observed-day counts are required to establish complete weeks.")
    for column in ("artist_id", "snapshot_class", "reporting_timezone"):
        if column in frame and frame[column].fillna("").nunique() != 1:
            raise ValueError("Choose one artist, retrieval vintage and reporting timezone.")
    if "reporting_timezone" in frame and not frame.reporting_timezone.eq("UTC").all():
        raise ValueError("Spotify comparisons require the retained UTC reporting calendar.")
    if "week_end" in frame:
        ends = pd.to_datetime(frame.week_end, errors="coerce")
        if not pd.DatetimeIndex(ends).equals(_offset(index, 6)):
            raise ValueError("Each weekly endpoint must be the following Sunday.")
    frame = frame.sort_index()
    return frame.reindex(pd.date_range(frame.index.min(), frame.index.max(), freq="W-MON", name="week_start"))


def _valid_values(frame, metric, complete):
    if metric not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    values = pd.to_numeric(frame[metric], errors="coerce").astype(float)
    good = complete & np.isfinite(values)
    if metric != "net_followers":
        good &= values.ge(0)
    status = metric + "_status"
    if status in frame:
        good &= frame[status].isin({"observed", "observed_zero", "available", "complete"})
    return values.where(good)


def rank_spotify_increases(weekly, outcome="streams", start=None, end=None):
    """Rank positive absolute rises using adjacent complete weeks before filtering.

    Returns an explicit ``week_start`` column. The prior comparison can precede
    the selected display period; pass the full bundle history, not a pre-sliced
    frame. Percentage change is unavailable when the prior value is zero or
    negative. Context listener values are averages of daily uniques.
    """
    if outcome not in OUTCOMES:
        raise ValueError("Choose a supported Spotify outcome.")
    low, high = _date(start) if start is not None else None, _date(end) if end is not None else None
    if low is not None and high is not None and low > high:
        raise ValueError("The reporting start must not follow the end.")
    if weekly.empty:
        return pd.DataFrame(columns=RANK_COLUMNS)
    if outcome not in weekly:
        raise ValueError("The selected Spotify outcome is not present.")
    frame = _weekly_frame(weekly)
    complete = pd.to_numeric(frame.spotify_days, errors="coerce").eq(7)
    if "complete_week" in frame:
        complete &= frame.complete_week.map(_true)
    result = pd.DataFrame(index=frame.index)
    result["week_end"] = _offset(frame.index, 6)
    result["previous_week_start"] = _offset(frame.index, -7)
    for metric in dict.fromkeys((outcome, *CONTEXT_METRICS)):
        current = _valid_values(frame, metric, complete)
        prior = current.shift(1)
        increase = current - prior
        percentage = increase / prior.where(prior.gt(0)) * 100
        if metric == outcome:
            result["prior"], result["current"], result["increase"], result["pct_change"] = prior, current, increase, percentage
        if metric in CONTEXT_METRICS:
            for field, values in (("prior", prior), ("current", current), ("increase", increase), ("pct_change", percentage)):
                result[f"{metric}_{field}"] = values
    valid = result.increase.gt(0) & result.prior.notna() & result.current.notna()
    if low is not None:
        valid &= result.index >= low
    if high is not None:
        valid &= result.week_end.le(high)
    result = result.loc[valid].reset_index().sort_values(["increase", "week_start"], ascending=[False, True], kind="stable").reset_index(drop=True)
    result = result.reindex(columns=RANK_COLUMNS)
    result.attrs.update(outcome=outcome, ranking="Positive absolute increase; ties ordered by earlier week",
        comparison="Previous adjacent complete Monday–Sunday week, calculated before display-period filtering",
        listener_definition="Average daily unique listeners, not weekly unique listeners",
        percentage_definition="(current - prior) / prior; unavailable when prior is zero or negative",
        selection_start=str(low.date()) if low is not None else None, selection_end=str(high.date()) if high is not None else None,
        source_calendar_weeks=len(frame), complete_source_weeks=int(complete.sum()),
        missing_or_invalid_pair_weeks=int((_valid_values(frame, outcome, complete).isna() | _valid_values(frame, outcome, complete).shift().isna()).sum()))
    return result


def _join_texts(values):
    return "\n".join(dict.fromkeys(_text(value) for value in values if _text(value)))


def _caption_available(values):
    blank = {"", "-", "--", "—", "n/a", "none", "nan", "loading preview", "loading preview...", "loading preview…"}
    return any(_text(value).strip().casefold() not in blank for value in values)


def _capture_caption_evidence(capture):
    """Describe supplied caption evidence; embedded JSON never supplies text."""
    text_present = _caption_available([capture.get("description", "")])
    try:
        native = json.loads(_text(capture.get("native_record_json")))
    except (ValueError, TypeError, RecursionError):
        native = None
    status = native.get("description_status") if isinstance(native, dict) else None
    if status == "native_no_text":
        return "conflicting_native_caption_evidence" if text_present else "native_no_text"
    if status == "native_text_present":
        return "native_text_present" if text_present else "native_text_reported_but_not_retained"
    return "retained_source_text" if text_present else "not_collected_or_unavailable"


def publication_capture_context(observations, publications):
    """Keep lifetime metric evidence beside publications, never in their counts.

    Each row is one metric from one latest-compatible capture or an unresolved
    capture. Scope, time, selection status and source reference remain explicit.
    No capture values are added or assigned to Spotify activity dates.
    """
    if observations.empty or publications.empty:
        return pd.DataFrame(columns=CAPTURE_CONTEXT_COLUMNS)
    keys = set(publications.identity_key)
    selected = select_content_observations(observations.loc[observations.identity_key.isin(keys)])
    records = []
    source_fields = [field for field in CAPTURE_CONTEXT_COLUMNS if field not in {"caption_evidence", "metric", "value", "value_status", "source_value"}]
    for capture in selected.to_dict("records"):
        caption_evidence = _capture_caption_evidence(capture)
        for metric in METRICS:
            status = _text(capture.get(metric + "_status"))
            raw = _text(capture.get(metric + "_raw"))
            if not raw and status in {"", "not_supplied"}:
                continue
            row = {field: capture.get(field, "") for field in source_fields}
            row.update(caption_evidence=caption_evidence, metric=metric, value=capture.get(metric, np.nan),
                       value_status=status, source_value=raw)
            records.append(row)
    return pd.DataFrame(records, columns=CAPTURE_CONTEXT_COLUMNS)


def publications_around_week(identities, week, before_weeks=1, after_weeks=0, exposures=None, query=""):
    """Return strict band identities with one certain publication week.

    All source dates, text and permalinks remain present. Two disputed dates in
    one week are eligible; disputed weeks and absent dates are not resolved.
    Relation describes calendar placement, not ordering within a day or impact.
    """
    if isinstance(before_weeks, bool) or not isinstance(before_weeks, int) or before_weeks not in {0, 1, 2}:
        raise ValueError("Choose zero, one or two preceding weeks.")
    if isinstance(after_weeks, bool) or not isinstance(after_weeks, int) or after_weeks not in {0, 1}:
        raise ValueError("Choose zero or one following week.")
    target = _date(week)
    if target.weekday() != 0:
        raise ValueError("Choose the Monday starting the Spotify week.")
    chosen_exposures = set(EXPOSURES if exposures is None else [exposures] if isinstance(exposures, str) else exposures)
    if not chosen_exposures.issubset(EXPOSURES):
        raise ValueError("Choose supported publication series.")
    columns = list(dict.fromkeys([*identities.columns, *PUBLICATION_COLUMNS]))
    empty = pd.DataFrame(columns=columns)
    if identities.empty:
        return empty
    required = {"identity_key", "post_id", "platform", "exposure", "dates"}
    if not required.issubset(identities) or not {"strict_band", "band_authored"}.intersection(identities):
        raise ValueError("Use the source-qualified identity bundle with authorship and date evidence.")
    if identities.identity_key.map(_text).eq("").any():
        raise ValueError("Typed identity keys are required; bare post IDs cannot be deduplicated safely.")
    excluded = {"authorship_or_identity": 0, "unknown_or_invalid_date": 0, "conflicting_week": 0, "outside_window_or_series": 0}
    records = []
    for key, group in identities.groupby("identity_key", sort=False):
        for field in ("post_id", "platform", "exposure"):
            if group[field].map(_text).nunique() != 1:
                raise ValueError("Conflicting identity metadata cannot be collapsed into one publication.")
        author_column = "strict_band" if "strict_band" in group else "band_authored"
        authors = set(";".join(group.get("author_evidence", pd.Series(dtype=str)).map(_text)).split(";"))
        affirmative_other = {"associated_account_authorship_unverified", "other_author_association_unverified", "verified_collaboration"}
        complete_identity = not str(key).startswith("unresolved:") and ("identity_complete" not in group or group.identity_complete.map(_true).all())
        if not group[author_column].map(_true).all() or not complete_identity or bool(authors & affirmative_other):
            excluded["authorship_or_identity"] += 1
            continue
        raw_dates = sorted({part.strip() for value in group.dates.map(_text) for part in value.split(";") if part.strip()})
        try:
            if not raw_dates or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in raw_dates):
                raise ValueError("Missing or invalid source date")
            dates = [_date(value) for value in raw_dates]
        except (ValueError, TypeError):
            excluded["unknown_or_invalid_date"] += 1
            continue
        weeks = {_monday(value) for value in dates}
        if len(weeks) != 1:
            excluded["conflicting_week"] += 1
            continue
        publication_week = next(iter(weeks))
        offset = (publication_week.date() - target.date()).days // 7
        row = group.iloc[0].to_dict()
        if row["exposure"] not in chosen_exposures or not -before_weeks <= offset <= after_weeks:
            excluded["outside_window_or_series"] += 1
            continue
        caption_values = [value for field in ("description", "text") if field in group for value in group[field]]
        text = _join_texts(caption_values)
        for field in ("permalink", "post_type", "source_file", "source_url"):
            if field in group:
                row[field] = _join_texts(group[field])
        conflict = len(dates) > 1
        available = _caption_available(caption_values)
        row.update(identity_key=key, strict_band=True, band_authored=True, dates=";".join(raw_dates),
            week=publication_week.strftime("%Y-%m-%d"), publication_week=publication_week, week_offset=offset,
            relation="preceding_week" if offset < 0 else "following_week" if offset > 0 else "same_week",
            date_conflict=conflict, text=text, description=text, caption_available=available,
            caption_availability="source_text_available" if available else "not_available_in_retained_source",
            timing_status="week_certain_date_conflict" if conflict else "source_calendar_date",
            timing_note=("Retained publication dates disagree but fall in the same week. " if conflict else "") +
                "Source calendar dates do not establish UTC publication time, intraday order relative to a Spotify peak, or causality.")
        records.append(row)
    result = pd.DataFrame(records).reindex(columns=columns) if records else empty
    search = str(query or "").strip().casefold()
    if search and not result.empty:
        searchable = [field for field in ("text", "description", "post_id", "permalink", "dates", "post_type", "platform", "exposure") if field in result]
        matches = result[searchable].apply(lambda row: any(search in _text(value).casefold() for value in row), axis=1)
        result = result.loc[matches].copy()
    if not result.empty:
        result = result.sort_values(["publication_week", "dates", "platform", "post_id", "identity_key"], kind="stable").reset_index(drop=True)
    result.attrs.update(selected_week=str(target.date()), preceding_weeks=before_weeks, following_weeks=after_weeks,
        excluded_identities=excluded, retained_matches=len(result),
        caption_definition="Caption availability means retained source text is present; blank captions do not identify Story subject or audio.",
        timing_definition="Relative publication week only; timing overlap is not an attributed listening effect.")
    return result
