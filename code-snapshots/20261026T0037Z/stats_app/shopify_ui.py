"""Read-only merchandise views for a separately dated Shopify collection.

Native report grains, missingness and the current inventory snapshot stay distinct.
The presentation layer never derives a sales history from order or inventory rows.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_app.analysis_ui_common import chart


NUMERIC_STATUSES = {"observed", "reported", "zero", "collected", "complete"}
UNAVAILABLE_STATUSES = {"unavailable", "blocked", "not_collected", "not_yet_collected"}
WINDOWS = ("Last 7 completed days", "Last 28 completed days", "Last 90 completed days",
           "Year to date", "All available completed days")
MONEY_METRICS = {"gross_sales", "discounts", "returns", "net_sales", "shipping", "shipping_charges",
                 "taxes", "duties", "total_sales", "average_order_value", "amount", "revenue",
                 "sales", "attributed_sales", "total_price", "price", "unit_cost", "cost", "profit", "sales_reversals",
                 "gross_payments", "refunded_payments", "net_payments", "shopify_payments_processing_fees",
                 "foreign_exchange_fees", "managed_markets_fees", "international_fees", "payout_amount", "payout_amount_in_payout_currency"}
RATE_METRICS = {"conversion_rate", "online_store_conversion_rate", "returning_customer_rate"}
FINANCIAL_METRICS = ("gross_payments", "refunded_payments", "net_payments", "shopify_payments_processing_fees",
                     "foreign_exchange_fees", "managed_markets_fees", "international_fees", "payout_amount", "payout_amount_in_payout_currency")
LABELS = {"orders": "Orders", "total_sales": "Total sales", "net_sales": "Net sales",
          "gross_sales": "Gross sales", "units_sold": "Units sold", "net_quantity": "Net units sold", "net_items_sold": "Net items sold",
          "average_order_value": "Average order value", "sessions": "Sessions",
          "visitors": "Visitors", "online_store_visitors": "Online store visitors",
          "sessions_with_cart_additions": "Sessions with cart additions",
          "sessions_that_reached_checkout": "Sessions reaching checkout",
          "sessions_that_completed_checkout": "Sessions completing checkout"}


def numeric_values(data: pd.DataFrame, metric: str) -> pd.Series:
    """Read finite source numbers; an unavailable numeric-looking cell stays absent."""
    if metric not in data:
        return pd.Series(float("nan"), index=data.index, dtype=float)
    values = pd.to_numeric(data[metric], errors="coerce").astype(float)
    values = values.where(values.abs().lt(float("inf")))
    status_column = next((name for name in (metric + "_status", metric + "_value_status") if name in data), None)
    if status_column:
        values = values.where(data[status_column].fillna("").astype(str).str.lower().isin(NUMERIC_STATUSES))
    return values


def collection_day(metadata: dict) -> date | None:
    """Anchor stored-snapshot windows to collection time in the verified store clock."""
    stamp = metadata.get("collected_at") or metadata.get("collected_at_utc")
    timezone = metadata.get("store", {}).get("timezone")
    if not stamp or not timezone:
        return None
    try:
        captured = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if captured.tzinfo is None:
            return None
        return captured.astimezone(ZoneInfo(timezone)).date()
    except (ValueError, KeyError):
        return None


def window_bounds(label: str, captured_day: date, earliest: date, latest: date) -> tuple[date, date]:
    """Return requested native calendar bounds without silently shortening a preset."""
    end = captured_day - timedelta(days=1)
    if label.startswith("Last "):
        return end - timedelta(days=int(label.split()[1]) - 1), end
    if label == "Year to date":
        return date(captured_day.year, 1, 1), end
    return earliest, min(latest, end)


def comparison_bounds(label: str, start: date, end: date) -> tuple[date, date] | None:
    if label == "All available completed days":
        return None
    if label == "Year to date":
        def prior_year(day):
            return date(day.year - 1, day.month, min(day.day, calendar.monthrange(day.year - 1, day.month)[1]))
        return prior_year(start), prior_year(end)
    return start - timedelta(days=(end - start).days + 1), start - timedelta(days=1)


def definition_breaks(metadata: dict, start: date, end: date) -> list[dict]:
    """Return source-recorded definition changes crossing the displayed interval."""
    result = []
    for item in metadata.get("source_definition_breaks", []):
        if isinstance(item, str):
            item = {"date": item}
        if not isinstance(item, dict):
            continue
        try:
            changed = date.fromisoformat(str(item.get("date") or item.get("effective_date"))[:10])
        except ValueError:
            continue
        if start < changed <= end:
            result.append({**item, "date": changed.isoformat()})
    return result


def daily_window(data: pd.DataFrame, date_column: str, start: date, end: date,
                 metrics: tuple[str, ...] | list[str]) -> tuple[pd.DataFrame, dict]:
    """Require one retained date row and one numeric value per requested day/metric."""
    labels = data[date_column].fillna("").astype(str)
    selected = data.loc[labels.between(start.isoformat(), end.isoformat())].copy()
    expected = max(0, (end - start).days + 1)
    valid_dates = pd.to_datetime(selected[date_column], format="%Y-%m-%d", errors="coerce")
    reported = int(valid_dates.nunique())
    duplicate_dates = bool(selected[date_column].duplicated().any())
    numeric_days = {metric: int(numeric_values(selected, metric).notna().sum()) for metric in metrics}
    complete_dates = expected > 0 and reported == expected and not duplicate_dates and len(selected) == expected
    return selected, {"expected_days": expected, "reported_days": reported,
                      "missing_days": max(0, expected - reported), "duplicate_dates": duplicate_dates,
                      "complete_dates": complete_dates, "numeric_days": numeric_days,
                      "complete_metrics": {metric: complete_dates and count == expected
                                           for metric, count in numeric_days.items()}}


def complete_sum(data: pd.DataFrame, metric: str, coverage: dict) -> float | None:
    if not coverage["complete_metrics"].get(metric, False):
        return None
    return float(numeric_values(data, metric).sum(min_count=1))


def completed_checkout_rate(data: pd.DataFrame, coverage: dict) -> float | None:
    """One source-defined funnel: completed-checkout sessions / online-store sessions."""
    numerator = complete_sum(data, "sessions_that_completed_checkout", coverage)
    denominator = complete_sum(data, "sessions", coverage)
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def weighted_daily_aov(data: pd.DataFrame, coverage: dict) -> float | None:
    """Weight native daily AOV by source orders, never average daily averages."""
    orders = complete_sum(data, "orders", coverage)
    if orders is None or orders <= 0 or "average_order_value" not in data:
        return None
    weights = numeric_values(data, "orders")
    active = weights.gt(0)
    values = numeric_values(data, "average_order_value")
    if values.loc[active].isna().any() or weights.lt(0).any():
        return None
    return float((values.loc[active] * weights.loc[active]).sum() / orders)


def safe_csv_bytes(data: pd.DataFrame) -> bytes:
    """Keep public catalog formula text inert while preserving numeric negatives."""
    result = data.copy()
    def safe_cell(value):
        if not isinstance(value, str) or not value.lstrip().startswith(("=", "+", "-", "@")):
            return value
        # A literal finite signed number remains a number; '-1+2' remains inert text.
        if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
            try:
                if Decimal(value).is_finite():
                    return value
            except InvalidOperation:
                pass
        return "'" + value
    for column in result.select_dtypes(include=["object", "string"]):
        result[column] = result[column].map(safe_cell)
    return result.to_csv(index=False).encode("utf-8-sig")


def _label(name: str) -> str:
    return LABELS.get(name, name.replace("_", " ").capitalize())


def _format(value, metric: str, currency="USD") -> str:
    if value is None or pd.isna(value):
        return "Unavailable"
    if metric in MONEY_METRICS or metric.endswith(("_sales", "_revenue", "_cost")):
        return f"{currency} {value:,.2f}"
    if metric in RATE_METRICS:
        return f"{value:.2%}"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _datasets(repo) -> list[dict]:
    return repo.datasets.fillna("").to_dict("records")


def _id(item: dict) -> str:
    return str(item.get("dataset_id", item.get("id", "")))


def _find(repo, *names) -> dict | None:
    for name in names:
        for item in _datasets(repo):
            if _id(item) == name:
                return item
    return None


def _data(repo, item: dict) -> pd.DataFrame:
    return repo.table(_id(item)) if item.get("path") else pd.DataFrame()


def _status(item: dict):
    status = str(item.get("status", "unavailable"))
    reason = str(item.get("reason", item.get("detail", "")))
    message = f"{item.get('label') or _label(_id(item))}: {status.replace('_', ' ')}. {reason}".strip()
    if status in UNAVAILABLE_STATUSES:
        st.info(message)
    elif status == "partial":
        st.warning(message)
    elif status in {"verified_empty", "verified empty"}:
        st.info(message)
    elif reason:
        st.caption(message)


def _scope(item: dict):
    facts = []
    if item.get("reporting_start") or item.get("reporting_end"):
        facts.append(f"Reporting: {item.get('reporting_start') or 'unknown'} – {item.get('reporting_end') or 'unknown'}")
    for field in ("grain", "timezone", "source_timezone", "currency", "report_name", "scope", "attribution_model", "attribution_window"):
        value = item.get(field)
        if value and not isinstance(value, (dict, list)):
            facts.append(f"{field.replace('_', ' ')}: {value}")
    if facts:
        st.caption(" · ".join(facts))
    for field in ("definition", "scope_note"):
        if item.get(field):
            st.caption(str(item[field]))


def _records(data: pd.DataFrame, item: dict, key: str, *, expanded=False):
    with st.expander("Records and source details", expanded=expanded):
        st.caption(f"{len(data):,} filtered records · {item.get('path', 'No retained table')}. Blank values remain unavailable.")
        if not data.empty:
            page_count = max(1, (len(data) + 249) // 250)
            page_key = key + "_page"
            if st.session_state.get(page_key, 1) > page_count:
                st.session_state.pop(page_key, None)
            page = int(st.number_input("Record page (250 rows)", min_value=1, max_value=page_count,
                                       value=1, key=page_key)) if page_count > 1 else 1
            st.dataframe(data.iloc[(page - 1) * 250:page * 250], hide_index=True, width="stretch")
        else:
            st.info("The native report is verified empty for its recorded scope; no rows are invented."
                    if item.get("status") in {"verified_empty", "verified empty"} else
                    "No retained rows match this view. An empty selection does not establish zero activity.")
        st.download_button("Download filtered records · CSV", safe_csv_bytes(data),
                           _id(item) + "_filtered.csv", "text/csv", key=key + "_download")
        _scope(item)
        for field in ("filters", "dimensions", "source_refs", "source_paths", "query", "definitions"):
            if item.get(field):
                st.write(field.replace("_", " ").capitalize() + ":", item[field])


def _dimension_filters(data: pd.DataFrame, columns: tuple[str, ...], key: str) -> pd.DataFrame:
    for column in columns:
        if column not in data or data.empty:
            continue
        options = sorted(data[column].fillna("").astype(str).unique())
        if len(options) < 2:
            continue
        selected = st.multiselect(_label(column) + " · empty means all", options,
                                  format_func=lambda value: value or "(not supplied)", key=key + "_" + column)
        if selected:
            data = data.loc[data[column].fillna("").astype(str).isin(selected)]
    return data


def _date_column(data: pd.DataFrame) -> str | None:
    return next((column for column in ("date", "day", "activity_date", "reporting_date") if column in data), None)


def _daily_metric_columns(data: pd.DataFrame) -> list[str]:
    preferred = ("total_sales", "orders", "units_sold", "net_quantity", "net_items_sold", "average_order_value", "net_sales", "gross_sales", "discounts", "returns", "sales_reversals",
                 "shipping", "shipping_charges", "taxes", "duties", "sessions", "visitors", "online_store_visitors",
                 "sessions_with_cart_additions", "sessions_that_reached_checkout", "sessions_that_completed_checkout", "conversion_rate",
                 *FINANCIAL_METRICS)
    return [column for column in preferred if column in data]


def heading(repo):
    metadata = repo.metadata
    store = metadata.get("store", {})
    st.subheader("Shopify merchandise")
    st.caption(" · ".join(str(store.get(name) or "Unknown " + name) for name in ("name", "domain", "currency", "timezone")))
    st.caption(f"Collected {metadata.get('collected_at') or metadata.get('collected_at_utc') or 'timestamp unavailable'}. "
               "Reporting dates describe store activity; inventory and catalog describe their collection-time snapshot.")
    st.caption("This separately dated collection preserves the existing October 20 reporting baseline and saved analysis versions.")
    if store.get("installed_channels"):
        st.caption("Installed channels: " + ", ".join(store["installed_channels"]) + ". "
                   + ("Channels with observed sales: " + ", ".join(store["sales_channels_observed"]) + "."
                      if store.get("sales_channels_observed") else ""))


def _daily_sales(repo, item: dict, data: pd.DataFrame, *, key="shopify_sales", traffic=False):
    day_column = _date_column(data)
    metrics = _daily_metric_columns(data)
    captured = collection_day(repo.metadata)
    parsed = pd.to_datetime(data[day_column], format="%Y-%m-%d", errors="coerce") if day_column else pd.Series(dtype="datetime64[ns]")
    if day_column is None or not metrics or captured is None or parsed.dropna().empty:
        st.info("Completed-day windows require a retained daily report and a verified store clock and collection timestamp.")
        _records(data, item, key, expanded=True)
        return
    label = st.selectbox("Shopify reporting window", WINDOWS, index=4, key=key + "_window")
    start, end = window_bounds(label, captured, parsed.min().date(), parsed.max().date())
    selected, coverage = daily_window(data, day_column, start, end, metrics)
    comparison = comparison_bounds(label, start, end)
    prior_data, prior_coverage = (daily_window(data, day_column, *comparison, metrics) if comparison
                                else (data.iloc[0:0], {"complete_metrics": {}}))
    if traffic:
        changes = definition_breaks(repo.metadata, comparison[0] if comparison else start, end)
        for change in changes:
            st.warning(f"Session measurement changed on {change['date']}. "
                       + str(change.get("description") or change.get("reason") or change.get("note") or "The source marks a definition break.")
                       + " Comparisons spanning that change are withheld; totals spanning the change combine source definitions.")
        if changes:
            prior_coverage["complete_metrics"] = {metric: False for metric in metrics}
    if item.get("status") not in {"collected", "complete"}:
        coverage["complete_metrics"] = {metric: False for metric in metrics}
        prior_coverage["complete_metrics"] = {metric: False for metric in metrics}
        st.warning("This report's dataset status does not establish complete collection. Window totals remain unavailable.")
    st.caption(f"{start.isoformat()} – {end.isoformat()} inclusive · {repo.metadata.get('store', {}).get('timezone', 'Unknown clock')}. "
               f"{coverage['reported_days']:,} of {coverage['expected_days']:,} required date rows retained.")
    if not coverage["complete_dates"]:
        st.warning("This selected window lacks one unique source row for every required date. "
                   "Window totals and comparisons are unavailable; retained observations are shown below.")
    elif any(not complete for metric, complete in coverage["complete_metrics"].items()
             if metric not in RATE_METRICS | {"average_order_value"}):
        st.warning("Some daily metric values are unavailable. Totals are withheld for those metrics.")
    currency = repo.metadata.get("store", {}).get("currency") or "Currency unknown"
    primary = [metric for metric in (("sessions", "online_store_visitors", "sessions_that_completed_checkout") if traffic
                                    else ("total_sales", "orders", "units_sold", "net_quantity", "net_items_sold")) if metric in metrics]
    # Visitors are distinct within the source period and must not be summed across days.
    primary = [metric for metric in primary if metric != "online_store_visitors"]
    has_aov = not traffic and "average_order_value" in data and "orders" in data
    period_visitors = None
    if traffic:
        native_summary = _find(repo, "traffic_summary")
        if (native_summary and native_summary.get("status") == "collected"
                and native_summary.get("reporting_start") == start.isoformat()
                and native_summary.get("reporting_end") == end.isoformat()):
            summary_data = _data(repo, native_summary)
            if len(summary_data) == 1 and "online_store_visitors" in summary_data:
                candidate = numeric_values(summary_data, "online_store_visitors").iloc[0]
                if pd.notna(candidate):
                    period_visitors = candidate
    cards = st.columns(max(1, len(primary) + (1 if traffic or has_aov else 0) + (1 if period_visitors is not None else 0)))
    for slot, metric in zip(cards, primary):
        current_value = complete_sum(selected, metric, coverage)
        previous_value = complete_sum(prior_data, metric, prior_coverage)
        delta = None if current_value is None or previous_value is None else f"{current_value - previous_value:+,.2f} vs comparison"
        slot.metric(_label(metric), _format(current_value, metric, currency), delta=delta, delta_color="off")
    if comparison:
        available_comparison = all(prior_coverage["complete_metrics"].get(metric, False) for metric in primary)
        st.caption(f"Comparison: {comparison[0].isoformat()} – {comparison[1].isoformat()} inclusive. "
                   + ("Card changes are absolute differences from this complete source period." if available_comparison
                      else "A complete compatible comparison is unavailable; affected changes are withheld."))
    if traffic:
        rate = completed_checkout_rate(selected, coverage)
        cards[len(primary)].metric("Completed-checkout session rate", "Unavailable" if rate is None else f"{rate:.2%}")
        if period_visitors is not None:
            cards[-1].metric("Visitors · exact source period", f"{period_visitors:,.0f}")
        st.caption("Completed-checkout session rate = sessions completing checkout ÷ online-store sessions. "
                   "It excludes other sales channels. Daily distinct visitors are not summed into period visitors.")
        if period_visitors is not None:
            st.caption("Visitor total is read from the native period summary with these exact dates; it is separate from the daily chart.")
    else:
        if has_aov:
            cards[-1].metric("Average order value", _format(weighted_daily_aov(selected, coverage), "average_order_value", currency))
            st.caption("Selected-period AOV weights each reported daily average by its order count. "
                       "It uses available source precision and excludes post-order adjustments; zero orders produce unavailable AOV.")
        st.caption("Sales retain the native report definition. Payments, payouts and profit are separate measures.")
    if metrics:
        metric = st.selectbox("Shopify daily metric", metrics, format_func=_label, key=key + "_metric")
        if not selected.empty and not coverage["duplicate_dates"]:
            # Only gap markers are drawn: missing dates must never become a continuous curve.
            shown = selected.sort_values(day_column)
            values = numeric_values(shown, metric)
            fig = go.Figure(go.Scatter(x=shown[day_column].tolist(), y=values.tolist(), mode="markers",
                                      name=_label(metric), connectgaps=False, marker={"color": "#edd264"}))
            fig.update_layout(height=340, xaxis_title="Store calendar date", yaxis_title=_label(metric) +
                              (f" ({currency})" if metric in MONEY_METRICS else ""))
            if metric in RATE_METRICS:
                fig.update_yaxes(tickformat=".1%")
            chart(fig, key + "_daily_chart")
            st.caption("Each marker is a retained daily observation; missing dates and unavailable values remain gaps.")
    _records(selected, item, key)
    current_rows = data.loc[data[day_column].fillna("").astype(str).ge(captured.isoformat())]
    if not current_rows.empty:
        st.caption(f"{len(current_rows):,} collection-day or later rows are excluded from completed-day windows.")


def _native_report(repo, item: dict, key: str):
    _status(item)
    _scope(item)
    if item.get("current_day_included") or "current day incomplete" in str(item.get("grain", "")):
        st.warning("This report includes the incomplete collection day. Its native observations are separate from completed-day windows and comparisons.")
    data = _data(repo, item)
    if data.empty:
        if item.get("path"):
            _records(data, item, key, expanded=True)
        return
    data = _dimension_filters(data, ("channel", "channel_name", "source_name", "referrer_source", "referrer_medium",
                                     "device_type", "country", "customer_type", "financial_status", "fulfillment_status"), key)
    metrics = _daily_metric_columns(data)
    # A single native period row is shown as source evidence, never apportioned into days.
    if len(data) == 1 and metrics:
        choices = (("sessions", "online_store_visitors", "sessions_that_completed_checkout", "conversion_rate")
                   if _id(item) == "traffic_summary" else
                   ("total_sales", "orders", "average_order_value", "net_quantity", "net_items_sold", "units_sold", "sessions"))
        if any(metric in metrics for metric in FINANCIAL_METRICS):
            choices = FINANCIAL_METRICS
        primary = [name for name in choices if name in metrics][:4]
        slots = st.columns(max(1, len(primary)))
        for slot, metric in zip(slots, primary):
            value = numeric_values(data, metric).iloc[0]
            slot.metric(_label(metric), _format(value, metric, repo.metadata.get("store", {}).get("currency", "Unknown currency")))
        st.caption("Directly reported source-period values; no daily allocation or period comparison is inferred.")
    dimension = next((name for name in ("sales_channel", "channel", "channel_name", "product_title", "device_type", "device",
                                        "referrer_source", "customer_type", "country", "discount_code") if name in data), None)
    if dimension and 1 < len(data) <= 100 and metrics and not data[dimension].duplicated().any():
        metric = st.selectbox("Shopify breakdown metric", metrics, format_func=_label, key=key + "_breakdown_metric")
        shown = data.copy()
        shown["_shown_value"] = numeric_values(shown, metric)
        shown = shown.sort_values("_shown_value", ascending=True, na_position="first")
        fig = go.Figure(go.Bar(x=shown["_shown_value"].tolist(), y=shown[dimension].tolist(), orientation="h",
                              name=_label(metric), marker_color="#edd264"))
        fig.update_layout(height=max(300, min(650, 35 * len(shown))), xaxis={"title": _label(metric), "rangemode": "tozero"})
        chart(fig, key + "_breakdown_chart")
        st.caption("Each bar is one native report row. Unknown values remain absent; no source rows are combined.")
    _records(data, item, key, expanded=True)


def render_sales(repo):
    item = _find(repo, "sales_daily", "daily_sales", "sales_over_time")
    if item is not None:
        _status(item)
        _scope(item)
        data = _data(repo, item)
        if not data.empty:
            _daily_sales(repo, item, data)
        else:
            _records(data, item, "shopify_sales_empty", expanded=True)
    else:
        item = _find(repo, "sales_summary", "sales_totals", "sales")
        if item:
            _native_report(repo, item, "shopify_sales_summary")
        else:
            st.info("No sales report is retained in this collection. This is not evidence of zero sales.")
    detail = [row for row in _datasets(repo) if _id(row) in {"sales_summary", "sales_today", "orders", "line_items", "sales_by_product", "sales_by_variant", "sales_by_channel", "sales_discounts", "discounts"}]
    if detail:
        selected = st.selectbox("Sales detail report", [_id(row) for row in detail], format_func=_label, key="shopify_sales_detail")
        _native_report(repo, next(row for row in detail if _id(row) == selected), "shopify_sales_detail_records")


def render_catalog(repo):
    available = [row for row in _datasets(repo) if _id(row) in {"products", "variants", "inventory", "inventory_levels", "locations", "channels", "collections", "inventory_history"}]
    st.caption("Current catalog and stock are dated snapshots. Native inventory history remains a separate source report; "
               "today's stock does not fill past dates or describe units sold.")
    if not available:
        st.info("Catalog and inventory reports were not retained in this collection.")
        return
    selected = st.selectbox("Catalog or inventory table", [_id(row) for row in available], format_func=_label, key="shopify_catalog_table")
    item = next(row for row in available if _id(row) == selected)
    _status(item)
    data = _data(repo, item)
    data = _dimension_filters(data, ("status", "product_status", "product_type", "category", "location_name", "tracked", "inventory_tracked", "inventory_policy"), "shopify_catalog_" + selected)
    if selected == "variants":
        data = _dimension_filters(data, ("title",), "shopify_catalog_variant_title")
    elif selected in {"inventory", "inventory_levels", "inventory_history"}:
        data = _dimension_filters(data, ("variant_title",), "shopify_catalog_inventory_variant")
    query = st.text_input("Find a product, variant or SKU", key="shopify_catalog_search")
    if query.strip() and not data.empty:
        columns = [column for column in data if any(token in column for token in ("title", "name", "sku", "handle", "product_id", "variant_id"))]
        if columns:
            mask = pd.Series(False, index=data.index)
            for column in columns:
                mask |= data[column].fillna("").astype(str).str.contains(query.strip(), regex=False, case=False)
            data = data.loc[mask]
    day_column = _date_column(data)
    if selected == "inventory_history" and day_column and not data.empty:
        parsed = pd.to_datetime(data[day_column], format="%Y-%m-%d", errors="coerce").dropna()
        if not parsed.empty:
            bounds = st.date_input("Shopify inventory history dates", (parsed.min().date(), parsed.max().date()),
                                   min_value=parsed.min().date(), max_value=parsed.max().date(), key="shopify_inventory_dates")
            if len(bounds) == 2:
                data = data.loc[data[day_column].astype(str).between(bounds[0].isoformat(), bounds[1].isoformat())]
            else:
                st.info("Choose both history dates to inspect the retained range.")
                data = data.iloc[0:0]
    if selected in {"inventory", "inventory_levels"} and not data.empty:
        stock = numeric_values(data, "available")
        keys = [column for column in ("inventory_item_id", "location_id") if column in data]
        if len(keys) == 2 and not data.duplicated(keys).any() and stock.notna().all():
            st.metric("Available stock · selected item/location rows", f"{stock.sum():,.0f}")
    _records(data, item, "shopify_catalog_records_" + selected, expanded=True)


def _report_group(repo, names: tuple[str, ...], key: str, note: str):
    categories = {"shopify_traffic": {"traffic"}, "shopify_marketing": {"marketing", "customers"},
                  "shopify_operations": {"fulfillment", "shipping", "costs", "payments"}}.get(key, set())
    excluded = {"traffic_daily", "sessions_daily"} if key == "shopify_traffic" else set()
    rows = [row for row in _datasets(repo) if _id(row) not in excluded
            and (_id(row) in names or row.get("category") in categories)]
    st.caption(note)
    if not rows:
        st.info("No supported report in this area was retained. See Coverage & sources for dataset availability.")
        return
    selected = st.selectbox("Shopify report", [_id(row) for row in rows], format_func=_label, key=key + "_report")
    _native_report(repo, next(row for row in rows if _id(row) == selected), key)


def render_traffic(repo):
    daily = _find(repo, "traffic_daily", "sessions_daily")
    if daily:
        _status(daily)
        _scope(daily)
        data = _data(repo, daily)
        if not data.empty:
            _daily_sales(repo, daily, data, key="shopify_traffic_daily", traffic=True)
    _report_group(repo, ("sessions", "traffic_summary", "conversion_funnel", "conversion_daily", "traffic_devices", "traffic_geography",
                         "traffic_referrers", "traffic_landing", "traffic_by_device", "traffic_by_geography", "landing_pages", "referrers"), "shopify_traffic",
                  "Traffic describes online-store sessions at the source's grain. Checkout sessions are not interchangeable with all-channel orders. "
                  "Cart, checkout and completion counts are independently defined session stages; they need not form a closed or monotonic funnel. "
                  "Rates retain the report's numerator, denominator and attribution scope; unavailable or zero denominators cannot produce a derived rate.")


def render_marketing(repo):
    _report_group(repo, ("marketing", "marketing_attribution", "attribution", "referrer_sales", "referrers", "utm_campaigns", "discounts",
                         "sales_customer_type", "sales_discounts", "customer_daily", "customer_summary", "customer_records_summary", "discount_codes", "customers_summary", "customers", "customer_cohorts", "customer_geography", "customer_signup_sources", "new_returning_customers",
                         "campaign_landing", "campaign_sessions", "campaign_sales"),
                  "shopify_marketing", "Attribution is descriptive source reporting. It does not establish that a campaign caused a purchase. "
                  "Customer evidence is aggregate; customer names and contact details are excluded.")


def render_operations(repo):
    _report_group(repo, ("fulfillment", "fulfillment_summary", "shipping", "shipping_methods", "product_costs", "costs", "profit", "payments",
                         "fulfillments", "shipping_lines", "transactions", "refund_lines", "profit_coverage", "payments_daily", "payments_summary", "fees_daily", "fees_summary", "payouts_daily", "payouts_summary", "payout_schedule", "inventory_history_summary", "payment_fees", "refunds", "payouts", "payout_summary"), "shopify_operations",
                  "Sales, product costs, profit, payments, refunds and payouts use different definitions and timing. "
                  "Missing costs or fees do not establish zero expense or a profit margin.")


def render_shopify_coverage(repo, key="shopify_coverage"):
    st.subheader("Shopify coverage")
    data = repo.datasets.copy()
    st.caption("Collected, partial, verified empty, unavailable and blocked describe each specific dataset and its retained scope. "
               "A collection date is separate from the reporting period. Full-store history is verified only when explicitly recorded.")
    columns = [name for name in ("dataset_id", "label", "status", "reason", "reporting_start", "reporting_end", "grain",
                                 "full_history_verified", "path") if name in data]
    st.dataframe(data[columns], hide_index=True, width="stretch")
    st.download_button("Download dataset coverage · CSV", safe_csv_bytes(data), "shopify_dataset_coverage.csv",
                       "text/csv", key=key + "_download")


def render_shopify_sources(repo, key="shopify_sources"):
    st.subheader("Shopify retained sources")
    st.caption("Retained source files, sanitized normalized tables and hashes identify this collection. "
               "Filtered CSV downloads neutralize spreadsheet formulas; source downloads preserve retained bytes.")
    sources = repo.sources()
    if sources.empty:
        st.info("No source files are recorded.")
        return
    st.dataframe(sources, hide_index=True, width="stretch")
    path = st.selectbox("Shopify retained source", sources.path.astype(str).tolist(), key=key + "_path")
    content = repo.source_bytes(path)
    st.download_button("Download unchanged retained source", content, path.rsplit("/", 1)[-1], key=key + "_source_download")
    if path in getattr(repo, "tables", ()) and st.checkbox("Inspect retained CSV records", key=key + "_inspect"):
        item = next((row for row in _datasets(repo) if row.get("path") == path), {"dataset_id": path.rsplit("/", 1)[-1], "path": path})
        data = repo.table(path)
        _records(data, item, key + "_records", expanded=True)
        if hasattr(repo, "row_provenance") and st.checkbox("Show stable row provenance", key=key + "_lineage"):
            st.dataframe(repo.row_provenance(path), hide_index=True, width="stretch")
    with st.expander("Collection manifest and definitions"):
        st.json(repo.metadata, expanded=False)


def render_coverage_sources(repo):
    render_shopify_coverage(repo)
    render_shopify_sources(repo)


def render_shopify_collection(repo):
    heading(repo)
    views = {"Sales & orders": render_sales, "Catalog & inventory": render_catalog,
             "Traffic & conversion": render_traffic, "Marketing & customers": render_marketing,
             "Fulfillment & costs": render_operations, "Coverage & sources": render_coverage_sources}
    selected = st.selectbox("Shopify view", list(views), key="shopify_view_selector")
    views[selected](repo)


def render_shopify_entry(repo, kind, key):
    with st.expander("Shopify collection · " + str(repo.metadata.get("collected_at", "dated collection"))[:10]):
        st.caption("Separate merchandise collection; open Shopify for sales, catalog, inventory and retained reporting scopes.")
        if st.checkbox("Inspect Shopify " + kind, key=key + "_open"):
            (render_shopify_sources if kind == "sources" else render_shopify_coverage)(repo, key=key)
