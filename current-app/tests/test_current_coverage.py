"""Current notices follow selected evidence, not acquisition-time prose."""
import pandas as pd

from stats_app.analysis_content import CONTENT_PATH
from stats_app.analysis_coverage import FOLLOW_REPAIR, current_coverage


class Repo:
    metadata = {"analysis_version": "test"}

    def __init__(self, frames):
        self.frames = {path: pd.DataFrame(rows) for path, rows in frames.items()}
        self.tables = list(self.frames)

    def table(self, path, raw=False):
        frame = self.frames[path].copy().fillna("")
        frame.attrs["source_sha256"] = "a" * 64
        return frame


def story(post="1", capture="2026-10-23T12:00:00+00:00", **fields):
    return dict(platform_selected="Instagram", selected_account_id="account", account_id_type="native_account",
                post_id=post, post_type="IG story", description="", publication_date="2026-10-10",
                snapshot_timestamp=capture, views="", views_status="unavailable", **fields)


def test_current_notice_counts_identities_across_captures_without_zero_filling():
    prior = story()
    prior.update(views="0", views_status="observed_zero")
    later = story(capture="2026-10-24T12:00:00+00:00")
    repo = Repo({CONTENT_PATH: [prior, later, story("2")]})
    data = current_coverage(repo).set_index("Dataset")
    row = data.loc["Instagram Stories"]
    assert row["Saved coverage"] == "2 distinct identities"
    assert "1 without numeric content metrics" in row["Remaining limits"]
    assert "2 without retained text" in row["Remaining limits"]
    assert "Link-click values: 0/2" in row["Remaining limits"]
    assert data.loc["Facebook Stories", "Saved coverage"] == "Uncollected in this version"
    assert len(repo.frames[CONTENT_PATH]) == 3


def test_repair_notice_requires_unique_complete_numeric_evidence():
    def follow(day, value="0", status="observed_zero", partial="false"):
        return dict(date=f"2026-01-{day:02}", value=value, value_status=status, partial_day=partial)
    repo = Repo({FOLLOW_REPAIR: [follow(1, partial="0"), follow(2, "", "missing"), follow(3, "-1", "observed"),
                               follow(4, "inf", "observed"), follow(5, partial="true"),
                               follow(6, "1", "observed"), follow(6, "2", "observed")]})
    row = current_coverage(repo).set_index("Dataset").loc["Instagram follows repair"]
    assert row["Saved coverage"] == "1 complete dates with numeric evidence"
    assert row["Reporting / publication dates"] == "2026-01-01 – 2026-01-01"
    assert "Supersedes inherited missing-date notices within this range" in row["Remaining limits"]


def test_older_version_does_not_claim_later_repair_or_supplement():
    old = Repo({"social/account_daily.csv": []})
    data = current_coverage(old).set_index("Dataset")
    assert data.loc["Instagram follows repair", "Saved coverage"] == "No reviewed repair in this version"
    assert "YouTube daily supplement" not in data.index
    current = current_coverage(old, ("youtube-daily-20261023",)).set_index("Dataset")
    assert "Registered separately" in current.loc["YouTube daily supplement", "Saved coverage"]
    assert "source blanks remain unavailable" in current.loc["YouTube daily supplement", "Remaining limits"]
