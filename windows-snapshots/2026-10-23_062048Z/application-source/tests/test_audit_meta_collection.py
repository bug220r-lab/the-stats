import pytest

from scripts.audit_meta_collection import strict_csv, story_overview, sql_summary


def test_collection_audit_rejects_ragged_normalized_table(tmp_path):
    path = tmp_path / "wide.csv"
    path.write_text("post_id,views,reach\n123,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Ragged"):
        strict_csv(path)


def test_story_overview_requires_labels_and_values_from_same_six_column_table():
    text = "\n".join(f"{i} text {v}" for i, v in enumerate(["Views", "Reach", "Interactions", "Link clicks", "Sticker taps", "Instagram follows", "31 ‑‑ 2 ‑‑ ‑‑ ‑‑"], 1))
    row = story_overview(text)
    assert row == {"views": "31", "reach": "‑‑", "interactions": "2", "link_clicks": "‑‑", "sticker_taps": "‑‑", "follows": "‑‑"}
    with pytest.raises(ValueError, match="six observed labels"):
        story_overview(text.replace("31 ‑‑ 2 ‑‑ ‑‑ ‑‑", "31 ‑‑ 2 ‑‑ ‑‑"))
    with pytest.raises(ValueError, match="absent"):
        story_overview(text.replace("Instagram follows", "Facebook follows"))


def test_independent_sql_audit_rejects_cross_export_ad_day_double_counting():
    row = dict(source_file="first.csv", ad_account_id="123", ad_id="456", reporting_start="2026-10-20", reporting_end="2026-10-20", **{"Amount spent (USD)": "0", "Impressions": "0", "Link clicks": ""})
    result = sql_summary([row])
    assert result[0]["observed_spend_rows"] == 1 and result[0]["observed_click_rows"] == 0
    with pytest.raises(ValueError, match="Overlapping"):
        sql_summary([row, {**row, "source_file": "second.csv"}])


def test_independent_sql_audit_rejects_duplicate_native_grain():
    row = dict(source_file="first.csv", ad_account_id="123", ad_id="456", reporting_start="2026-10-20", reporting_end="2026-10-20")
    with pytest.raises(ValueError, match="Duplicate"):
        sql_summary([row, row])
