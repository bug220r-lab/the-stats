"""Local presentation assets for the band; independent of analytical data."""
import streamlit as st

from stats_app.config import PROJECT_ROOT


ASSET_DIR = PROJECT_ROOT / "assets" / "branding"
LOGO_PATH = ASSET_DIR / "couch-sticker-original.png"


def render_brand_header() -> None:
    """Keep a single compact brand block in the sidebar, using original artwork."""
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            padding-top: 4.5rem;
        }
        .st-key-sidebar-brand [data-testid="stMarkdownContainer"] p {
            font-size: 1.125rem;
            font-weight: 600;
            line-height: 1.2;
            margin: 0;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid #333330;
        }
        [data-testid="stMetric"] {
            border-top: 2px solid #edd264;
            padding: 0.8rem 0.3rem 0.4rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar.container(key="sidebar-brand", gap="small"):
        if LOGO_PATH.is_file():
            st.image(str(LOGO_PATH), width=125)
        else:
            st.markdown("[REDACTED]")
        st.markdown("The Stats™")

