"""Monochrome band presentation, independent of analytical data and storage."""
import streamlit as st

from stats_app.config import PROJECT_ROOT


ASSET_DIR = PROJECT_ROOT / "assets" / "branding"
LOGO_PATH = ASSET_DIR / "couch-sticker-original.png"


def render_brand_header() -> None:
    """Keep a single compact brand block in the sidebar, using original artwork."""
    st.markdown(
        """
        <style>
        :root {
            --stats-ink: #080808;
            --stats-panel: #111111;
            --stats-rule: #383838;
            --stats-white: #f4f4f4;
            --stats-muted: #b8b8b8;
            --stats-terminal: Consolas, "Cascadia Mono", "Courier New", monospace;
        }
        [data-testid="stAppViewContainer"] {
            background-color: var(--stats-ink);
            background-image: linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
            background-size: 64px 100%;
        }
        [data-testid="stMainBlockContainer"] {
            padding-top: 3rem;
            padding-bottom: 4rem;
            max-width: 1480px;
        }
        [data-testid="stMain"] { font-size: 1rem; }
        h1 {
            font-family: var(--stats-terminal);
            font-weight: 700;
            letter-spacing: -.055em;
            text-transform: uppercase;
            padding-bottom: 1.1rem;
            border-bottom: 1px solid var(--stats-rule);
        }
        h2, h3 { letter-spacing: -.025em; }
        [data-testid="stCaptionContainer"] { color: var(--stats-muted); }
        [data-testid="stVerticalBlock"] { gap: 1.15rem; }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.75rem; }
        [data-testid="stSidebar"] {
            background-color: #060606;
            background-image: repeating-linear-gradient(0deg, transparent 0 35px, rgba(255,255,255,.025) 35px 36px);
            border-right: 1px solid var(--stats-rule);
        }
        [data-testid="stSidebarNav"] a {
            border-radius: 2px;
            border-left: 2px solid transparent;
            padding-top: .5rem;
            padding-bottom: .5rem;
            transition: background-color .12s ease;
        }
        [data-testid="stSidebarNav"] a:hover { background: #191919; }
        [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: #202020;
            border-left-color: var(--stats-white);
            color: #fff;
        }
        [data-testid="stSidebarNav"] header {
            font-family: var(--stats-terminal);
            font-size: .7rem;
            text-transform: uppercase;
            letter-spacing: .14em;
            color: var(--stats-muted);
        }
        button:focus-visible, a:focus-visible, input:focus-visible,
        textarea:focus-visible, [role="combobox"]:focus-visible {
            outline: 2px solid #fff !important;
            outline-offset: 3px;
        }
        .st-key-sidebar-brand {
            border-top: 1px solid var(--stats-rule);
            padding-top: 1.1rem;
        }
        .st-key-sidebar-brand [data-testid="stMarkdownContainer"] p {
            font-family: var(--stats-terminal);
            font-size: 1.05rem;
            font-weight: 700;
            line-height: 1.2;
            letter-spacing: .13em;
            text-transform: uppercase;
            margin: 0;
        }
        .st-key-sidebar-brand [data-testid="stCaptionContainer"] {
            font-family: var(--stats-terminal);
            font-size: .65rem;
            letter-spacing: .1em;
        }
        [data-testid="stMetric"] {
            border: 1px solid var(--stats-rule);
            border-top: 2px solid var(--stats-white);
            border-radius: 2px;
            background: var(--stats-panel);
            padding: 1.25rem;
        }
        [data-testid="stMetricLabel"] {
            font-family: var(--stats-terminal);
            letter-spacing: .025em;
        }
        [data-testid="stMetricValue"] {
            font-variant-numeric: tabular-nums;
            letter-spacing: -.045em;
        }
        [data-testid="stButton"] button,
        [data-testid="stDownloadButton"] button,
        [data-testid="stExpander"] {
            border-radius: 2px;
        }
        [data-testid="stButton"] button,
        [data-testid="stDownloadButton"] button {
            border-color: #505050;
            font-weight: 600;
        }
        [data-testid="stButton"] button:hover,
        [data-testid="stDownloadButton"] button:hover {
            border-color: #fff;
        }
        [data-testid="stExpander"] {
            border-color: var(--stats-rule);
            background: rgba(17,17,17,.6);
        }
        [data-testid="stDataFrame"], [data-testid="stTable"] {
            border: 1px solid var(--stats-rule);
        }
        @media (prefers-reduced-motion: reduce) {
            [data-testid="stSidebarNav"] a { transition: none; }
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
        st.caption("[ MUSIC + SOCIAL ]")

