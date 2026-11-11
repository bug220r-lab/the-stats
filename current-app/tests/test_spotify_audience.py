"""Retained audience interpretation protects scope, unknowns and source bytes."""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from stats_app.analysis_repository import AnalysisRepository
from stats_app.spotify_audience import (
    ARTIST_DAILY, PERIOD_AUDIENCE, RECOVERED_AUDIENCE,
    SEGMENT_CAPTURE, SEGMENT_DAILY, audience_movement, audience_segment_daily,
    exact_retained_period_audience, super_listener_history,
)


class MemoryRepo:
    def __init__(self, tables=None, assets=None):
        self.frames = tables or {}
        self.assets = assets or {}
        self.tables = list(self.frames)

    def table(self, path):
        return self.frames[path].copy(deep=True)

    def original_bytes(self, path):
        return self.assets[path]

    def text(self, path):
        return self.original_bytes(path).decode("utf-8-sig")

    def file_catalog(self):
        return pd.DataFrame({"path": list(self.assets) + self.tables})


def capture(value='"309"', scope="Worldwide"):
    return (f'- /url: /c/artist/artist1/audience/stats\n'
            f'- paragraph: Oct 20, 2026 • {scope}\n'
            f'- paragraph: Last 28 days • {scope}\n'
            '- generic: Reactivated listeners\n- button "Help icon":\n'
            f'- generic: {value}\n'
            '- generic: New active listeners\n- button "Help icon":\n- generic: "153"\n'
            '- generic: New listeners\n- button "Help icon":\n- generic: "350"\n').encode()


def periods_and_recovered():
    periods = pd.DataFrame([dict(metric="listeners", start_date="2026-01-01", end_date="2026-10-20",
                                scope="Worldwide", snapshot_class="original_baseline", artist_id="artist1",
                                reporting_timezone="UTC", current_value=9419, previous_value=3558,
                                current_status="available", previous_status="available",
                                previous_period_start="2025-03-14", previous_period_end="2025-12-31",
                                source_file="native-period.csv", source_row=32)])
    recovered = pd.DataFrame([{
        "Scope": "artist", "Spotify ID": "artist1", "Period start": "2025-01-01", "Period end": "2025-10-20",
        "Metric": "period_unique_listeners", "Population": "Worldwide", "Value": 3077,
        "reporting_timezone": "UTC", "snapshot_class": "baseline_supplement",
        "Method": "Direct dashboard period total; manually transcribed, not a sum of daily listeners",
        "source_file": "recovered.csv", "source_row": 2, "Collected UTC": "2026-10-23 (UTC date only)",
    }])
    return periods, recovered


def test_segment_history_preserves_unknown_and_row_lineage():
    raw = ("date,total_audience,monthly_active_listeners,previously_active,programmed,super_listeners,moderate_listeners,light_listeners,measurement_type,source\n"
           "2026-10-19,12344,792,4672,6880,,231,516,rolling_audience_stock,chart.json\n"
           "2026-10-20,12351,791,4672,6888,47,230,514,rolling_audience_stock,chart.json\n").encode()
    repo = MemoryRepo(assets={SEGMENT_DAILY: raw})
    result = audience_segment_daily(repo)
    assert pd.isna(result.iloc[0].super_listeners)
    assert result.iloc[-1].super_listeners == 47
    assert result.source_csv_record.tolist() == [2, 3]
    assert result.source_sha256.eq(hashlib.sha256(raw).hexdigest()).all()
    assert repo.original_bytes(SEGMENT_DAILY) == raw
    duplicated = raw + raw.splitlines(keepends=True)[-1]
    with pytest.raises(ValueError, match="duplicate"):
        audience_segment_daily(MemoryRepo(assets={SEGMENT_DAILY: duplicated}))


def test_movement_scoped_source_capture_and_missing_is_not_zero():
    raw = capture()
    repo = MemoryRepo(assets={SEGMENT_CAPTURE: raw})
    result = audience_movement(repo)
    assert result.value.tolist() == [309, 153, 350]
    assert result.period_start.eq("2026-09-23").all() and result.period_end.eq("2026-10-20").all()
    assert result.source_line.notna().all()
    assert result.source_sha256.eq(hashlib.sha256(raw).hexdigest()).all()
    assert repo.original_bytes(SEGMENT_CAPTURE) == raw
    missing = audience_movement(MemoryRepo(assets={SEGMENT_CAPTURE: capture('"—"')}))
    assert pd.isna(missing.iloc[0].value) and missing.iloc[0].value_status == "unavailable"
    assert missing.iloc[1].value == 153  # Never borrow the next label's count.
    wrong_scope = audience_movement(MemoryRepo(assets={SEGMENT_CAPTURE: capture(scope="United States")}))
    assert wrong_scope.value.isna().all() and wrong_scope.period_end.isna().all()


