"""Read-only before/after audit of Story backfill and Spotify spike context."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
from hashlib import file_digest
import json
from pathlib import Path

import pandas as pd

from stats_app.analysis_content import METRICS, publication_inventory
from stats_app.analysis_correlation import EXPOSURES, build_weekly_activity
from stats_app.analysis_repository import AnalysisRepository
from stats_app.analysis_spikes import (
    _caption_available, _capture_caption_evidence, publication_capture_context, publications_around_week, rank_spotify_increases,
)
from stats_app.content_summaries import content_coverage, content_source_paths
from stats_app.meta_collection import PACKAGING_ASSETS

PREFIX = "social/meta_story_backfill_20261024/"
CONTENT = PREFIX + "content_snapshots.csv"
SPOTIFY = "spotify/cleaned/artist_daily.csv"


def digest(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def metric_coverage(observations):
    return {metric: int(observations.loc[observations[metric].notna(), "identity_key"].nunique()) for metric in METRICS}


def caption_keys(identities):
    return set(identities.loc[identities.description.map(lambda text: _caption_available([text])), "identity_key"])


def nearby_publications(identities, week):
    """Preselect certain candidate weeks before the unchanged strict selector.

    The identity bundle already provides a certain week or an empty string.
    Unknown/cross-week identities cannot match the production drilldown. This
    avoids traversing the full corpus repeatedly for each audit window.
    """
    target = pd.Timestamp(week)
    low = (target.date() - timedelta(days=7)).isoformat()
    high = target.strftime("%Y-%m-%d")
    candidates = identities.loc[identities.week.between(low, high)]
    return publications_around_week(candidates, target)


def run(before_db, after_db, output_dir, expected_identities=75):
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new empty audit directory to preserve prior evidence.")
    before, after = AnalysisRepository(before_db), AnalysisRepository(after_db)
    db_hashes = {"before": digest(before.db_path), "after": digest(after.db_path)}
    catalogs = {"before": before.file_catalog(), "after": after.file_catalog()}
    hashes = {name: frame.set_index("path").sha256.to_dict() for name, frame in catalogs.items()}
    retained_paths = {path: ("raw/meta_story_backfill_20261024_predecessor_metadata/" + path
                             if path in PACKAGING_ASSETS else path) for path in hashes["before"]}
    inherited_missing = sorted(path for path, retained in retained_paths.items() if retained not in hashes["after"])
    inherited_changed = sorted(path for path, value in hashes["before"].items()
                               if retained_paths[path] in hashes["after"] and hashes["after"][retained_paths[path]] != value)
    if CONTENT not in after.tables:
        raise ValueError("Candidate has no explicit Story-backfill content table.")
    bundles = {"before": build_weekly_activity(before), "after": build_weekly_activity(after)}
    before_obs, after_obs = bundles["before"]["observations"], bundles["after"]["observations"]
    backfill = after_obs.loc[after_obs.source_table.eq(CONTENT)]
    before_ids, after_ids = bundles["before"]["identities"], bundles["after"]["identities"]
    before_lookup = before_ids.set_index("identity_key")
    old_keys, new_keys = set(before_ids.identity_key), set(after_ids.identity_key)
    caption_sets = {name: caption_keys(bundle["identities"]) for name, bundle in bundles.items()}
    ranks = {name: {outcome: rank_spotify_increases(bundle["weekly"], outcome)
                    for outcome in ("streams", "mean_daily_listeners")} for name, bundle in bundles.items()}
    available_spike_weeks = sorted({week for frame in ranks["after"].values()
                                    for week in frame.week_start.dt.strftime("%Y-%m-%d")})
    detail_rows = []
    for key, source_rows in backfill.groupby("identity_key", sort=True):
        identity = after_ids.loc[after_ids.identity_key.eq(key)].iloc[0]
        prior_identity = before_lookup.loc[key] if key in before_lookup.index else None
        week = identity.week
        items = (publications_around_week(after_ids.loc[after_ids.identity_key.eq(key)], week, before_weeks=0)
                 if week else pd.DataFrame())
        items = items.loc[items.identity_key.eq(key)] if not items.empty else items
        context = publication_capture_context(after_obs, items)
        retained = context.loc[context.source_table.eq(CONTENT)] if not context.empty else context
        numeric = source_rows[METRICS].notna().any()
        wanted = set(numeric.index[numeric])
        shown = set(retained.loc[retained.value.notna(), "metric"]) if not retained.empty else set()
        supplied_captions = [value for value in source_rows.description if _caption_available([value])]
        displayed_caption = items.description.iloc[0] if not items.empty else ""
        matching_windows = [spike for spike in available_spike_weeks
                            if week and abs((pd.Timestamp(week) - pd.Timestamp(spike)).days) <= 7]
        detail_rows.append(dict(identity_key=key, post_id=identity.post_id, publication_dates=identity.dates,
            prior_publication_dates=prior_identity.dates if prior_identity is not None else "",
            date_conflict_before=bool(prior_identity.date_conflict) if prior_identity is not None else False,
            date_conflict_after=bool(identity.date_conflict),
            date_evidence_changed=identity.dates != (prior_identity.dates if prior_identity is not None else ""),
            prior_publication_week=prior_identity.week if prior_identity is not None else "",
            publication_week_status="same_week_date_conflict" if identity.date_conflict and week else
                "cross_week_date_conflict" if identity.date_conflict else "source_calendar_date" if week else "unknown_date",
            new_native_publication_labels="\n".join(dict.fromkeys(source_rows.published_local)),
            source_week=week, preexisting_publication=key in old_keys, strict_band=bool(identity.strict_band),
            reaches_spike_detail=not items.empty, caption_before=key in caption_sets["before"],
            caption_after=key in caption_sets["after"], new_source_text=_caption_available(source_rows.description),
            all_new_captions_reach_spike_detail=all(value in displayed_caption for value in supplied_captions),
            new_numeric_metrics=";".join(sorted(wanted)), numeric_metrics_in_spike_detail=";".join(sorted(shown)),
            all_new_numeric_metrics_reach_spike_detail=wanted.issubset(shown),
            candidate_capture_count=len(source_rows), latest_candidate_metric_rows=len(retained)))
        detail_rows[-1].update(available_rising_spike_windows=";".join(matching_windows),
                               has_available_rising_spike_window=bool(matching_windows))
    details = pd.DataFrame(detail_rows)
    date_changes = details.loc[details.date_evidence_changed].copy()
    new_date_conflicts = details.loc[details.date_conflict_after & ~details.date_conflict_before]
    exact_day_inventories = {name: publication_inventory(bundle["observations"]) for name, bundle in bundles.items()}
    window_rows = []
    backfill_keys = set(backfill.identity_key)
    example_rows = []
    weeks = {"2026-02-23"}
    for outcome in ranks["after"]:
        weeks.update(ranks["after"][outcome].week_start.head(12).dt.strftime("%Y-%m-%d"))
    for week in sorted(weeks):
        row = dict(spotify_week=week, content_window="preceding week plus selected week")
        for name, bundle in bundles.items():
            items = nearby_publications(bundle["identities"], week)
            context = publication_capture_context(bundle["observations"], items)
            row.update({name + "_publications": len(items), name + "_captions": int(items.caption_available.sum()),
                        name + "_identities_with_numeric_capture_metrics":
                            int(context.loc[context.value.notna(), "identity_key"].nunique()) if not context.empty else 0})
            if name == "after":
                matched = backfill.loc[backfill.identity_key.isin(items.identity_key)]
                row["backfilled_identities_in_window"] = int(matched.identity_key.nunique())
                row["backfilled_text_identities_in_window"] = int(matched.loc[matched.description.map(lambda value: _caption_available([value])), "identity_key"].nunique())
                row["backfilled_view_observed_identities_in_window"] = int(matched.loc[matched.views.notna(), "identity_key"].nunique())
        for outcome, ranked in ranks["after"].items():
            matching = ranked.loc[ranked.week_start.eq(pd.Timestamp(week))]
            row[outcome + "_rank"] = int(matching.index[0]) + 1 if not matching.empty else None
            row[outcome + "_increase"] = float(matching.increase.iloc[0]) if not matching.empty else None
        window_rows.append(row)
    windows = pd.DataFrame(window_rows)
    for outcome, ranked in ranks["after"].items():
        for rank, spike in ranked.head(12).iterrows():
            items = nearby_publications(after_ids, spike.week_start)
            for item in items.loc[items.identity_key.isin(backfill_keys)].itertuples():
                source = backfill.loc[backfill.identity_key.eq(item.identity_key)].iloc[0]
                if not _caption_available([source.description]) or pd.isna(source.views) or source.views <= 0:
                    continue
                example_rows.append(dict(outcome=outcome, spike_rank=int(rank) + 1,
                    spotify_week=spike.week_start.strftime("%Y-%m-%d"), spotify_increase=float(spike.increase),
                    post_id=item.post_id, publication_dates=item.dates, date_conflict=bool(item.date_conflict),
                    native_publication_label=source.published_local, caption=source.description,
                    lifetime_views=float(source.views), lifetime_views_status=source.views_status,
                    lifetime_reach=float(source.reach) if pd.notna(source.reach) else None,
                    lifetime_reach_status=source.reach_status, capture_time=source.snapshot_timestamp,
                    metric_scope=source.metric_platform_scope, source_table=source.source_table,
                    relation=item.relation, qualification="Calendar-window context only; lifetime views are not daily activity, attributed Spotify streams or proof of effect."))
    examples = pd.DataFrame(example_rows)
    checks = dict(parent_catalog_paths_preserved=not inherited_missing, parent_catalog_sha256_preserved=not inherited_changed,
        expected_backfill_identity_count=int(backfill.identity_key.nunique()) == expected_identities,
        parent_publication_identities_preserved=old_keys.issubset(new_keys), publication_identity_set_unchanged=old_keys == new_keys,
        prior_publication_dates_retained=all(set(row.prior_publication_dates.split(";")) - {""} <= set(row.publication_dates.split(";"))
                                            for row in details.itertuples()),
        backfill_only_existing_publications=bool(len(details)) and bool(details.preexisting_publication.all()),
        backfill_has_complete_identities=bool(len(backfill)) and bool(backfill.identity_complete.all()),
        backfill_reaches_spike_detail=bool(len(details)) and bool(details.reaches_spike_detail.all()),
        all_new_captions_reach_spike_detail=bool(len(details)) and bool(details.all_new_captions_reach_spike_detail.all()),
        all_new_numeric_metrics_reach_spike_detail=bool(len(details)) and bool(details.all_new_numeric_metrics_reach_spike_detail.all()),
        spotify_daily_source_unchanged=hashes["before"].get(SPOTIFY) == hashes["after"].get(SPOTIFY),
        spotify_weekly_outcomes_unchanged=bundles["before"]["weekly"].drop(columns=[c for c in bundles["before"]["weekly"] if c.startswith(EXPOSURES)]).equals(
            bundles["after"]["weekly"].drop(columns=[c for c in bundles["after"]["weekly"] if c.startswith(EXPOSURES)])),
        weekly_publication_counts_unchanged=bundles["before"]["weekly"][list(EXPOSURES)].equals(bundles["after"]["weekly"][list(EXPOSURES)]),
        streams_spike_ranking_unchanged=ranks["before"]["streams"].equals(ranks["after"]["streams"]),
        listener_spike_ranking_unchanged=ranks["before"]["mean_daily_listeners"].equals(ranks["after"]["mean_daily_listeners"]))
    checks["before_database_unchanged"] = digest(before.db_path) == db_hashes["before"]
    checks["after_database_unchanged"] = digest(after.db_path) == db_hashes["after"]
    result = dict(status="verified" if all(checks.values()) else "review_required", checks=checks,
        databases={name: dict(path=str(repo.db_path), sha256=db_hashes[name]) for name, repo in (("before", before), ("after", after))},
        source_paths={"before": content_source_paths(before), "after": content_source_paths(after)},
        parent_asset_catalog_paths=len(hashes["before"]), parent_asset_missing=inherited_missing,
        parent_asset_catalog_sha256_changed=inherited_changed,
        relocated_parent_packaging_assets={path: retained for path, retained in retained_paths.items() if path != retained},
        coverage={name: content_coverage(bundle["observations"]) for name, bundle in bundles.items()},
        numeric_metric_identity_coverage={name: metric_coverage(bundle["observations"]) for name, bundle in bundles.items()},
        caption_identity_coverage={name: len(keys) for name, keys in caption_sets.items()},
        recovered_caption_identities=len(caption_sets["after"] - caption_sets["before"]),
        backfill_observations=len(backfill), backfill_identities=int(backfill.identity_key.nunique()),
        backfill_caption_evidence_observations=dict(Counter(_capture_caption_evidence(row) for row in backfill.to_dict("records"))),
        backfill_source_text_identities=int(details.new_source_text.sum()),
        backfill_without_source_text_identities=int((~details.new_source_text).sum()),
        expected_backfill_identities=expected_identities,
        backfill_identities_in_available_rising_spike_windows=int(details.has_available_rising_spike_window.sum()),
        newly_conflicting_publication_date_identities=len(new_date_conflicts),
        newly_same_week_date_conflicts=int(new_date_conflicts.publication_week_status.eq("same_week_date_conflict").sum()),
        newly_cross_week_date_conflicts=int(new_date_conflicts.publication_week_status.eq("cross_week_date_conflict").sum()),
        exact_day_inventory_publications={name: int(frame.retained_publications.sum()) for name, frame in exact_day_inventories.items()},
        note="Source calendar publication counts and Spotify UTC daily activity remain separate. Metric context retains lifetime capture time, metric scope, status and provenance; no lifetime values are allocated to daily or weekly Spotify outcomes. Historical reviewed inference is not rerun.")
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    details.to_csv(output / "backfill_identity_drilldown.csv", index=False)
    date_changes.to_csv(output / "new_publication_date_evidence.csv", index=False)
    for name, frame in exact_day_inventories.items():
        frame.to_csv(output / f"{name}_exact_day_publication_inventory.csv", index=False)
    windows.to_csv(output / "spike_window_comparison.csv", index=False)
    examples.to_csv(output / "spike_context_browser_examples.csv", index=False)
    for name in bundles:
        for outcome, frame in ranks[name].items():
            frame.to_csv(output / f"{name}_{outcome}_spike_rankings.csv", index=False)
    report = ["# Story backfill and Spotify spike comparison", "", f"Result: **{result['status']}**.", "",
              f"The candidate adds {len(backfill):,} retained capture observations for {int(backfill.identity_key.nunique()):,} Story identities.",
              f"New capture text evidence: {result['backfill_source_text_identities']:,} identities with retained source text; {result['backfill_without_source_text_identities']:,} without. Explicit native caption statuses: {json.dumps(result['backfill_caption_evidence_observations'], sort_keys=True)}. Native no-text is distinct from text that was not collected or is unavailable; it does not describe text embedded in the image/video.",
              f"Identities with retained source text: {len(caption_sets['before']):,} before; {len(caption_sets['after']):,} after ({result['recovered_caption_identities']:,} newly covered).",
              "", "## Checks", "", "| Check | Result |", "|---|---|"]
    report.extend(f"| {key.replace('_', ' ')} | {'PASS' if value else 'REVIEW'} |" for key, value in checks.items())
    report.extend(["", "## Interpretation", "", result["note"], "",
                   "The publication drilldown keeps each typed platform/account/post identity once. Captions from retained captures remain available together. A separate expandable capture table and CSV show latest-compatible lifetime metrics with source references. Unknown capture times and same-time conflicts remain explicit and are not merged.",
                   "", f"Newly conflicting publication dates: {len(new_date_conflicts):,} identities, including {result['newly_same_week_date_conflicts']:,} whose dates remain in one Monday–Sunday week and {result['newly_cross_week_date_conflicts']:,} whose week is disputed. All old and new source dates remain present. Exact-day inventory excludes any conflicting-date identity; same-week comparison context can retain one publication while displaying the date disagreement. No publication time or timezone is inferred.",
                   f"Exact-day inventory: {result['exact_day_inventory_publications']['before']:,} publications before; {result['exact_day_inventory_publications']['after']:,} after. A reduction caused by newly contradictory dates is an explicit exclusion, not deletion or a silently chosen replacement date.",
                   "", f"{int(details.has_available_rising_spike_window.sum()):,} of {len(details):,} backfilled identities lie within the preceding/selected/following window of at least one selectable rising week across streams or average daily listeners. The per-identity CSV lists those weeks. Structural source-week checks alone do not imply that a Story coincided with a Spotify increase.",
                   "", "The parent asset comparison checks retained catalog SHA-256 values and paths. Three package metadata assets are expected under the explicit predecessor-metadata namespace; analytical and source assets retain their original paths. Parsed content/Spotify reads also verify their stored CSV bytes and rows. Staging verification supplies the separate complete-package source check.",
                   "", "## Evidence", "", "- `comparison.json`: exact source hashes, coverage and checks.",
                   "- `backfill_identity_drilldown.csv`: per-identity caption/stat/UI eligibility.",
                   "- `new_publication_date_evidence.csv`: changed date sets and literal new native labels; both source dates remain retained.",
                   "- `before_exact_day_publication_inventory.csv`, `after_exact_day_publication_inventory.csv`: exact-day counts excluding contradictory dates.",
                   "- `spike_window_comparison.csv`: top spike windows plus February 23, before and after.",
                   "- `spike_context_browser_examples.csv`: actual top-spike-window Stories with newly retained source text and nonzero observed lifetime views, for browser verification; these are timing examples, not effectiveness rankings.",
                   "- `before_*_spike_rankings.csv`, `after_*_spike_rankings.csv`: exact unchanged Spotify rankings.", ""])
    (output / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-db", required=True)
    parser.add_argument("--after-db", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-identities", type=int, default=75)
    args = parser.parse_args()
    result = run(args.before_db, args.after_db, args.output_dir, args.expected_identities)
    print(json.dumps({"status": result["status"], "checks": result["checks"],
                      "backfill_identities": result["backfill_identities"],
                      "recovered_caption_identities": result["recovered_caption_identities"]}, indent=2))
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
