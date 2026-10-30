"""Common, explicit source identity; reporting and capture dates never substitute."""
from dataclasses import dataclass
import streamlit as st


@dataclass(frozen=True)
class SourceContext:
    source_id: str
    label: str
    account: str = "Not supplied"
    reporting_start: str = "Source-specific"
    reporting_end: str = "Source-specific"
    timezone: str = "Unknown / source-specific"
    captured_at: str = "Not supplied"
    availability: str = "Available"


def render_context(context):
    st.caption(f"{context.availability} · Account: {context.account} · Reporting: {context.reporting_start} → {context.reporting_end} · {context.timezone}")
    st.caption(f"Source: {context.label} · Version: {context.source_id} · Capture: {context.captured_at}")


def repository_context(repo, *, spotify=False):
    metadata = repo.metadata
    store = metadata.get("store") or {}
    if not isinstance(store, dict):
        store = {}
    key = str(getattr(repo, "registered_key", metadata.get("collection_key", metadata.get("analysis_version", "saved source"))))
    label = str(getattr(repo, "registered_label", metadata.get("label", key)))
    account = (metadata.get("account_display_name") or metadata.get("account") or metadata.get("channel_name")
               or metadata.get("channel") or metadata.get("store") or "Not supplied")
    if isinstance(account, dict):
        account = account.get("name", account.get("handle", account.get("domain", str(account))))
    start, end, zone = metadata.get("reporting_start") or "Source-specific", metadata.get("reporting_end") or "Source-specific", metadata.get("reporting_timezone") or metadata.get("source_timezone") or store.get("timezone") or "Unknown / source-specific"
    if spotify and "spotify/cleaned/artist_daily.csv" in repo.tables:
        daily = repo.table("spotify/cleaned/artist_daily.csv")
        if not daily.empty:
            start, end, zone = str(daily.date.min()), str(daily.date.max()), "UTC · Spotify activity"
            if "artist_id" in daily:
                account = "Spotify artist " + ", ".join(daily.artist_id.dropna().astype(str).unique())
    elif "social/account_daily.csv" in repo.tables:
        social = repo.table("social/account_daily.csv")
        if not social.empty:
            account = ", ".join(social.account_handle.dropna().astype(str).unique())
            start, end = "Social account activity " + str(social.date.min()), str(social.date.max())
            zone = "Pacific · social account activity; other evidence has its own dates"
    periods = metadata.get("reporting_periods", [])
    if periods and not spotify:
        starts = [str(p.get("reporting_start")) for p in periods if p.get("reporting_start")]
        ends = [str(p.get("reporting_end")) for p in periods if p.get("reporting_end")]
        if starts and ends:
            start, end = min(starts), max(ends)
    captured = (metadata.get("collected_at") or metadata.get("retrieval_date") or metadata.get("retrieval_vintage")
                or "Not supplied; see row provenance")
    return SourceContext(key, label, str(account), start, end, str(zone), str(captured), "Available · retained evidence")
