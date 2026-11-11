"""TikTok ranking preparation with explicit native precision and source scope.

Native reporting-window order is authoritative. Cumulative counters are never
substituted for period values, and duplicate captions never establish identity.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import re
from urllib.parse import urlsplit

import pandas as pd


METRIC_LABELS = {"new-followers": "New followers", "views": "Video views",
                 "new-viewers": "New viewers", "likes": "Likes"}
SNAPSHOT_METRICS = {"new_followers_raw": "Acquired followers", "views_raw": "Views",
                    "likes_raw": "Likes", "saves_raw": "Saves", "shares_raw": "Shares"}
REQUIRED_RANKING_COLUMNS = {"ranking_metric", "window_days", "rank", "post_display",
                            "ranking_value_raw", "all_views_raw", "source_file"}


def native_number(value):
    """Return a chart-only numeric position plus precision; retain raw elsewhere."""
    if value is None or pd.isna(value):
        return None, "unavailable"
    text = str(value).strip()
    exact = re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", text)
    rounded = re.fullmatch(r"(\d+(?:\.\d+)?)([KM])", text, flags=re.IGNORECASE)
    if not exact and not rounded:
        return None, "unavailable"
    try:
        number = Decimal(text.replace(",", "")) if exact else Decimal(rounded[1]) * {"K": 1000, "M": 1000000}[rounded[2].upper()]
        result = float(number)
    except (InvalidOperation, ValueError, OverflowError):
        return None, "unavailable"
    if not math.isfinite(result):
        return None, "unavailable"
    return result, "exact" if exact else "rounded"


def caption_key(value):
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    # Studio adds a displayed duration on its own first line for some videos.
    text = re.sub(r"^\d{1,2}:\d{2}(?::\d{2})?\s*\n", "", text)
    return " ".join(text.split())


def public_post_url(value, post_id):
    """Only an observed public TikTok URL for this exact retained identity."""
    if not isinstance(value, str) or not isinstance(post_id, str) or not post_id:
        return ""
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme == "https" and parsed.hostname in {"www.tiktok.com", "tiktok.com"}
        invalid_parts = parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment
    except ValueError:
        return ""
    if not valid or invalid_parts:
        return ""
    return value if re.fullmatch(r"/@[^/]+/video/" + re.escape(post_id), parsed.path) else ""


def _identity_map(inventory):
    if inventory.empty or not {"caption_raw", "post_id"}.issubset(inventory.columns):
        return {}
    data = inventory.copy()
    data["caption_key"] = data.caption_raw.map(caption_key)
    result = {}
    for key, group in data.loc[data.caption_key.ne("")].groupby("caption_key", sort=False):
        if len(group) != 1 or group.post_id.isna().any():
            result[key] = ("", "", "ambiguous_caption")
            continue
        row = group.iloc[0]
        post_id = str(row.post_id)
        url = public_post_url(row.get("canonical_url", ""), post_id)
        result[key] = (post_id, url, "unique_caption_match" if url else "unique_caption_no_public_url")
    return result


def prepare_native_rankings(rankings, inventory):
    """Return all source rows, with safe optional identities and plot positions."""
    if rankings.empty or not REQUIRED_RANKING_COLUMNS.issubset(rankings.columns):
        result = pd.DataFrame()
        result.attrs["unavailable_reason"] = "This collection does not retain the metric and window fields needed for strongest-post rankings."
        return result
    data = rankings.copy(deep=True).fillna("")
    data["window_days_numeric"] = pd.to_numeric(data.window_days, errors="coerce")
    data["rank_numeric"] = pd.to_numeric(data["rank"], errors="coerce")
    data["caption"] = data.post_display.map(caption_key)
    identities = _identity_map(inventory)
    joined = [identities.get(key, ("", "", "unmatched_caption")) for key in data.caption]
    data[["post_id", "public_url", "identity_status"]] = pd.DataFrame(joined, index=data.index)
    parsed = [native_number(value) for value in data.ranking_value_raw]
    data[["plot_value", "value_precision"]] = pd.DataFrame(parsed, index=data.index)
    data["metric_label"] = data.ranking_metric.map(METRIC_LABELS).fillna(data.ranking_metric)
    data["counter_scope"] = "Reporting-window metric; All views is a separate cumulative display"
    return data


def select_native_rankings(data, window_days, metric, source_file, search=""):
    if data.empty:
        return data.copy()
    result = data.loc[data.window_days_numeric.eq(window_days) & data.ranking_metric.eq(metric)
                      & data.source_file.eq(source_file)].copy()
    if not result.empty and (result.rank_numeric.isna().any() or result.rank_numeric.duplicated().any()
                             or (result.rank_numeric < 1).any() or (result.rank_numeric % 1 != 0).any()):
        raise ValueError("The selected native ranking has invalid or repeated ranks; its captures must remain separate.")
    if search.strip():
        text = search.strip()
        mask = result[["caption", "post_id"]].astype(str).apply(lambda c: c.str.contains(text, case=False, regex=False)).any(axis=1)
        result = result.loc[mask]
    return result.sort_values("rank_numeric", kind="stable").reset_index(drop=True)


def ranking_period(panels, window_days):
    required = {"window_days", "reporting_start", "reporting_end"}
    if panels.empty or not required.issubset(panels.columns):
        return None
    rows = panels.loc[pd.to_numeric(panels.window_days, errors="coerce").eq(window_days), ["reporting_start", "reporting_end"]].dropna()
    rows = rows.loc[rows.reporting_start.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}") & rows.reporting_end.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}")].drop_duplicates()
    if len(rows) != 1:
        return None
    start, end = rows.iloc[0].tolist()
    try:
        if (pd.Timestamp(end) - pd.Timestamp(start)).days + 1 != window_days:
            return None
    except ValueError:
        return None
    return start, end


def prepare_snapshot_rankings(summary, inventory, metric="new_followers_raw", search=""):
    """Approximate ordering of cumulative snapshots; rounded values stay labeled."""
    if summary.empty or "post_id" not in summary or metric not in summary:
        return pd.DataFrame()
    if summary.post_id.duplicated().any() or (not inventory.empty and "post_id" in inventory and inventory.post_id.duplicated().any()):
        raise ValueError("Post snapshots need one retained row per post identity.")
    data = summary.copy(deep=True).fillna("")
    inv_cols = [c for c in ["post_id", "caption_raw", "canonical_url"] if c in inventory]
    if "post_id" in inv_cols:
        data = data.merge(inventory[inv_cols], on="post_id", how="left", validate="one_to_one", suffixes=("", "_inventory")).fillna("")
    data["caption"] = data.get("caption_raw", pd.Series("", index=data.index)).map(caption_key)
    data["public_url"] = [public_post_url(row.get("canonical_url", ""), str(row.post_id)) for _, row in data.iterrows()]
    data["ranking_value_raw"] = data[metric]
    parsed = [native_number(value) for value in data[metric]]
    data[["plot_value", "value_precision"]] = pd.DataFrame(parsed, index=data.index)
    data["counter_scope"] = "Cumulative post snapshot; unequal ages and capture times"
    if search.strip():
        data = data.loc[data[["caption", "post_id"]].astype(str).apply(lambda c: c.str.contains(search.strip(), case=False, regex=False)).any(axis=1)]
    return data.sort_values("plot_value", ascending=False, kind="stable", na_position="last").reset_index(drop=True)
