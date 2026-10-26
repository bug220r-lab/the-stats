"""Sidebar page links; selection stays compatible with dashboard shortcuts."""
import streamlit as st

from stats_app.dashboard_controls import navigate


PRIMARY_PAGES = ("Overview", "Spotify", "YouTube collection", "Social", "Shopify", "Cross-platform")
MORE_PAGES = ("Decision report", "Campaigns", "Meta collection", "Import data",
              "Data quality", "Snapshot explorer", "Sources & provenance",
              "Coverage & cross-reference")


def navigation_regions():
    """Reserve navigation above source controls, which determine available pages."""
    st.markdown("""
        <style>
        .st-key-primary-navigation button,
        .st-key-more-navigation button {
            justify-content: flex-start;
            text-align: left;
        }
        .st-key-primary-navigation button > div,
        .st-key-more-navigation button > div {
            justify-content: flex-start;
        }
        .st-key-primary-navigation button[kind="primary"],
        .st-key-more-navigation button[kind="primary"] {
            color: #111111;
        }
        .st-key-primary-navigation button[kind="secondary"],
        .st-key-more-navigation button[kind="secondary"] {
            background: transparent;
            border-color: transparent;
        }
        .st-key-primary-navigation button:hover,
        .st-key-more-navigation button:hover {
            border-color: #edd264;
        }
        .st-key-primary-navigation button p { font-weight: 600; }
        </style>
    """, unsafe_allow_html=True)
    primary = st.sidebar.container(key="primary-navigation", gap="small")
    st.sidebar.divider()
    selected = st.session_state.get("explore_page", "Overview")
    more = st.sidebar.expander("More", expanded=selected not in PRIMARY_PAGES)
    secondary = more.container(key="more-navigation", gap="small")
    return primary, secondary, more


def render_navigation(pages, primary, secondary):
    """Keep every available page reachable, with only one active page link."""
    if st.session_state.get("explore_page") not in pages:
        st.session_state["explore_page"] = pages[0]
    selected = st.session_state["explore_page"]
    main_pages = [page for page in PRIMARY_PAGES if page in pages]
    other_pages = [page for page in MORE_PAGES if page in pages]
    # Future pages remain reachable even before being assigned a preferred order.
    other_pages.extend(page for page in pages if page not in main_pages + other_pages)
    for container, group in ((primary, main_pages), (secondary, other_pages)):
        with container:
            for page in group:
                st.button("YouTube" if page == "YouTube collection" else page,
                          key="nav:" + page, width="stretch",
                          type="primary" if page == selected else "secondary",
                          on_click=navigate, args=(page,))
    return selected
