"""Read-only descriptive alignment of preserved Meta caption references and Spotify.

No lifetime metrics are assigned to publication days, no listener totals are summed,
and no statistical/causal claim is computed here. Inputs are the frozen package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, default=Path('data/reconciliation/meta_20261023/package'))
    parser.add_argument('--output', type=Path, default=Path('data/reconciliation/meta_spotify_crossref_20261023/events'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source_paths = [
        'social/meta_collection/mapping/post_song_map.csv',
        'social/meta_collection/mapping/post_song_references.csv',
        'social/meta_collection/mapping/event_map.csv',
        'spotify/cleaned/track_daily_long.csv',
        'spotify/cleaned/recordings.csv',
        'spotify/cleaned/track_28day_comparison.csv',
        'social/meta_collection/mapping/post_evidence.csv',
    ]
    hashes = {x: hashlib.sha256((args.package / x).read_bytes()).hexdigest() for x in source_paths}
    loaded = {x: pd.read_csv(args.package/x, dtype=str, keep_default_na=False) for x in source_paths}
    posts, refs, eventmap, daily, recordings, prior28, postevidence = [loaded[x] for x in source_paths]
    assert not posts.duplicated(['platform_selected', 'selected_account_id', 'post_id']).any()
    assert not refs.duplicated(['post_key', 'song_id']).any()
    assert not recordings.song_id.duplicated().any()
    catalog = recordings.set_index('song_id')
    explicit = refs[refs.status.eq('explicit_caption_reference')].copy()
    assert explicit.song_id.isin(catalog.index).all()
    assert explicit.audio_use_verified.eq('False').all()
    assert explicit.stream_attribution_available.eq('False').all()
    explicit['pacific_date'] = pd.to_datetime(explicit.publication_date)
    explicit['utc_date'] = pd.to_datetime(explicit.published_utc, utc=True).dt.tz_localize(None).dt.normalize()
    explicit['date'] = explicit.utc_date
    streams = daily[daily.metric.eq('streams')].copy()
    streams['date'] = pd.to_datetime(streams.date)
    streams['value'] = pd.to_numeric(streams.value, errors='coerce')
    assert not streams.duplicated(['song_id', 'date']).any()
    assert streams.reporting_timezone.eq('UTC').all()
    assert streams.value_status.eq('observed').all()
    assert streams.value.notna().all()
    series = {song: g.set_index('date').value.sort_index() for song, g in streams.groupby('song_id')}
    date_groups = explicit.groupby(['song_id', 'date'], sort=True)
    primary_dates = {song: sorted(g.date.unique()) for song, g in explicit.groupby('song_id')}

    def shift(date, days):
        return pd.Timestamp(pd.Timestamp(date).to_pydatetime() + timedelta(days=days))

    def window(song, date):
        pre = pd.date_range(shift(date, -7), shift(date, -1))
        post = pd.date_range(shift(date, 1), shift(date, 7))
        before, after = series[song].reindex(pre), series[song].reindex(post)
        complete = bool(before.notna().all() and after.notna().all())
        pretotal, posttotal = (int(before.sum()), int(after.sum())) if complete else (None, None)
        return {
            'pre_start': str(pre[0].date()), 'pre_end': str(pre[-1].date()),
            'post_start': str(post[0].date()), 'post_end': str(post[-1].date()),
            'pre_observed_days': int(before.notna().sum()), 'post_observed_days': int(after.notna().sum()),
            'complete': complete, 'pre_streams': pretotal, 'post_streams': posttotal,
            'change': posttotal-pretotal if complete else None,
            'change_pct': (posttotal/pretotal-1)*100 if complete and pretotal else None,
            'percent_status': 'defined' if complete and pretotal else 'zero_pre_period' if complete else 'incomplete',
        }

    rows = []
    for (song, date), group in date_groups:
        release = pd.Timestamp(catalog.loc[song, 'first_released'])
        active_dates = set(pd.date_range(shift(date, -7), shift(date, 7))) - {date}
        other_dates = [pd.Timestamp(d) for d in primary_dates[song] if pd.Timestamp(d) != date]
        overlap = [str(d.date()) for d in other_dates if active_dates.intersection(set(pd.date_range(shift(d, -7), shift(d, 7))) - {d})]
        nearby = [str(d.date()) for d in other_dates if abs((d-date).days) <= 7]
        near_release = shift(date, -7) <= release <= shift(date, 7)
        before_release = shift(date, 7) < release
        age = (date-release).days
        row = {
            'song_id': song, 'recording_label': catalog.loc[song, 'recording_label'].strip(),
            'publication_date_utc': str(date.date()), 'first_released': str(release.date()),
            'track_age_days': age, 'release_inside_comparison_span': near_release,
            'entire_comparison_before_release': before_release,
            'release_phase': 'pre_release' if before_release else 'release_in_window' if near_release else 'first_28_days_after_release' if age <= 28 else 'established',
            'post_count': len(group), 'platforms': '|'.join(sorted(group.platform_selected.unique())),
            'band_authored_post_count': int(group.author_scope.eq('band_authored').sum()),
            'other_author_association_unverified_count': int(group.author_scope.ne('band_authored').sum()),
            'post_keys': '|'.join(group.post_key), 'post_ids': '|'.join(group.post_id),
            'permalinks': '|'.join(group.permalink), 'captions_json': json.dumps(group.evidence_excerpt.tolist(), ensure_ascii=False),
            'utc_publication_dates': '|'.join(sorted(group.utc_date.dt.strftime('%Y-%m-%d').unique())),
            'pacific_publication_dates': '|'.join(sorted(group.pacific_date.dt.strftime('%Y-%m-%d').unique())),
            'same_song_other_publications_within7': '|'.join(nearby),
            'same_song_window_overlap_dates': '|'.join(overlap),
            'same_song_window_overlap_count': len(overlap),
            'audio_use_verified': False, 'stream_attribution_available': False,
        }
        row.update(window(song, date))
        rows.append(row)
    events = pd.DataFrame(rows)
    assert len(events) == explicit[['song_id', 'utc_date']].drop_duplicates().shape[0]
    assert events.post_count.sum() == len(explicit)
    events.sort_values(['publication_date_utc', 'recording_label']).to_csv(args.output/'all_mapped_song_day_windows.csv', index=False)
    explicit.to_csv(args.output/'explicit_caption_post_references.csv', index=False)
    explicit[explicit.author_scope.eq('band_authored')].to_csv(args.output/'band_authored_caption_post_references.csv', index=False)
    explicit[explicit.author_scope.ne('band_authored')].to_csv(args.output/'other_author_unverified_references.csv', index=False)
    assert events.band_authored_post_count.gt(0).all(), 'Headline windows must have a band-authored reference.'

    sensitivity = []
    for (song, date), group in explicit.groupby(['song_id', 'pacific_date'], sort=True):
        row = {'song_id': song, 'recording_label': catalog.loc[song, 'recording_label'].strip(),
               'publication_date_pacific': str(date.date()), 'post_count': len(group), 'post_keys': '|'.join(group.post_key)}
        row.update(window(song, date))
        sensitivity.append(row)
    pd.DataFrame(sensitivity).to_csv(args.output/'pacific_anchor_sensitivity.csv', index=False)

    latest = []
    current_start, current_end = pd.Timestamp('2026-09-23'), pd.Timestamp('2026-10-20')
    previous_start, previous_end = pd.Timestamp('2026-08-26'), pd.Timestamp('2026-09-22')
    for song, s in series.items():
        current = s.reindex(pd.date_range(current_start, current_end))
        previous = s.reindex(pd.date_range(previous_start, previous_end))
        assert current.notna().all() and previous.notna().all()
        c, p = int(current.sum()), int(previous.sum())
        original = prior28.loc[prior28.song_id.eq(song)].iloc[0]
        assert c == int(original.current_streams) and p == int(original.previous_streams)
        mapped = explicit[explicit.song_id.eq(song)]
        currentrefs = mapped[mapped.date.between(current_start, current_end)]
        prevrefs = mapped[mapped.date.between(previous_start, previous_end)]
        latest.append({'song_id': song, 'recording_label': catalog.loc[song, 'recording_label'].strip(),
                       'current_start': str(current_start.date()), 'current_end': str(current_end.date()),
                       'previous_start': str(previous_start.date()), 'previous_end': str(previous_end.date()),
                       'current_streams': c, 'previous_streams': p, 'change': c-p,
                       'change_pct': (c/p-1)*100 if p else None,
                       'current_explicit_references': len(currentrefs), 'previous_explicit_references': len(prevrefs),
                       'last_explicit_reference': str(mapped.date.max().date()) if len(mapped) else None})
    recent = pd.DataFrame(latest).sort_values('change', ascending=False)
    recent.to_csv(args.output/'latest28_song_alignment.csv', index=False)
    posts['date'] = pd.to_datetime(posts.published_utc, utc=True).dt.tz_localize(None).dt.normalize()
    posts[posts.date.between(previous_start, current_end)].merge(postevidence[['post_key', 'description']], on='post_key', validate='1:1').to_csv(args.output/'recent_retained_posts.csv', index=False)
    eventmap['promotion_timestamp'] = pd.to_datetime(eventmap.promotion_date, format='%Y-%m-%d', errors='coerce')
    eventmap['event_timestamp'] = pd.to_datetime(eventmap.event_date, format='%Y-%m-%d', errors='coerce')
    recent_events = eventmap[eventmap.promotion_timestamp.between(previous_start, current_end) | eventmap.event_timestamp.between(previous_start, current_end)]
    recent_events.to_csv(args.output/'recent_event_mentions.csv', index=False)

    # Catalog release dates and explicit caption claims remain separate sources.
    release_rows = []
    for _, r in eventmap[eventmap.event_date_status.eq('retained_release_metadata')].iterrows():
        for song in json.loads(r.song_ids):
            row = {'song_id': song, 'recording_label': catalog.loc[song, 'recording_label'].strip(),
                   'release_id': r.release_id, 'release_title': r.release_title, 'release_date': r.event_date,
                   'date_evidence': r.event_date_status}
            row.update(window(song, pd.Timestamp(r.event_date)))
            release_rows.append(row)
    pd.DataFrame(release_rows).to_csv(args.output/'catalog_release_windows.csv', index=False)

    complete = events[events.complete]
    established = complete[complete.release_phase.eq('established')]
    nonoverlap = established[established.same_song_window_overlap_count.eq(0)]
    def tally(frame):
        return {'events': len(frame), 'positive': int(frame.change.gt(0).sum()),
                'negative': int(frame.change.lt(0).sum()), 'unchanged': int(frame.change.eq(0).sum()),
                'median_change': float(frame.change.median()) if len(frame) else None,
                'sum_not_valid_due_overlapping_windows': True}
    summary = {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'input_package': str(args.package.resolve()),
        'source_sha256': hashes,
        'method': {'comparison': '7 UTC daily stream bins before versus 7 after UTC publication calendar date from published_utc; day 0 excluded',
                   'seven_day_window_fixed_before_values': True,
                   'anchor_note': 'UTC primary chosen after source-schema review; initial Pacific alignment retained as sensitivity, with no lag selection by outcome.',
                   'same_song_same_calendar_date_references_grouped': True,
                   'sensitivity': 'Also computed with Pacific publication calendar dates; neither rebins UTC streams into Pacific.',
                   'outcome': 'streams only; no daily unique audience totals or lifetime social metrics',
                   'interpretation': 'Descriptive temporal alignment. Overlap, release timing, selection, and missing exposure/link data prevent causal or independent event interpretation.',
                   'latest_comparison': '2026-09-23 to 2026-10-20 versus 2026-08-26 to 2026-09-22'},
        'map': {'posts': len(posts), 'explicit_refs': len(explicit), 'explicit_posts': explicit.post_key.nunique(),
                'band_authored_explicit_refs': int(explicit.author_scope.eq('band_authored').sum()),
                'band_authored_explicit_posts': explicit.loc[explicit.author_scope.eq('band_authored'), 'post_key'].nunique(),
                'band_authored_song_day_events': int(events.band_authored_post_count.gt(0).sum()),
                'other_author_unverified_refs_not_headline_marketing': int(explicit.author_scope.ne('band_authored').sum()),
                'explicit_song_day_events': len(events), 'songs_with_explicit_references': explicit.song_id.nunique(),
                'first_reference': explicit.date.min().strftime('%Y-%m-%d'), 'last_reference': explicit.date.max().strftime('%Y-%m-%d'),
                'status_counts': refs.status.value_counts().to_dict(),
                'platform_references': explicit.platform_selected.value_counts().to_dict(),
                'author_scopes': explicit.author_scope.value_counts().to_dict(),
                'references_with_next_utc_date': int(explicit.pacific_date.ne(explicit.utc_date).sum())},
        'complete_windows': tally(complete), 'incomplete_windows': len(events)-len(complete),
        'release_phases': complete.release_phase.value_counts().to_dict(),
        'established_track_windows': tally(established), 'established_without_same_song_window_overlap': tally(nonoverlap),
        'windows_with_same_song_overlap': int(complete.same_song_window_overlap_count.gt(0).sum()),
        'recent': {'streams_current': int(recent.current_streams.sum()), 'streams_previous': int(recent.previous_streams.sum()),
                   'explicit_refs_current': int(recent.current_explicit_references.sum()), 'explicit_refs_previous': int(recent.previous_explicit_references.sum()),
                   'all_posts_current': len(posts[posts.date.between(current_start, current_end)]),
                   'all_posts_previous': len(posts[posts.date.between(previous_start, previous_end)]),
                   'event_mentions_or_dates': len(recent_events)},
        'validation': {'source_hashes_unchanged': all(hashlib.sha256((args.package/k).read_bytes()).hexdigest()==v for k,v in hashes.items()),
                       'source_song_day_unique': True, 'all_used_values_observed': True,
                       'source_28day_comparison_exact_match': True, 'source_post_identity_unique': True,
                       'explicit_song_mapping_catalog_valid': True, 'no_performance_metric_fanout': True},
    }
    assert summary['validation']['source_hashes_unchanged']
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('\nESTABLISHED TRACK WINDOWS:')
    print(established[['recording_label','publication_date_utc','post_count','platforms','pre_streams','post_streams','change','change_pct','same_song_window_overlap_count']].sort_values('change',ascending=False).to_string(index=False))
    print('\nLATEST 28:')
    print(recent.to_string(index=False))


if __name__ == '__main__':
    main()
