"""Source-qualified publication/Spotify exploration; no UI or statistical fitting.

Publication counts describe retained identities, never verified inactivity. Saved
inference is exposed only when its reviewed six-source manifest matches the
selected immutable repository. Interactive estimates are descriptive Spearman
correlations; changing filters never reruns bootstrap or significance tests.
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from stats_app.analysis_content import load_content_observations

EXPOSURES = ("facebook_posts", "instagram_stories", "instagram_feed")
REVIEWED_EXPOSURES = EXPOSURES[:2]
OUTCOMES = ("streams", "mean_daily_listeners", "saves", "playlist_adds", "net_followers")
LABELS = {"facebook_posts": "Retained Facebook posts", "instagram_stories": "Retained Instagram Stories",
          "instagram_feed": "Retained Instagram feed posts", "streams": "Spotify streams",
          "mean_daily_listeners": "Average daily listeners", "saves": "Save actions",
          "playlist_adds": "Playlist additions", "net_followers": "Net follower change"}
REVIEWED_START, REVIEWED_END = "2024-01-01", "2025-12-28"
SOURCE_PATHS = ("spotify/cleaned/artist_daily.csv", "spotify/cleaned/release_events.csv",
                "social/posts_latest.csv", "social/meta_collection/instagram_stories_manual.csv",
                "social/meta_content_20261023/content_snapshots.csv", "social/meta_content_20261023/identity_bridges.csv")
DEFAULT_ANALYSIS_DIR = Path(__file__).resolve().parents[1] / "data/analysis/social_spotify_20261023"
CAPTIONS = [
    "Counts describe retained band-authored publication identities, not views or lifetime engagement. A zero means no retained publication, not verified inactivity.",
    "Spotify uses UTC dates; Meta publication timezone is not consistently confirmed. Matching calendar weeks is not a timezone conversion.",
    "Streams, save actions and playlist additions are summed across complete weeks. Average daily listeners is not weekly unique listeners; follower changes use consecutive balances.",
    "Interactive correlations are descriptive. Adjacent changes reduce shared long-term trend but do not adjust fully for seasonality, campaigns, releases or other causes. No two-week-lag model is fitted.",
    "Retained 2026 Facebook/Instagram feed counts drop after May; sources cannot distinguish real posting decline from archival/filter coverage. This period cannot validate predictive uplift.",
    "Instagram feed history is incomplete, especially before October 2025. Its optional exploratory series has no reviewed inference.",
]
IDENTITY_COLUMNS = ["identity_key", "post_id", "platform", "exposure", "strict_band", "band_authored", "dates", "week",
                    "date_conflict", "text", "description", "post_type", "permalink", "author_evidence", "observation_count", "identity_complete"]


def _text(value):
    return "" if value is None or pd.isna(value) else str(value)


def _date(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is not None:
        raise ValueError("Use a known source-calendar date without an inferred timezone.")
    return stamp.normalize()


def monday(value):
    stamp = _date(value)
    return pd.Timestamp(stamp.date() - timedelta(days=stamp.weekday()))


def _offset(value, days):
    return pd.Timestamp(_date(value).date() + timedelta(days=days))


def _offset_index(index, days):
    # Explicit nanosecond units avoid pandas/NumPy generic-timedelta coercion.
    return index + np.timedelta64(days * 86_400_000_000_000, "ns")


def publication_identities(observations):
    """Collapse captures by the reader's typed/bridged identity, never bare ID.

    Unknown author evidence may coexist with positive band-author evidence.
    Any affirmative alternative/associated authorship excludes the identity.
    A date dispute is retained as its entire date set, not resolved by order.
    """
    if observations.empty:
        return pd.DataFrame(columns=IDENTITY_COLUMNS)
    required = {"identity_key", "post_id", "platform_selected", "post_type", "author_scope", "publication_date"}
    if not required.issubset(observations):
        raise ValueError("Publication observations lack required identity, author or date fields.")
    if observations.identity_key.fillna("").eq("").any():
        raise ValueError("A typed publication identity is required; bare post IDs are insufficient.")
    rows = []
    for key, group in observations.groupby("identity_key", sort=False):
        platforms = set(group.platform_selected.map(_text))
        post_ids = set(group.post_id.map(_text))
        if len(platforms) != 1 or len(post_ids) != 1:
            raise ValueError("One publication identity cannot contain different platforms or post IDs.")
        dates = set()
        for value in group.publication_date.map(_text):
            try:
                if value and len(value) == 10 and _date(value).strftime("%Y-%m-%d") == value:
                    dates.add(value)
            except (ValueError, TypeError):
                pass
        dates = sorted(dates)
        weeks = sorted({monday(value).strftime("%Y-%m-%d") for value in dates})
        authors = set(group.author_scope.map(_text))
        complete = (all(str(v).lower() in {"true", "1"} for v in group.identity_complete)
                    if "identity_complete" in group else not str(key).startswith("unresolved:"))
        conflicting_authors = {"associated_account_authorship_unverified", "other_author_association_unverified", "verified_collaboration"}
        strict = complete and "band_authored" in authors and not bool(authors & conflicting_authors)
        platform, post_id = next(iter(platforms)), next(iter(post_ids))
        kinds = set(group.post_type.map(_text))
        story_types = {"IG story"}
        exposure = ("facebook_posts" if platform == "Facebook" and not any("story" in p.lower() for p in kinds)
                    else "instagram_stories" if platform == "Instagram" and kinds == story_types
                    else "instagram_feed" if platform == "Instagram" and not any("story" in p.lower() for p in kinds)
                    else "unsupported_or_conflicting_type")
        def texts(column):
            return "\n".join(dict.fromkeys(v for v in group.get(column, pd.Series(dtype=str)).map(_text) if v))
        rows.append(dict(identity_key=key, post_id=post_id, platform=platform, exposure=exposure,
            strict_band=bool(strict), band_authored=bool(strict), dates=";".join(dates), week=weeks[0] if len(weeks) == 1 else "",
            date_conflict=len(dates) > 1, text=texts("description"), description=texts("description"),
            post_type=";".join(sorted(kinds)), permalink=texts("permalink"),
            author_evidence=";".join(sorted(authors)), observation_count=len(group), identity_complete=bool(complete)))
    return pd.DataFrame(rows, columns=IDENTITY_COLUMNS)


def _weekly_index(values):
    index = pd.DatetimeIndex(pd.to_datetime(values))
    if index.tz is not None or index.hasnans or index.has_duplicates or (index.dayofweek != 0).any() or (index != index.normalize()).any():
        raise ValueError("Weekly rows require unique, timezone-naive Monday dates.")
    return index.sort_values().rename("week_start")


def _observed(frame, metric):
    if metric not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    values = pd.to_numeric(frame[metric], errors="coerce").astype(float)
    values = values.where(np.isfinite(values) & values.ge(0))
    status = metric + "_status" if metric + "_status" in frame else "value_status"
    if status in frame:
        values = values.where(frame[status].isin({"observed", "observed_zero", "available"}))
    if "partial_day" in frame:
        values = values.where(frame.partial_day.astype(str).str.lower().isin({"false", "0"}))
    return values


def weekly_spotify(daily):
    """Retain every calendar week and per-outcome missingness, including gaps."""
    columns = ["spotify_days", "complete_week", "week_end", *OUTCOMES]
    if daily.empty:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], name="week_start"))
    if "date" not in daily:
        raise ValueError("Spotify daily data requires reporting dates.")
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame.date, errors="raise")
    if frame.date.isna().any() or frame.date.dt.tz is not None or not frame.date.eq(frame.date.dt.normalize()).all():
        raise ValueError("Spotify activity must have known UTC calendar-date labels.")
    for column in ("artist_id", "snapshot_class", "reporting_timezone"):
        if column in frame and frame[column].fillna("").nunique() != 1:
            raise ValueError("Select one Spotify artist, retrieval vintage and reporting timezone.")
    if "reporting_timezone" in frame and not frame.reporting_timezone.eq("UTC").all():
        raise ValueError("This comparison requires Spotify UTC daily activity.")
    if frame.date.duplicated().any():
        raise ValueError("Duplicate Spotify dates would inflate activity; no aggregate produced.")
    frame = frame.sort_values("date").reset_index(drop=True)
    for column in ("daily_streams", "daily_listeners", "daily_saves", "daily_playlist_adds", "followers_stock"):
        frame[column] = _observed(frame, column)
    consecutive = frame.date.diff().dt.days.eq(1)
    frame["net_followers"] = frame.followers_stock.diff().where(consecutive)
    frame["week_start"] = frame.date - pd.to_timedelta(frame.date.dt.dayofweek, unit="D")
    index = pd.date_range(monday(frame.date.min()), monday(frame.date.max()), freq="W-MON", name="week_start")
    rows = []
    grouped = {week: group for week, group in frame.groupby("week_start")}
    for week in index:
        group = grouped.get(week, frame.iloc[:0])
        complete = len(group) == 7
        row = dict(week_start=week, week_end=_offset(week, 6), spotify_days=len(group), complete_week=complete)
        for dest, src in (("streams", "daily_streams"), ("saves", "daily_saves"), ("playlist_adds", "daily_playlist_adds"), ("net_followers", "net_followers")):
            row[dest] = float(group[src].sum()) if complete and group[src].notna().all() else np.nan
        row["mean_daily_listeners"] = float(group.daily_listeners.mean()) if complete and group.daily_listeners.notna().all() else np.nan
        rows.append(row)
    result = pd.DataFrame(rows).set_index("week_start")
    result.attrs["coverage"] = {"source_start": str(frame.date.min().date()), "source_end": str(frame.date.max().date()),
        "source_days": len(frame), "missing_calendar_days": int((frame.date.max()-frame.date.min()).days + 1-len(frame)),
        "incomplete_calendar_weeks": int((~result.complete_week).sum())}
    return result


def weekly_publications(identities, index, date_shift=0):
    """Retained counts inside observed bounds; unknown tails and disputed weeks stay null."""
    if not isinstance(date_shift, int) or isinstance(date_shift, bool) or date_shift not in {-1, 0, 1}:
        raise ValueError("Publication-date sensitivity is limited to -1, 0 or +1 day.")
    index = _weekly_index(index)
    result = pd.DataFrame(0.0, index=index, columns=EXPOSURES)
    coverage = {}
    for exposure in EXPOSURES:
        group = identities.loc[identities.strict_band.eq(True) & identities.exposure.eq(exposure)] if not identities.empty else identities
        all_dates, ambiguous_weeks = [], set()
        unknown = 0
        for row in group.itertuples():
            dates = [_offset(value, date_shift) for value in row.dates.split(";") if value]
            all_dates.extend(dates)
            weeks = {monday(value) for value in dates}
            if len(weeks) == 1:
                week = next(iter(weeks))
                if week in result.index:
                    result.loc[week, exposure] += 1
            elif len(weeks) > 1:
                ambiguous_weeks.update(weeks)
            else:
                unknown += 1
        status = exposure + "_status"
        result[status] = "retained_count_only"
        if not all_dates:
            result[exposure] = np.nan
            result[status] = "no_eligible_publication_evidence"
            first = last = last_full = None
        else:
            first, last = min(all_dates), max(all_dates)
            last_full = monday(last) if last.weekday() == 6 else _offset(monday(last), -7)
            # An observed publication does not certify every day in its edge week.
            outside = (result.index < first) | (_offset_index(result.index, 6) > last)
            result.loc[outside, exposure] = np.nan
            result.loc[outside, status] = "outside_observed_publication_bounds"
        disputed = result.index.intersection(pd.DatetimeIndex(sorted(ambiguous_weeks)))
        result.loc[disputed, exposure] = np.nan
        result.loc[disputed, status] = "ambiguous_publication_week"
        coverage[exposure] = {"first_publication_date": str(first.date()) if first is not None else None,
            "last_publication_date": str(last.date()) if last is not None else None,
            "last_complete_publication_week": str(last_full.date()) if last_full is not None else None,
            "eligible_identities": len(group), "unknown_date_identities": unknown, "ambiguous_weeks": len(ambiguous_weeks),
            "coverage_status": "retained_archive_only_not_complete_history" if all_dates else "unavailable",
            "note": "Interior zeros mean zero retained publications. Source/filter gaps and unretained content cannot be distinguished from real inactivity."}
    result.attrs["series"] = coverage
    return result


def select_complete_weeks(weekly, start=None, end=None):
    """Select only seven-date Monday–Sunday rows fully inside the requested dates."""
    result = weekly.copy()
    if result.empty:
        return result
    _weekly_index(result.index)
    low = _date(start) if start is not None else result.index.min()
    high = _date(end) if end is not None else _offset(result.index.max(), 6)
    if low > high:
        raise ValueError("Start date must not follow end date.")
    mask = (result.index >= low) & (_offset_index(result.index, 6) <= high)
    if "spotify_days" in result:
        mask &= result.spotify_days.eq(7)
    if "complete_week" in result:
        mask &= result.complete_week.eq(True)
    result = result.loc[mask].sort_index().copy()
    result.attrs["requested_start"] = str(low.date())
    result.attrs["requested_end"] = str(high.date())
    return result


def build_weekly_activity(repo, start=None, end=None):
    observations = load_content_observations(repo)
    identities = publication_identities(observations)
    if SOURCE_PATHS[0] not in repo.tables:
        raise ValueError("The selected version has no artist daily Spotify source.")
    spotify = weekly_spotify(repo.table(SOURCE_PATHS[0], raw=True))
    publications = weekly_publications(identities, spotify.index)
    combined = spotify.join(publications)
    weekly = select_complete_weeks(combined, start, end)
    coverage = dict(spotify=spotify.attrs.get("coverage", {}), series=publications.attrs["series"],
        observations=len(observations), identities=len(identities),
        strict_band_identities=int(identities.strict_band.eq(True).sum()),
        excluded_authorship_or_identity=int(identities.strict_band.ne(True).sum()),
        date_conflicts=int(identities.date_conflict.eq(True).sum()),
        week_certain_date_conflicts=int((identities.date_conflict.eq(True) & identities.week.ne("")).sum()),
        selected_complete_weeks=len(weekly), selected_start=str(weekly.index.min().date()) if len(weekly) else None,
        selected_end=str(_offset(weekly.index.max(), 6).date()) if len(weekly) else None)
    return {"weekly": weekly, "identities": identities, "observations": observations,
            "coverage": coverage, "captions": CAPTIONS.copy()}


def correlation_pairs(weekly, exposure, outcome, lag=0, *, changes=True):
    """Shift on a complete calendar before dropping missing rows; never bridge gaps."""
    if exposure not in EXPOSURES or outcome not in OUTCOMES or lag not in {0, 1} or isinstance(lag, bool):
        raise ValueError("Choose a supported publication series, Spotify outcome and lag 0 or 1.")
    columns = ["x", "y", "target_week", "exposure_value", "outcome_value", "previous_source_week", "previous_target_week"]
    if weekly.empty:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], name="week_start"))
    _weekly_index(weekly.index)
    frame = weekly.sort_index().reindex(pd.date_range(weekly.index.min(), weekly.index.max(), freq="W-MON", name="week_start"))
    xraw = pd.to_numeric(frame[exposure], errors="coerce").astype(float)
    yraw = pd.to_numeric(frame[outcome], errors="coerce").astype(float)
    xraw = xraw.where(np.isfinite(xraw) & xraw.ge(0))
    yraw = yraw.where(np.isfinite(yraw) & (True if outcome == "net_followers" else yraw.ge(0)))
    if "spotify_days" in frame:
        yraw = yraw.where(frame.spotify_days.eq(7))
    x, y = np.log1p(xraw), np.arcsinh(yraw) if outcome == "net_followers" else np.log1p(yraw)
    if changes:
        x, y = x.diff(), y.diff()
    result = pd.DataFrame({"x": x, "y": y.shift(-lag), "target_week": _offset_index(frame.index, 7*lag),
        "exposure_value": xraw, "outcome_value": yraw.shift(-lag),
        "previous_source_week": _offset_index(frame.index, -7),
        "previous_target_week": _offset_index(frame.index, 7*(lag-1))}, index=frame.index)
    result = result.dropna(subset=["x", "y"])
    result.attrs.update(calendar_weeks=len(frame), missing_pair_weeks=len(frame)-len(result), lag_weeks=lag, changes=changes)
    return result


def _rho(x, y):
    if len(x) < 4 or x.nunique() < 2 or y.nunique() < 2:
        return float("nan")
    return float(x.rank(method="average").corr(y.rank(method="average")))


def describe_association(weekly, exposure, outcome, lag=0):
    pairs = correlation_pairs(weekly, exposure, outcome, lag)
    levels = correlation_pairs(weekly, exposure, outcome, lag, changes=False)
    rho = _rho(pairs.x, pairs.y)
    status = "available" if np.isfinite(rho) else "insufficient_pairs" if len(pairs) < 4 else "constant_series"
    return {"rho": rho, "n": len(pairs), "rho_levels": _rho(levels.x, levels.y), "n_levels": len(levels),
        "status": status, "exposure": exposure, "outcome": outcome, "lag_weeks": lag,
        "pairs": pairs, "missing_pair_weeks": pairs.attrs.get("missing_pair_weeks", 0),
        "caption": "Descriptive Spearman correlation of adjacent weekly changes. No confidence interval, p-value, predictive or causal inference is recomputed for this selection.",
        "method": "First differences of log(1 + weekly activity); signed net followers use asinh. Lag 1 pairs publication week t with Spotify week t+1."}


def load_reviewed_results(repo, analysis_dir=None):
    """Fail closed on source or reviewed-output drift; never fit inference in UI."""
    empty = {"status": "unavailable", "reason": "", "results": pd.DataFrame(), "sensitivity_2026": pd.DataFrame(),
             "manifest": {}, "captions": [], "source_mismatches": []}
    directory = Path(analysis_dir) if analysis_dir is not None else DEFAULT_ANALYSIS_DIR
    try:
        manifest = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
        sources = manifest["sources"]
        if len(sources) != len(SOURCE_PATHS) or {row["path"] for row in sources} != set(SOURCE_PATHS):
            raise ValueError("Reviewed manifest must contain each of the six required source assets exactly once.")
        catalog = repo.file_catalog()
        if catalog.path.duplicated().any():
            raise ValueError("Selected source catalog has duplicate paths.")
        hashes = catalog.set_index("path").sha256.to_dict()
        mismatches = [row["path"] for row in sources if hashes.get(row["path"]) != row["sha256"]]
        if mismatches:
            empty.update(reason="Reviewed inference is unavailable: source hashes differ or are missing in this selected version.", source_mismatches=mismatches)
            return empty
        verification = json.loads((directory / "source_audit/verification.json").read_text(encoding="utf-8"))
        if verification.get("status") != "arithmetic_verified_interpretation_requires_caveats" or not verification.get("checks") or not all(verification["checks"].values()):
            raise ValueError("Independent reviewed-result verification is unavailable or incomplete.")
        for filename in ("analysis.py", "analysis_plan.md", "correlations.csv", "correlations_2026_sensitivity.csv"):
            digest = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
            if verification.get("analysis_input_sha256", {}).get(filename) != digest:
                raise ValueError("Reviewed result or method files have changed since independent verification.")
            manifest_key = {"analysis.py": "script_sha256", "analysis_plan.md": "plan_sha256"}.get(filename)
            if manifest_key and manifest.get(manifest_key) != digest:
                raise ValueError("Reviewed method does not match the run manifest.")
        if verification.get("source_sha256") != {row["path"]: row["sha256"] for row in sources}:
            raise ValueError("Independent verification source hashes differ from the run manifest.")
        results = pd.read_csv(directory / "correlations.csv")
        sensitivity = pd.read_csv(directory / "correlations_2026_sensitivity.csv")
        expected = {(e, o, lag) for e in REVIEWED_EXPOSURES for o in OUTCOMES for lag in (0, 1)}
        if len(results) != 20 or set(results[["exposure", "outcome", "lag_weeks"]].itertuples(index=False, name=None)) != expected:
            raise ValueError("The complete reviewed 20-test family is required.")
        return {"status": "available", "reason": "All six source assets and independently reviewed result files match.",
            "results": results, "sensitivity_2026": sensitivity, "manifest": manifest, "verification": verification,
            "source_mismatches": [], "captions": [
                "Reviewed results are fixed to January 1, 2024–December 28, 2025 and the full 20-test family. Interactive dates do not change this inference.",
                "Intervals are approximate, pointwise and unadjusted. BH q values use all 20 planned tests; no result passes q < 0.05.",
                "The 2026 sensitivity is a separate limited-archive description, not predictive validation. Annual subsets use week-start year."]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        empty["reason"] = "Reviewed inference is unavailable: " + str(error)
        return empty
