# Windows post-capture delta

This separate delta adds five known files and updates two files that changed after the base snapshot cutoff. Base ZIP bytes and hashes remain unchanged. Delta capture ended 2026-10-23T06:41:42.301335+00:00 UTC. These seven paths are listed in `DELTA_MANIFEST.json` with both new hashes and the expected base hashes for replaced files.

Restore the base snapshot first. Both Google Drive and GitHub carry the same 14 ZIP parts because the Drive connection's single-upload limit is 512 MiB. Keep the `parts/` directory next to `PARTS_MANIFEST.json` and `restore_snapshot.py`, then run:

```powershell
python restore_snapshot.py join PARTS_MANIFEST.json The_Stats_Windows_Snapshot_2026-10-23_062048Z.zip
python restore_snapshot.py verify The_Stats_Windows_Snapshot_2026-10-23_062048Z.zip
python restore_snapshot.py restore The_Stats_Windows_Snapshot_2026-10-23_062048Z.zip C:\TheStats-Restored-2026-10-23
python apply_delta.py The_Stats_Windows_PostCapture_Delta_2026-10-23_064142Z.zip --verify-only
python apply_delta.py The_Stats_Windows_PostCapture_Delta_2026-10-23_064142Z.zip C:\TheStats-Restored-2026-10-23
```

`apply_delta.py` verifies the delta, checks all paths and expected base hashes before writing, and refuses to overwrite unexpected content. It affects only the restored workspace, not the active source project. It accepts an already-applied identical delta. The active-library snapshot remains the complete consistent library captured with the base package. The delta contains source/UI/handoff updates and audit receipts only; no database is modified.

The published `application-source/README.md`, `application-source/stats_app/youtube_ui.py`, and new `application-source/handoff/YOUTUBE_DAILY_SUPPLEMENT_20261023.md` include this delta. Other browsable source files match the base package. Use both packages for the most recent captured work. Ongoing work after this delta cutoff is not claimed included.
