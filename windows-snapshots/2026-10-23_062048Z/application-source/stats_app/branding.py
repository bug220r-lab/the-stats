"""Local presentation assets for the band; independent of analytical data."""
import streamlit as st

from stats_app.config import PROJECT_ROOT


ASSET_DIR = PROJECT_ROOT / "assets" / "branding"
LOGO_PATH = ASSET_DIR / "couch-sticker-original.png"


def render_brand_header() -> None:
    """Show the original Drive artwork without external requests or image edits."""
    st.markdown(
        """
        <style>
        .st-key-band-header {
            border-bottom: 1px solid #3b3b39;
            margin-bottom: 1.5rem;
            padding-bottom: 1.15rem;
        }
        .st-key-band-header h1 {
            letter-spacing: -0.055em;
            font-size: clamp(2.4rem, 4vw, 3.5rem);
            line-height: 1.02;
            padding-top: 0;
        }
        .st-key-band-header [data-testid="stCaptionContainer"] {
            color: #c7c6bf;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid #333330;
        }
        [data-testid="stMetric"] {
            border-top: 2px solid #edd264;
            padding: 0.8rem 0.3rem 0.4rem 0;
        }
        @media (max-width: 640px) {
            .st-key-band-header { margin-bottom: 1rem; }
            .st-key-band-header [data-testid="stImage"] { max-width: 200px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="band-header"):
        title, artwork = st.columns([3, 1.15], vertical_alignment="center")
        with title:
            st.caption("[REDACTED]  /  BAND ANALYTICS")
            st.title("The Stats™️")
            st.caption("Streaming & social analytics · source-backed snapshots")
        if LOGO_PATH.is_file():
            with artwork:
                st.image(str(LOGO_PATH), width="stretch")
    with st.sidebar:
        if LOGO_PATH.is_file():
            st.image(str(LOGO_PATH), width=190)
        else:
            st.subheader("[REDACTED]")
        st.caption("THE STATS™️ · BAND WORKSPACE")

