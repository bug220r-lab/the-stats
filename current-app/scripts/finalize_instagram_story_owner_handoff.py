"""Record completed owner-archive runtime verification after backup acceptance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/reconciliation/instagram_story_owner_20261023"
KEY = "instagram-story-owner-20261023"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    final = json.loads((OUT / "final_preservation_and_backup.json").read_text(encoding="utf-8"))
    assert final["active_version"] == KEY
    assert final["all_earlier_databases_unchanged"] and final["earlier_database_count"] == 7
    assert final["duplicate_replay_registry_unchanged"] and final["duplicate_promotion"]["idempotent"]
    assert len(final["database_quick_checks"]) == 8
    assert set(final["database_quick_checks"].values()) == {"ok"}
    assert final["backup_analysis_versions"] == 6
    evidence_paths = [
        "test-results/instagram-story-owner-20261023/owner-review-live.txt",
        "test-results/instagram-story-owner-20261023/owner-review-live.png",
        "test-results/instagram-story-owner-20261023/owner-archive-grid.png",
        "data/reconciliation/instagram_story_owner_20261023/independent_acceptance_audit.json",
        "data/reconciliation/instagram_story_owner_20261023/staged_ui_smoke_final.json",
        "data/reconciliation/instagram_story_owner_20261023/final_preservation_and_backup.json",
    ]
    runtime = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_key": KEY,
        "launcher": {"command": ".\\launch_windows.bat --no-browser", "session_id": 31807,
                     "observed_process_id": 11952, "address": "127.0.0.1", "port": 8501,
                     "actual_restart_passed": True, "verification_source": "Root live launcher output and listening-process command line"},
        "live_dashboard": {"url": "http://127.0.0.1:8501/", "active_version_visible": KEY,
                           "view": "Meta collection / Instagram owner archive", "identity_rows_verified": 6,
                           "verified_story_songs": 0, "source_meme_post_links": 4,
                           "six_summary_rows_rendered": True, "oct11_candidate_only": True,
                           "earlier_collection_views_available": True,
                           "verification_source": "Root live browser readback and visual screenshot inspection"},
        "tests": {"focused_tests_passed": 29, "focused_duration_seconds": 7.42,
                  "overlapping_owner_tests_rerun_passed": 7, "owner_rerun_duration_seconds": 0.96,
                  "full_suite_rerun": False, "staged_ui_smoke_passed": True},
        "preservation": {"prior_databases_unchanged": 7, "verified_snapshot_databases": 8,
                         "selectable_analysis_versions": 6, "idempotent_promotion_passed": True,
                         "backup_files": final["backup_files"], "backup": final["backup"],
                         "relocated_all_tables_and_zip_readback_passed": True,
                         "live_restore_performed": False},
        "evidence": [{"path": rel, "bytes": (ROOT / rel).stat().st_size, "sha256": sha(ROOT / rel)} for rel in evidence_paths],
        "limitations": ["No native Story audio label was exposed; six song assignments remain unresolved.",
                        "No listening or fingerprinting was performed. Source meme audio is not transferred to the band Story.",
                        "Original October 20 baseline membership remains unverified; all existing data is preserved.",
                        "No full-suite rerun, manual double-click/Ctrl+C, Linux execution, or hosted authentication/concurrency verification is claimed.",
                        "No TikTok collection or new statistical/causal attribution was performed."],
    }
    (OUT / "runtime_verification.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    draft = ROOT / "handoff/INSTAGRAM_STORY_OWNER_20261023.md"
    content = draft.read_text(encoding="utf-8")
    old_intro = "Drafted October 23, 2026. **Candidate `instagram-story-owner-20261023` is built, staged and independently accepted; live activation, launcher readback and a new backup remain root-owned follow-up steps.** Do not treat this draft as proof of activation. The candidate inherits `instagram-audio-20261023`. Continue the existing Windows workspace; TikTok remains excluded."
    new_intro = "Saved October 23, 2026. **Active immutable analysis: `instagram-story-owner-20261023`.** Activation, the actual Windows launcher restart, live browser rendering and portable backup readback passed. This version inherits `instagram-audio-20261023`. Continue the existing Windows workspace; TikTok remains excluded. The [preceding handoff](HANDOFF_before_instagram_story_owner_20261023.md) retains the personal-account post review and earlier history."
    assert old_intro in content
    content = content.replace(old_intro, new_intro).replace("after activation. The new view", "in the live dashboard. The new view")
    content = content.replace("## Candidate preservation and acceptance", "## Preservation and acceptance")
    old_pending = "The root agent must record actual activation, duplicate handling, restart/browser rendering, post-activation preservation and backup verification before replacing the main handoff. The preceding live handoff is `HANDOFF.md`; retain it as history when activating this candidate."
    assert old_pending in content
    completed = ("Root activation and live verification passed. The actual `.\\launch_windows.bat --no-browser` restart served only **127.0.0.1:8501** (observed process 11952), and the browser showed the new active version with all six summary rows and 6/0/4 metrics. Replaying promotion was idempotent and did not change the registry. All **seven earlier baseline/archive/analysis databases** remain byte-for-byte unchanged; those seven plus the new owner analysis passed integrity checks.\n\n"
                 f"Verified portable backup: **{final['backup_files']} files and six selectable analysis versions**, under `backups/library-instagram-story-owner-2026-10-23/`. All six versions loaded from the relocated backup with equal tables and original ZIP bytes. No live-library restore/replacement was performed. See [runtime verification](../data/reconciliation/instagram_story_owner_20261023/runtime_verification.json) and [preservation/backup receipt](../data/reconciliation/instagram_story_owner_20261023/final_preservation_and_backup.json).")
    content = content.replace(old_pending, completed)
    main_handoff = ROOT / "handoff/HANDOFF.md"
    preserved = ROOT / "handoff/HANDOFF_before_instagram_story_owner_20261023.md"
    old_main = main_handoff.read_bytes()
    assert b"instagram-audio-20261023" in old_main
    if preserved.exists():
        assert preserved.read_bytes() == old_main
    else:
        preserved.write_bytes(old_main)
    draft.write_text(content, encoding="utf-8")
    main_handoff.write_text(content, encoding="utf-8")
    assert draft.read_bytes() == main_handoff.read_bytes()
    print(json.dumps({"handoff_updated": True, "runtime_verified": True, "backup_files": final["backup_files"], "active_version": KEY}))


if __name__ == "__main__":
    main()
