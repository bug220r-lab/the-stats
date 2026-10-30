"""Retain direct post audio labels separately from unresolved Story identities."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import pandas as pd
from stats_app.analysis_repository import load_registered_analysis
from stats_app.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / 'data/collection/instagram-story-audio-20261023'


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    parent = load_registered_analysis(load_settings().data_dir, 'meta-followup-20261023')
    prior_map = parent.table('social/meta_collection/mapping/post_song_map.csv').fillna('')
    catalog = parent.table('spotify/cleaned/recordings.csv').fillna('')
    output = COLLECTION / 'normalized'
    output.mkdir(exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError('Preserving existing normalized outputs; choose a new collection.')
    inputs = [('reel-DcCDTzAT3F7', 'DcCDTzAT3F7', 'August 14'),
              ('latest-feed-post-DcHBIVGDnya-final', 'DcHBIVGDnya', 'August 16'),
              ('pinned-song-DWH8LXSDp1e', 'DWH8LXSDp1e', 'March 20')]
    posts = []
    for name, shortcode, date_text in inputs:
        meta = json.loads((COLLECTION / 'post_search' / (name + '.json')).read_text(encoding='utf-8'))
        native_text = (COLLECTION / 'post_search' / (name + '.txt')).read_text(encoding='utf-8')
        prior = prior_map[prior_map.permalink.str.contains('/' + shortcode + '/', regex=False)]
        assert len(prior) == 1
        prior = prior.iloc[0]
        timestamps = [r['datetime'] for r in meta['visible_times'] if r['text'] == date_text]
        assert len(timestamps) == 1
        published = datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))
        assert published.strftime('%Y-%m-%dT%H:%M') == str(prior.published_utc)[:16]
        label = meta.get('native_audio_label', '')
        audio_url = meta.get('native_audio_url', '')
        verified = bool(label and audio_url)
        candidate = ''
        if verified:
            assert label in native_text and ('instagram.com' + urlparse(audio_url).path) in native_text
            assert label == '[REDACTED] • The Cut (Starts Tomorrow)'
            matches = catalog[catalog.title.eq('The Cut (Starts Tomorrow)') & catalog.artist_id.eq('6X14XfGTmB560PF063wXDk')]
            assert len(matches) == 1
            candidate = str(matches.iloc[0].song_id)
        refs = ';'.join('post_search/' + name + ext for ext in ('.json', '.txt', '.png'))
        posts.append({
            'post_id': str(prior.post_id), 'shortcode': shortcode, 'source_url': meta['source_url'],
            'content_kind': meta['content_kind'], 'selected_account_id': str(prior.selected_account_id),
            'account_handle': 'redactedbandoh', 'viewer_account': meta['viewer_account'],
            'published_at_utc': published.isoformat(), 'published_local': published.astimezone(ZoneInfo('America/Los_Angeles')).isoformat(),
            'publication_timezone': 'UTC native HTML time; Pacific display derived with America/Los_Angeles',
            'inherited_published_local': prior.published_local, 'inherited_publication_precision': 'minute',
            'native_audio_label': label, 'native_audio_title': 'The Cut (Starts Tomorrow)' if verified else '',
            'native_audio_artist': '[REDACTED]' if verified else '', 'native_audio_url': audio_url,
            'native_audio_id': audio_url.rstrip('/').rsplit('/', 1)[-1] if verified else '',
            'native_audio_label_verified': verified,
            'audio_evidence_status': 'native_label_verified' if verified else 'not_visible_in_inspected_post',
            'spotify_catalog_candidate_id': candidate,
            'catalog_match_status': 'unique_title_artist_match' if verified else 'not_applicable',
            'spotify_recording_identity_verified': False,
            'story_relationship_status': 'no_verified_link_to_six_stories',
            'caption_song_mentions_json': json.dumps(meta.get('caption_mentions', []), ensure_ascii=False),
            'captured_at_utc': meta['captured_at_utc'], 'evidence_ref': refs,
            'identity_source_table': 'social/meta_collection/mapping/post_song_map.csv',
            'reporting_basis': 'Current native audio metadata on an individual post; no period activity or conversion metric',
        })
    pd.DataFrame(posts).to_csv(output / 'post_audio_evidence.csv', index=False)
    prior_stories = parent.table('social/meta_followup/story_song_map.csv').fillna('')
    assert len(prior_stories) == 6 and prior_stories.post_id.astype(str).nunique() == 6
    stories = []
    for r in prior_stories.to_dict('records'):
        stories.append({
            'post_id': str(r['post_id']), 'published_local': r['published_local'],
            'platform_selected': r['platform_selected'], 'selected_account_id': str(r['selected_account_id']),
            'prior_mapping_status': r['mapping_status'], 'candidate_song_title': r['candidate_song_title'],
            'mapping_status': 'unresolved_after_personal_post_search', 'assigned_song_id': '',
            'audio_use_verified': False, 'matched_feed_post_id': '',
            'reason': 'No direct identity/audio bridge from inspected feed posts or Reels to this expired Story. Native audio on another post is not Story audio evidence.',
            'evidence_ref': 'post_search/profile-post-grid.txt;post_search/reel-grid.txt;post_search/reel-DcCDTzAT3F7.json',
            'prior_evidence_table': 'social/meta_followup/story_song_map.csv',
            'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
            'captured_at_utc': '',
        })
    pd.DataFrame(stories).to_csv(output / 'story_match_status.csv', index=False)
    status = [
        ('post_native_audio', 'one_native_post_label_verified', 'Three posts inspected. The Aug14 Reel labels The Cut (Starts Tomorrow) by [REDACTED]. Two inspected carousels expose no native audio label. Exact Spotify recording identity is not verified.', 'normalized/post_audio_evidence.csv'),
        ('six_recent_stories', 'all_six_unresolved', 'No verified song/audio assignment or feed-to-Story identity bridge. Earlier candidate and artwork interpretations remain qualified and unchanged.', 'normalized/story_match_status.csv'),
        ('public_post_search', 'scoped_search_completed', 'Inspected current band Posts and Reels grids using jude__lewis. Latest visible feed post Aug16 and Reel Aug14 agree with retained exports. No October feed/Reel counterpart found; this is not proof of complete account history.', 'post_search/profile-post-grid.txt;post_search/reel-grid.txt'),
        ('baseline_and_prior_data', 'preserved_membership_unverified', 'Preserve all predecessor assets and databases. Original October20 baseline membership remains unverified. No statistical recalculation, attributed streams or lifetime metric update.', 'preflight_preservation.json'),
        ('tiktok', 'excluded', 'No TikTok collection.', 'User scope instruction'),
    ]
    pd.DataFrame([dict(zip(['dataset','status','detail','evidence_ref'], row), captured_at_utc='') for row in status]).to_csv(output / 'collection_status.csv', index=False)
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'parent_version': 'meta-followup-20261023',
                'source_capture_timestamps': 'Only explicit JSON captured_at_utc fields represent capture times; file timestamps are not substituted.',
                'files': [{'path': p.relative_to(COLLECTION).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(COLLECTION.rglob('*')) if p.is_file()]}
    (COLLECTION / 'normalization_receipt.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'inspected_posts': len(posts), 'verified_native_post_labels': sum(r['native_audio_label_verified'] for r in posts), 'unresolved_stories': len(stories), 'confirmed_story_audio': 0}))


if __name__ == '__main__':
    main()
