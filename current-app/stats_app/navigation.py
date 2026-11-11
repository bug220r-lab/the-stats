"""Native Streamlit pages with stable URLs and compatible analytical shortcuts."""
from functools import partial
import streamlit as st

PAGE_GROUPS = {
    "Overview": ("Overview",),
    "Explore": ("Spotify", "Apple Music", "YouTube collection", "Social", "TikTok", "Linktree", "Shopify"),
    "Analysis": ("Growth diagnostics", "Cross-platform", "TikTok insights", "Content plan", "Decision report", "Saved diagnosis"),
    "Data & tools": ("Data quality", "Sources & provenance", "Snapshot explorer", "Coverage & cross-reference",
                     "Meta collection", "Campaigns", "Import data"),
}
PAGE_PATHS = {
    "Overview": "overview", "Spotify": "spotify", "Apple Music": "apple-music",
    "YouTube collection": "youtube", "Social": "social", "TikTok": "tiktok", "Linktree": "linktree", "Shopify": "shopify",
    "Growth diagnostics": "growth", "Cross-platform": "cross-platform", "TikTok insights": "tiktok-insights", "Content plan": "content-plan", "Decision report": "decision-report",
    "Saved diagnosis": "saved-diagnosis", "Data quality": "data-quality", "Sources & provenance": "sources",
    "Snapshot explorer": "snapshots", "Coverage & cross-reference": "coverage", "Meta collection": "meta-collection",
    "Campaigns": "campaigns", "Import data": "import",
}


def run_navigation(render_page):
    """Register once and execute only the selected page, even if unavailable."""
    grouped, routes = {}, {}
    for group, names in PAGE_GROUPS.items():
        grouped[group] = []
        for name in names:
            page = st.Page(partial(render_page, name), title="YouTube" if name == "YouTube collection" else name,
                           url_path=PAGE_PATHS[name], default=name == "Overview")
            grouped[group].append(page)
            routes[name] = page
    selected = st.navigation(grouped, position="sidebar", expanded=True)
    st.session_state["_native_routes"] = routes
    requested = st.session_state.pop("_requested_page", None)
    if requested in routes and routes[requested].url_path != selected.url_path:
        st.switch_page(routes[requested])
    name = next(name for name, page in routes.items() if page.url_path == selected.url_path)
    st.session_state["explore_page"] = name
    selected.run()
