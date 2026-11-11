"""Shopify presentation calculations and isolated Streamlit interaction checks."""
from datetime import date
import json

import pandas as pd
from streamlit.testing.v1 import AppTest

from stats_app.shopify_ui import (collection_day, comparison_bounds, complete_sum, completed_checkout_rate, definition_breaks,
                                  daily_window, numeric_values, safe_csv_bytes, weighted_daily_aov, window_bounds)


def test_native_clock_and_snapshot_windows_do_not_advance_with_today():
    metadata = {"collected_at": "2026-10-25T02:30:00+00:00", "store": {"timezone": "America/New_York"}}
    captured = collection_day(metadata)
    assert captured == date(2026, 10, 24)
    assert window_bounds("Last 7 completed days", captured, date(2025, 12, 23), date(2026, 10, 24)) == (
        date(2026, 10, 17), date(2026, 10, 23))
    assert window_bounds("Year to date", captured, date(2025, 12, 23), date(2026, 10, 24)) == (
        date(2026, 1, 1), date(2026, 10, 23))
    assert collection_day({"collected_at": "2026-10-25T02:30:00", "store": {"timezone": "America/New_York"}}) is None


def test_missing_dates_and_numeric_statuses_withhold_totals_without_mutation():
    data = pd.DataFrame({"day": ["2026-10-01", "2026-10-03"], "total_sales": ["0", "15.20"],
                         "total_sales_status": ["zero", "unavailable"]})
    selected, coverage = daily_window(data, "day", date(2026, 10, 1), date(2026, 10, 3), ["total_sales"])
    assert coverage["missing_days"] == 1 and not coverage["complete_dates"]
    assert complete_sum(selected, "total_sales", coverage) is None
    values = numeric_values(data, "total_sales")
    assert values.iloc[0] == 0 and pd.isna(values.iloc[1])
    assert data.iloc[1].total_sales == "15.20"


def test_duplicate_dates_are_not_aggregated_across_report_dimensions():
    data = pd.DataFrame({"day": ["2026-10-01", "2026-10-01"], "orders": ["1", "2"]})
    selected, coverage = daily_window(data, "day", date(2026, 10, 1), date(2026, 10, 1), ["orders"])
    assert coverage["duplicate_dates"] and not coverage["complete_dates"]
    assert complete_sum(selected, "orders", coverage) is None


def test_weighted_aov_and_session_rate_preserve_denominators():
    data = pd.DataFrame({"day": ["2026-10-01", "2026-10-02", "2026-10-03"],
                         "orders": ["1", "3", "0"], "average_order_value": ["10", "30", ""],
                         "sessions": ["10", "90", "0"], "sessions_that_completed_checkout": ["1", "1", "0"]})
    selected, coverage = daily_window(data, "day", date(2026, 10, 1), date(2026, 10, 3),
                                      ["orders", "sessions", "sessions_that_completed_checkout"])
    assert weighted_daily_aov(selected, coverage) == 25
    assert completed_checkout_rate(selected, coverage) == .02
    data.loc[1, "average_order_value"] = ""
    assert weighted_daily_aov(data, coverage) is None
    data.loc[:, "sessions"] = "0"
    assert completed_checkout_rate(data, coverage) is None


def test_source_negative_refunds_remain_numeric_and_csv_formula_text_is_inert():
    data = pd.DataFrame({"title": [" =HYPERLINK()", "+untrusted", "safe"], "sales_reversals": [-21.98, 0., 0.]})
    text = safe_csv_bytes(data).decode("utf-8-sig")
    assert "' =HYPERLINK()" in text and "'+untrusted" in text
    assert "-21.98" in text
    assert data.iloc[0].title == " =HYPERLINK()"
    assert numeric_values(pd.DataFrame({"value": ["-21.98", "inf", ""]}), "value").isna().tolist() == [False, True, True]
    signed = safe_csv_bytes(pd.DataFrame({"value": ["-21.98", "-1+2", "+0.5", "-Infinity"]})).decode("utf-8-sig")
    assert "'-21.98" not in signed and "'+0.5" not in signed
    assert "'-1+2" in signed and "'-Infinity" in signed


def test_comparisons_keep_complete_rolling_period_and_matching_ytd_dates():
    assert comparison_bounds("Last 7 completed days", date(2026, 10, 18), date(2026, 10, 24)) == (
        date(2026, 10, 11), date(2026, 10, 17))
    assert comparison_bounds("Year to date", date(2026, 1, 1), date(2026, 10, 24)) == (
        date(2025, 1, 1), date(2025, 10, 24))
    assert comparison_bounds("All available completed days", date(2025, 12, 23), date(2026, 10, 24)) is None


def test_session_definition_break_is_scoped_to_crossing_periods():
    metadata = {"source_definition_breaks": [{"date": "2026-09-21", "reason": "Native session method changed"}]}
    assert len(definition_breaks(metadata, date(2026, 1, 1), date(2026, 10, 24))) == 1
    assert not definition_breaks(metadata, date(2026, 9, 21), date(2026, 10, 24))


