"""Source inspection and chart presentation shared by audited analysis pages."""
import pandas as pd
import streamlit as st
from stats_app import dashboard_controls as controls


def fmt(value, digits=0):
    return "Unavailable" if value is None or pd.isna(value) else f"{float(value):,.{digits}f}"


def chart(fig, key=None, **layout):
    fig.update_layout(margin=dict(t=20,l=10,r=10,b=20), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(size=15, color="#f4f4f4"),
                      colorway=["#f4f4f4", "#a3a3a3", "#737373", "#d4d4d4", "#525252"],
                      legend=dict(orientation="h",y=-.18),
                      hoverlabel=dict(bgcolor="#171717", bordercolor="#737373", font_color="#f4f4f4"))
    fig.update_xaxes(gridcolor="rgba(255,255,255,.08)", zerolinecolor="#525252", linecolor="#525252")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.08)", zerolinecolor="#525252", linecolor="#525252")
    # The former brand accent becomes white; explicit semantic series colors,
    # missing-value gaps, trace order and chart-specific line styles are retained.
    for trace in fig.data:
        line = getattr(trace, "line", None)
        line_color = getattr(line, "color", None)
        if isinstance(line_color, str) and line_color.lower() == "#edd264":
            line.color = "#f4f4f4"
        marker = getattr(trace, "marker", None)
        marker_color = getattr(marker, "color", None)
        if isinstance(marker_color, str) and marker_color.lower() == "#edd264":
            marker.color = "#f4f4f4"
    if layout:
        fig.update_layout(**layout)
    st.plotly_chart(fig, width="stretch", key=key, config={"displaylogo":False})


def download(data, name, key):
    result = data.copy()
    for column in result.select_dtypes(include=["object", "string"]):
        result[column] = result[column].map(lambda v: "'"+v if isinstance(v,str) and v.startswith(("=","+","-","@")) else v)
    st.download_button("Download filtered records · CSV", result.to_csv(index=False).encode("utf-8-sig"), name,
                       "text/csv",key=key)


def evidence(repo, path, data, key, note=""):
    st.caption(f"Source table: {path}. {note}")
    controls.own_keys(key + "_evidence")
    panel = st.expander("Records, definitions and lineage", expanded=False,
                        key=key + "_evidence", on_change="rerun")
    with panel:
        st.dataframe(data, width="stretch", hide_index=True)
        download(data, path.split('/')[-1], key+"_csv")
        if panel.open:
            st.download_button("Download unchanged source table",repo.original_bytes(path),path.split('/')[-1],"text/csv",key=key+"_raw")
            dictionary = repo.table("data_dictionary.csv")
            if "table" in dictionary:
                definitions = dictionary.loc[dictionary.table.fillna("").astype(str).str.endswith(path.split('/')[-1])]
                if not definitions.empty:
                    st.dataframe(definitions, hide_index=True, width="stretch")
        st.caption("The source table preserves original source file/row and retrieval fields where supplied. Derived tables identify their input table; audit and source inventories remain available in Data quality.")
