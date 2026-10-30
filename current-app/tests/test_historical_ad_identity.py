"""Do not silently promote names, missing clicks or mismatched identities."""
import pytest

from scripts.audit_historical_ad_identity import classify, native_id, total
from stats_app.storage import StorageError


def test_exact_native_identity_triplet_required_for_band():
    band = {"Link Object ID": "o:118246571240106", "Instagram Account ID": "x:5324346047653591",
            "Link": "https://www.instagram.com/_u/redactedbandoh"}
    assert classify(band)[0] == "band"
    assert classify(dict(band, Link="https://www.therialtotheatre.com/record-and-release-program"))[0] == "unknown"
    assert classify(None)[0] == "unknown"


def test_rialto_identity_is_explicitly_nonband():
    assert classify({"Link Object ID": "o:723656497712673", "Instagram Account ID": "x:935441079885561",
                     "Link": "https://www.therialtotheatre.com/record-and-release-program"})[0] == "nonband"


def test_missing_clicks_remain_missing_and_currency_is_exact():
    assert total([{"clicks": ""}, {"clicks": ""}], "clicks") == ""
    assert total([{"clicks": ""}, {"clicks": "0"}], "clicks") == "0"
    assert total([{"spend": "104.98"}, {"spend": "149.96"}, {"spend": "99.64"}, {"spend": "199.94"}], "spend", 2) == "554.52"


def test_native_id_prefix_and_long_string_identity_are_preserved():
    assert native_id("a:120203882112190452", "a:") == "120203882112190452"
    with pytest.raises(StorageError):
        native_id("cg:120203882112190452", "a:")