def _app_script(sales_status="collected", changes=()):
    """Synthetic data stays inside the test script and is never imported to a library."""
    metadata = {"collected_at": "2026-10-25T05:00:00+00:00", "store": {
        "name": "Synthetic test store", "domain": "fixture.invalid", "timezone": "America/New_York", "currency": "USD"}}
    metadata["source_definition_breaks"] = list(changes)
    sales = [{"day": day.strftime("%Y-%m-%d"), "orders": "0", "total_sales": "0", "net_items_sold": "0", "average_order_value": ""}
             for day in pd.date_range("2026-10-18", "2026-10-25")]
    sales[1].update(orders="1", total_sales="20.00", net_items_sold="2", average_order_value="15.00")
    # Collection day is deliberately huge: completed windows must exclude it.
    sales[-1].update(orders="99", total_sales="9999.00", net_items_sold="99", average_order_value="101")
    tables = {"sales_daily": sales,
              "variants": [{"product_title": "Test shirt", "variant_title": "Small", "sku": "TEST-S", "status": "ACTIVE", "price": "10.00"},
                           {"product_title": "Test shirt", "variant_title": "Large", "sku": "TEST-L", "status": "ACTIVE", "price": "10.00"}],
              "traffic_daily": [{"day": day.strftime("%Y-%m-%d"), "sessions": "10", "online_store_visitors": "8",
                                 "sessions_that_completed_checkout": "1", "sessions_with_cart_additions": "0", "sessions_that_reached_checkout": "2"}
                                for day in pd.date_range("2026-10-18", "2026-10-24")],
              "profit_coverage": []}
    datasets = [{"dataset_id": name, "path": "normalized/" + name + ".csv", "label": name,
                 "status": (sales_status if name == "sales_daily" else "collected") if name != "profit_coverage" else "unavailable",
                 "reason": "Costs not recorded" if name == "profit_coverage" else "Synthetic test evidence",
                 "grain": "daily" if name.endswith("daily") else "snapshot"} for name in tables]
    return f'''import pandas as pd
from stats_app.shopify_ui import render_shopify_collection
import json
class FixtureRepository:
    metadata = json.loads({json.dumps(json.dumps(metadata))})
    datasets = pd.DataFrame(json.loads({json.dumps(json.dumps(datasets))}))
    def table(self, dataset):
        return pd.DataFrame(json.loads({json.dumps(json.dumps(tables))})[dataset])
    def sources(self):
        return pd.DataFrame([{{"path": "normalized/variants.csv", "sha256": "test-only", "bytes": 0}}])
    def source_bytes(self, path):
        return b"test-only"
render_shopify_collection(FixtureRepository())
'''


def _choose(app, label, value):
    next(widget for widget in app.selectbox if widget.label == label).set_value(value).run()
    assert not app.exception and not app.error


def test_streamlit_complete_window_excludes_current_day_and_partial_preset():
    app = AppTest.from_string(_app_script(), default_timeout=30).run()
    assert not app.exception and not app.error
    # A 28-day preset cannot be shortened to the seven supplied days.
    _choose(app, "Shopify reporting window", "Last 28 completed days")
    assert app.metric[0].value == "Unavailable"
    _choose(app, "Shopify reporting window", "Last 7 completed days")
    assert [item.value for item in app.metric] == ["USD 20.00", "1", "2", "USD 15.00"]
    assert any("collection-day" in caption.value for caption in app.caption)
    assert len(app.dataframe[0].value) == 7
    assert "2026-10-25" not in set(app.dataframe[0].value.day)


def test_streamlit_catalog_search_and_traffic_source_denominators():
    app = AppTest.from_string(_app_script(), default_timeout=30).run()
    _choose(app, "Shopify view", "Catalog & inventory")
    assert len(app.dataframe[0].value) == 2
    next(widget for widget in app.text_input if widget.label == "Find a product, variant or SKU").set_value("TEST-L").run()
    assert not app.exception
    assert app.dataframe[0].value.sku.tolist() == ["TEST-L"]
    _choose(app, "Shopify view", "Traffic & conversion")
    _choose(app, "Shopify reporting window", "Last 7 completed days")
    assert [item.value for item in app.metric] == ["70", "7", "10.00%"]
    assert any("independently defined" in caption.value for caption in app.caption)
    _choose(app, "Shopify view", "Fulfillment & costs")
    assert any("Costs not recorded" in item.value for item in app.info)
    assert not app.metric


def test_streamlit_partial_source_is_not_promoted_to_complete_by_date_count():
    app = AppTest.from_string(_app_script(sales_status="partial"), default_timeout=30).run()
    assert not app.exception and not app.error
    assert [item.value for item in app.metric] == ["Unavailable"] * 4
    assert any("does not establish complete collection" in item.value for item in app.warning)


def test_streamlit_traffic_definition_break_is_visible_for_crossing_history():
    app = AppTest.from_string(_app_script(changes=[{"date": "2026-10-21", "reason": "Test definition break"}]), default_timeout=30).run()
    _choose(app, "Shopify view", "Traffic & conversion")
    assert any("Session measurement changed on 2026-10-21" in item.value for item in app.warning)
    assert any("Test definition break" in item.value for item in app.warning)
