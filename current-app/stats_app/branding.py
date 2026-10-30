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
            padding-top: 3rem;
            padding-bottom: 4rem;
            max-width: 1480px;
        }
        [data-testid="stMain"] { font-size: 1rem; }
        h1 { letter-spacing: -0.03em; }
        h2, h3 { letter-spacing: -0.015em; }
        [data-testid="stVerticalBlock"] { gap: 1.15rem; }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.75rem; }
        [data-testid="stSidebarNav"] a { border-radius: 8px; padding-top: .45rem; padding-bottom: .45rem; }
        [data-testid="stSidebarNav"] a[aria-current="page"] { background: #35301d; }
        button:focus-visible, a:focus-visible, input:focus-visible {
            outline: 3px solid #edd264 !important; outline-offset: 3px;
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
            border: 1px solid #39382f;
            border-top: 2px solid #edd264;
            border-radius: 10px;
            background: #1c1c1b;
            padding: 1.25rem;
        }
        @media (max-width: 700px) {
            [data-testid="stMainBlockContainer"] { padding: 2.5rem 1rem; }
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
            [data-testid="stColumn"] { min-width: min(100%, 300px); flex: 1 1 300px; }
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

