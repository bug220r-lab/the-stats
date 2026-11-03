# [REDACTED] dashboard branding

The dashboard uses the band's existing **COUCH STICKER.png** artwork, fetched from the connected Google Drive on October 23, 2026. The original file is retained unchanged as `couch-sticker-original.png`; it is displayed at responsive sizes without cropping, recoloring or redrawing it. The photographic `redacted-sticker-original.png` is retained for provenance and comparison but is not displayed in the application.

The approved compact layout (October 24, 2026, option A) shows the couch logo once, at 125 pixels wide in the sidebar, with a small **The Stats™** label beneath it. The main pane starts with the page content, without a duplicate logo or large branding header. Streamlit's sidebar collapse/reopen controls remain available.

Sources:

- [COUCH STICKER.png](https://drive.google.com/file/d/1bG_KQYyHeBIrL1HcSpZlro6P8pBWQmLo/view), 71,908 bytes, 4800 × 2118 pixels, luminance and alpha PNG. SHA-256: `8f79cb00debaaf1d5eaf7a6eb4953b4da2263bb3b100a54819beee230fa62b66`.
- [redacted sticker.png](https://drive.google.com/file/d/1Qc2qkbjxt9mC6zTi-WqW3FuX5lSuEkdz/view), 1,486,040 bytes, 2048 × 1535 pixels, RGBA PNG. SHA-256: `43219d140026835be608ba4792c3cea24da53863996826829554ef57a2d9b90f`.
- [Original sticker folder](https://drive.google.com/drive/folders/1ftj4UaCYPodzOq7_HU-b2Qc5Qc5UDbmp).
- [Band Master folder](https://drive.google.com/drive/folders/1N5VsA9GuliG6FShwiKyJZXwVJ_F5h8Mk).

The official `00_ADMIN / Brand Assets` folder was accessible but empty when checked. The EPK document also returned empty content. No official color or font guide was found in this focused search. The white couch outline and bracketed wordmark are therefore the source-backed visual identity. Near-black surfaces and warm white text are interface choices that complement the artwork. The existing yellow chart accent is retained for analytical readability; it is not asserted to be an official brand color. Body type uses the existing Streamlit sans-serif interface font; there is no newly downloaded or invented brand font.

The current [Instagram profile, @redactedbandoh](https://www.instagram.com/redactedbandoh/), was checked at `2026-10-23T05:09:17.192Z`. Its profile photo shows the couch and bracketed wordmark; its pinned merchandise post shows the same white couch line art used here. The bio reads “Go ahead, take a seat. Post Nu Metal from Akron, OH” and links to [the band's Linktree](https://linktr.ee/redactedoh). This corroborates the selected Drive artwork as a current band identity. Evidence is preserved under `data/collection/meta-followup-20261023/social_branding/instagram-profile.png` and `instagram-profile.json`; the screenshot is retained as evidence and is not used as a dashboard asset. Exact source evidence hashes are in `sources.json`.

`stats_app/branding.py` resolves assets with `pathlib` from the project root. Branding performs no database access and makes no external runtime requests. The existing authentication gate runs before the branded content. A missing logo falls back to the band name, leaving the dashboard usable.

The [Facebook band profile](https://www.facebook.com/redactedbandoh/) was also inspected on October 23. It uses a white bracketed wordmark on a black profile image and links to the same Linktree. The current screenshot and link capture are retained in `data/collection/meta-followup-20261023/social_branding/facebook-profile.png` and `facebook-profile.json`. This supports the neutral black/white presentation; it supplies no official font or color specification.

## Monochrome Matrix presentation — October 30, 2026

The user selected a Matrix-inspired desktop identity in **black and white** to
match the band. The dashboard now uses near-black surfaces, white rules and
focus indicators, compact terminal typography and a faint static line texture.
The original couch artwork stays unchanged and appears once in the compact
sidebar block; the main pane continues to start with the current page content.
All typography uses existing system fonts, and there are no runtime font,
artwork or animation downloads. Reduced-motion settings suppress the short
navigation hover transition; no decorative animation or flashing is used.

The shared chart frame uses neutral labels, grid lines and default series colors.
The earlier yellow brand accent becomes white. Explicit semantic colors, trace
styles and missing-data gaps remain available rather than applying a grayscale
filter to analytical content. This supersedes the earlier yellow-accent interface
choice while preserving the dated source and design evidence above. These are
presentation changes only: calculations, selections and registrations are unaffected.
