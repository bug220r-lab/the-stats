"""Write explicit follow-up availability from reviewed retained evidence."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "data/collection/meta-followup-20261023"


def main():
    rows = [
        ("six_recent_stories", "visually_reviewed_audio_unverified", "All six Meta previews inspected; 36 lifetime cells retained (14 observed, 22 unavailable). Zero confirmed song IDs. Oct11 The Cut candidate only; Oct10 album/brand artwork only. User does not know songs. Owner Instagram archive access still needed for audio labels.", "normalized/story_song_map.csv; normalized/story_metrics.csv; stories/instagram-archive-access.json"),
        ("2026_ads_manager", "scoped_no_data", "One accessible account 582351779816254; Jan1-Oct22,2026 ad and campaign exports return No data available; five current published UI rows show $0. Payment activity says No transactions. No zero-filled daily series or inference about inaccessible accounts.", "normalized/ads_coverage.csv; ads/acquisition_metadata.json"),
        ("historical_ad_identity", "mixed_account_corrected_by_identity", "Maximum history $661.02 partitions to band-identified $554.52, Rialto $99.79, unresolved $6.71. Current exact-ID configurations establish identity at capture, not unchanged historical creative revisions. June band-identified $199.94; earlier $202.43 included $2.49 unresolved. February generic band-promotion interpretation withdrawn.", "normalized/ad_identity_scope.csv; normalized/ad_identity_totals.csv; AD_IDENTITY_CORRECTION.md"),
        ("ad_destinations", "configuration_only", "Four published band configurations link to Instagram profile, not Spotify. One published Rialto configuration links to the theatre program. One draft destination missing. Configuration does not prove delivery or historical stability.", "normalized/ad_destinations.csv; ads/ad_configuration_all.csv"),
        ("profile_link_destinations", "current_inventory_verified", "Instagram and Facebook bio links point to official Linktree. Six music cards inspected; Debut Album card currently points to Funny Guy track3QVtuSBGLC9fTmLfF6qP7Z. Three other track IDs have no exact canonical-catalog match and remain separate. No per-link analytics or historical card versions were available in this public view.", "normalized/link_destinations.csv; normalized/link_evidence_issues.csv; links/linktree-cards.json"),
        ("facebook_aug26_link_post", "destination_verified", "Post998829296519708 shares Akron-Summit County Public Library submission invitation and links to Blimp City Beats, not a Spotify track.", "links/facebook-998829296519708.txt; links/facebook-998829296519708-destination.json"),
        ("baseline_and_prior_snapshots", "preserved_baseline_membership_unverified", "Every predecessor asset remains unchanged in a new analysis version. Original October20 baseline membership is still unverified; later captures retain their own timestamps and reporting scopes.", "preflight_preservation.json"),
        ("tiktok", "excluded", "No TikTok sign-in, analytics or content collection performed. Incidental TikTok label on the band's public Linktree was not opened.", "User scope instruction"),
    ]
    output = pd.DataFrame(rows, columns=["dataset", "status", "detail", "evidence_ref"])
    output["captured_at_utc"] = ""
    output["reviewed_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.to_csv(C / "normalized/collection_status.csv", index=False)
    print(json.dumps({"status_rows": len(output), "captured_at_note": "Blank on review summary; individual captures and acquisition timestamps retained in source tables"}))


if __name__ == "__main__":
    main()
