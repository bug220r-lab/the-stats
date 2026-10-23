# Social collection — October 22, 2026

Facebook and Instagram source exports were collected from the authenticated Meta Business Suite browser session. Raw CSVs, export settings, screenshots, account identity evidence and acquisition timestamps are retained privately under `data/social_captures/2026-10-22/`. The replay manifest is `capture_manifest.json` in that directory.

These captures use their own snapshot, **Social captures · Oct 22, 2026 · separate from Oct 20 archive**. They do not replace the archived Spotify package, change its observations, or establish the identity of the unavailable original October 20 baseline.

## Coverage and interpretation

- Account Results exports cover July 24–October 21, 2026. The source date picker explicitly uses Pacific Time. Additional source readings cover September 24–October 21.
- Native daily observations and exact-window source readings remain separate evidence. Unique viewers and reach must use a matching source period total; daily distinct audiences are never summed.
- Instagram's Results Views include Facebook crossposts. The source scope and available platform components are retained; the combined export is not presented as Instagram-only views.
- Instagram post exports label their measurements **Lifetime**. The export's selected dates identify content, not a measurement window. Reporting cutoffs remain unknown, while native publication times and capture times stay separate. The Social media view has a dedicated lifetime-content table and download.
- Collaborator account IDs and native Meta/Page IDs remain distinct. Names are not used to merge accounts.
- Sparse exports retain missing dates. The Instagram follows export does not imply zero follows on its omitted dates.
- The Facebook post Performance export contains one selected shared post and video-threshold metrics, all zero. It does not establish zero activity across Facebook. Source zeros before publication remain recorded but are excluded from activity calculations.

## Access gaps

TikTok Studio and TikTok for Artists require user sign-in. No private analytics were available from those login pages. Their missing data is not represented by zero observations.

Instagram Stories export generation remained disabled for the selected account using both the last 90 days and last 30 days. The disabled control is recorded as source evidence.

The dashboard is a local import and analysis application. Collection uses an authenticated browser or user-supplied exports; it does not automatically sign in to or synchronize platforms.

## Reproduce and inspect

From the project directory with the virtual environment active:

```sh
python scripts/load_social.py data/social_captures/2026-10-22/capture_manifest.json
python scripts/load_social.py data/social_captures/2026-10-22/capture_manifest.json --commit
```

The first command validates and reports without changing the database. The second imports into the manifest's separately identified snapshot. Repeating the same manifest is idempotent. Unexpected schemas, mismatched checksums or unresolved errors block import.

In the app, select the social snapshot and open **Social media**. Account selectors display source identities. Use **Data & collection** for import history, metric definitions and capture gaps. Preserve the whole `data/social_captures/` directory with database backups so screenshots and acquisition logs remain available alongside archived source CSVs.