def test_super_history_masks_unavailable_and_keeps_overlapping_stocks():
    daily = pd.DataFrame({"date": ["2026-10-19", "2026-10-20"], "rolling28_super_listeners": [45, 47],
                          "artist_id": ["artist1"] * 2, "snapshot_class": ["original_baseline"] * 2,
                          "reporting_timezone": ["UTC"] * 2, "value_status": ["unavailable", "observed"]})
    repo = MemoryRepo(tables={ARTIST_DAILY: daily})
    result = super_listener_history(repo)
    assert pd.isna(result.iloc[0].rolling28_super_listeners)
    assert result.iloc[-1].rolling28_super_listeners == 47
    assert len(super_listener_history(repo, "2026-10-20", "2026-10-20")) == 1
    assert repo.table(ARTIST_DAILY).iloc[0].rolling28_super_listeners == 45


def test_recovered_direct_matching_prior_fills_ytd_without_rewriting_native():
    periods, recovered = periods_and_recovered()
    repo = MemoryRepo(tables={PERIOD_AUDIENCE: periods, RECOVERED_AUDIENCE: recovered})
    row = exact_retained_period_audience(repo, "2026-01-01", "2026-10-20",
                                         previous_start="2025-01-01", previous_end="2025-10-20")
    assert row.current_value == 9419 and row.previous_value == 3077
    assert row.percent_change == pytest.approx((9419 / 3077 - 1) * 100)
    assert row.previous_source_asset == RECOVERED_AUDIENCE
    assert row.previous_snapshot_class == "baseline_supplement"
    assert row.native_previous_value == 3558
    assert row.native_previous_period_start == "2025-03-14"
    pd.testing.assert_frame_equal(repo.table(PERIOD_AUDIENCE), periods)
    # Its compatible native comparison remains valid when no prior-year
    # interval was requested; the recovery never replaces an existing match.
    native = exact_retained_period_audience(repo, "2026-01-01", "2026-10-20")
    assert native.previous_value == 3558 and native.previous_source_asset == PERIOD_AUDIENCE


@pytest.mark.parametrize("column,value", [
    ("Population", "United States"), ("Spotify ID", "other-artist"),
    ("reporting_timezone", "America/Los_Angeles"), ("Period start", "2025-01-02"),
    ("Method", "Sum of daily unique listeners"), ("Value", -1),
])
def test_incompatible_recovery_cannot_fill_missing_denominator(column, value):
    periods, recovered = periods_and_recovered()
    recovered[column] = value
    repo = MemoryRepo(tables={PERIOD_AUDIENCE: periods, RECOVERED_AUDIENCE: recovered})
    row = exact_retained_period_audience(repo, "2026-01-01", "2026-10-20",
                                         previous_start="2025-01-01", previous_end="2025-10-20")
    assert not row.comparison_available and row.previous_value is None and row.percent_change is None


def test_ambiguous_recovery_rows_remain_unavailable():
    periods, recovered = periods_and_recovered()
    repo = MemoryRepo(tables={PERIOD_AUDIENCE: periods, RECOVERED_AUDIENCE: pd.concat([recovered, recovered])})
    row = exact_retained_period_audience(repo, "2026-01-01", "2026-10-20",
                                         previous_start="2025-01-01", previous_end="2025-10-20")
    assert not row.comparison_available


def test_current_retained_audience_assets_are_readable():
    # Optional package fixture keeps private data out of tests; when available
    # this checks actual archived CSV/text formats against the interpretation.
    db = Path(__file__).resolve().parents[1] / "data/reconciliation/staged_analysis/analysis.sqlite3"
    if not db.exists():
        pytest.skip("Private source package unavailable")
    repo = AnalysisRepository(db)
    if SEGMENT_DAILY not in set(repo.file_catalog().path):
        pytest.skip("This historical package omits retained audience assets")
    segments = audience_segment_daily(repo)
    assert len(segments) == 28 and segments.date.min() == "2026-09-23" and segments.date.max() == "2026-10-20"
    assert segments.iloc[-1].total_audience == 12351
    assert audience_movement(repo).value.tolist() == [309, 153, 350]
    assert len(super_listener_history(repo)) == 1024
