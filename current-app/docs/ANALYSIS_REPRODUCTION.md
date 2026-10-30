# Reproduce the delivered analysis

The dashboard uses the delivered analytical tables. Reproduction is a separate offline audit: it runs the package's Python analysis in a new copy and retains the original package and raw exports unchanged. It does not update a dashboard database or rebuild the HTML report narrative.

From PowerShell in this project directory, after `setup_windows.bat` has completed:

```powershell
.\.venv\Scripts\python.exe .\scripts\reproduce_analysis.py `
  --package '.\data\recovery\cleaned_analysis_2026-10-22\analysis_2026-10-22' `
  --output '.\data\reconciliation\analysis_rerun_01'
```

The output directory must be **new** and outside the source package. Choose a different output name for each run. If the preserved package is elsewhere, replace only the `--package` argument with its extracted directory containing `raw_sha256.json` and `code/run_all.py`. No personal machine path is required. On Linux, the corresponding interpreter is `.venv/bin/python`; the wrapper and its path fixes work on either platform.

The wrapper verifies the raw manifest, hashes and copies the whole package, applies two recorded path fixes to the copy, and runs its `code/run_all.py` with the same Python interpreter. The original scripts use Windows backslashes in two source inventories; `.as_posix()` makes those identities agree with the preserved manifest. UTF-8 mode and a matplotlib cache inside the output copy are set for the child process only. The wrapper never installs packages or changes system settings.

Review these files inside the chosen output:

- `audit/windows_reproduction_manifest.json`: interpreter/dependency versions, source hashes, exact copy-only fixes, child exit code, and original-file preservation result.
- `audit/windows_reproduction_run.log`: full pipeline output and errors.
- `audit/final_validation.json`: numerical and source checks produced by the analysis.
- `statistical_results.csv`: all 53 combined results, including the 12 planned cross-platform comparisons.

Exit code zero requires both a successful pipeline and passing final checks, unchanged original files, and matching raw checksums after reproduction. On failure, preserve the output directory and read the log; the wrapper does not delete evidence or overwrite an existing run. Missing dependencies can be restored with `setup_windows.bat`, which uses the project's pinned lock file.

## Verification actually performed

The real package was reproduced on Windows using Python 3.12.14. The five-script `code/run_all.py` pipeline completed successfully in **45.27 seconds** in `data/reconciliation/analysis_reproduction_2026-10-22`. The initial unmodified attempt exposed the path-separator checksum-lookup bug; the successful run used only the two copy-only fixes above and UTF-8 process configuration. The original package was unchanged.

Runtime versions were pandas **2.3.3**, NumPy **2.5.4**, SciPy **1.17.0**, matplotlib **3.10.8**, and openpyxl **3.1.5**. The delivered package had pinned pandas 2.2.3 and NumPy 2.3.5; this run used the existing project's versions. Twelve principal delivered and regenerated CSVs matched at relative tolerance `1e-10` and absolute tolerance `1e-12`, including daily artist/track data, comparisons, social data, joins, and statistical results.

Verified results:

- All **652 retained raw files** and **32 native Meta CSVs** passed checksums. All original package files remained unchanged.
- Spotify: **1,024 consecutive artist dates**, **66,631 recording-day-metric rows**, and **14 recordings reconciled across 365 complete common dates**.
- September 23–October 20 streams: **4,246 versus 4,011**; directly reported period-unique listeners: **1,062 versus 1,121**. Matched YTD streams: **58,175 versus 22,825**. Latest/prior 90-day streams: **13,775 versus 19,832**.
- Eleven recordings gained streams; Funny Guy provided **35.0447%** of latest-period streams.
- Social: **3,528 canonical calendar rows**, **128 null Instagram Follows observations**, **183 quarantined malformed Stories**, and **377 valid lifetime post/Story records**. October 21 remains partial; Instagram-selected Views retains its combined Facebook/Instagram scope.
- All **53 results** and **12 planned comparisons** remained present. Six comparisons support exploratory inference. Ten defined Spearman coefficients, six circular-shift p-values, and the full 12-test BH correction were independently recomputed. Minimum BH-adjusted p-value: **0.384615**; no adjusted significant result. This does not establish that marketing has no effect.

Detailed evidence is in `data/reconciliation/cleaned_analysis_audit.json`; the preflight, original failure log, successful log, and exact patches are retained alongside the reproduction copy. These reports contain private local paths and remain outside Git.

The wrapper's seven focused isolated tests passed: preservation and child execution, existing-output refusal, checksum failure, unsafe manifest paths, retained failure evidence, rejection of stale copied validation, and refusal to nest output inside source. Run them with `.\.venv\Scripts\python.exe -m pytest -q tests/test_analysis_reproduction.py`. The complete real analysis was not rerun solely to test the wrapper.

## Remaining limits

NumPy emitted timedelta deprecation warnings; calculations completed and numerical comparisons passed. Future dependency upgrades should rerun the checks before adoption. The pipeline regenerates CSV/JSON/figure outputs; its delivered HTML narrative is a separate reviewed snapshot. This audit did not visually verify that HTML, collect live analytics, access TikTok, or establish causal marketing effects. Dashboard browser verification is documented separately.
