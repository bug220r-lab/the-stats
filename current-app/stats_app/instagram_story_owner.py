"""Add owner archive identity and source-post evidence, with music unresolved."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from stats_app.analysis_repository import AnalysisRepository
from stats_app.instagram_audio import STORY_IDS
from stats_app.meta_collection import _read_csv, validate_collection_table
from stats_app.meta_followup import SupplementSpec, build_evidence_supplement
from stats_app.storage import StorageError


VERSION = "instagram-story-owner-20261023"
LABEL = "Instagram owner archive · October 23, 2026 · identities and source posts; songs unresolved"
PREFIX = "social/instagram_story_owner_20261023/"
RAW_PREFIX = "raw/instagram_story_owner_20261023/"
PREDECESSOR_PREFIX = "raw/instagram_story_owner_20261023_predecessor_metadata/"
SPEC = SupplementSpec(
    namespace="instagram_story_owner_20261023", lineage_key="instagram_story_owner",
    title="Instagram owner archive review", handoff_filename="INSTAGRAM_STORY_OWNER_HANDOFF.md",
    evidence_type="Verified owner archive identity bridges and embedded source meme posts; six Story songs remain unresolved",
    limitations=(
        "The six owner archive identities are verified by account, calendar date and identical artwork; music is not verified.",
        "The owner web player displayed no native audio labels. Absence of a label does not establish silence.",
        "Four embedded See Post links identify third-party meme provenance, not Spotify destinations or the Story soundtrack.",
        "Audio listening or fingerprinting was not performed; the browser did not support the attempted blob media download.",
        "No lifetime metrics, historical statistics, link clicks or Spotify conversions are inferred. Original October 20 baseline membership remains unverified.",
    ),
)


def _all(frame, column, expected):
    return frame[column].str.lower().eq(expected).all()


def build_instagram_story_owner(parent, collection_root, output_dir, zip_path):
    if not isinstance(parent, AnalysisRepository):
        parent = AnalysisRepository(parent)
    if parent.metadata.get("analysis_version") != "instagram-audio-20261023":
        raise StorageError("Owner archive review requires the instagram-audio-20261023 predecessor.")
    tables = {}
    for filename in ("story_owner_review.csv", "story_source_links.csv", "collection_status.csv"):
        path = Path(collection_root) / "normalized" / filename
        if not path.is_file():
            raise StorageError("Owner archive review requires normalized/" + filename)
        tables[filename] = validate_collection_table(_read_csv(path.read_bytes(), filename), filename)
    stories, links = tables["story_owner_review.csv"], tables["story_source_links.csv"]
    required_stories = {"post_id", "archive_story_id", "instagram_native_story_id", "archive_source_url", "published_local",
        "publication_timezone", "selected_account_id", "account_handle", "viewer_account", "native_archive_identity_verified",
        "audio_use_verified", "assigned_song_id", "native_audio_label_visible", "audio_label_status", "mapping_status",
        "audio_listening_or_fingerprinting_performed", "candidate_song_title", "candidate_song_ids", "prior_mapping_status",
        "embedded_source_post_url", "source_post_audio_as_story_audio_verified", "evidence_ref"}
    required_links = {"post_id", "archive_story_id", "destination_url", "destination_scope", "link_type",
        "source_post_link_verified", "story_audio_use_verified", "spotify_destination_verified", "click_metric_value",
        "click_metric_status", "stream_attribution_available", "evidence_ref"}
    if not required_stories.issubset(stories) or not required_links.issubset(links):
        raise StorageError("Owner review requires explicit identity, audio availability and source-post scope fields.")
    if len(stories) != 6 or set(stories.post_id) != STORY_IDS or stories.archive_story_id.duplicated().any():
        raise StorageError("Retain each of the six Stories and its distinct owner archive identity exactly once.")
    if not (_all(stories, "native_archive_identity_verified", "true") and _all(stories, "audio_use_verified", "false")
            and _all(stories, "native_audio_label_visible", "false") and stories.assigned_song_id.eq("").all()
            and _all(stories, "audio_listening_or_fingerprinting_performed", "false")
            and _all(stories, "source_post_audio_as_story_audio_verified", "false")
            and stories.mapping_status.eq("unresolved_after_owner_archive_review").all()
            and stories.audio_label_status.eq("not_visible_in_owner_archive_player").all()):
        raise StorageError("Verified owner archive identity must remain separate from unresolved song/audio identity.")
    prior = parent.table("social/meta_followup/story_song_map.csv", raw=True).set_index("post_id")
    for row in stories.itertuples():
        old = prior.loc[row.post_id]
        for column, old_column in (("published_local", "published_local"), ("publication_timezone", "publication_timezone"),
                ("selected_account_id", "selected_account_id"), ("account_handle", "account_handle"),
                ("candidate_song_title", "candidate_song_title"), ("candidate_song_ids", "candidate_song_ids"),
                ("prior_mapping_status", "mapping_status")):
            if getattr(row, column) != old[old_column]:
                raise StorageError("An inherited Story identity, publication field or candidate was changed.")
        if row.viewer_account != row.account_handle or row.instagram_native_story_id != old.permalink.rstrip("/").split("/")[-1]:
            raise StorageError("Owner viewer or public Story ID conflicts with retained identity.")
        if f"/stories/archive/{row.archive_story_id}/" not in row.archive_source_url:
            raise StorageError("Owner archive URL and identity differ.")
    if len(links) != 4 or links.post_id.duplicated().any() or not set(links.post_id).issubset(STORY_IDS):
        raise StorageError("This review requires four distinct embedded source-post links.")
    if not (links.destination_scope.eq("third_party_source_meme_post").all() and links.link_type.eq("embedded_see_post").all()
            and _all(links, "source_post_link_verified", "true") and _all(links, "story_audio_use_verified", "false")
            and _all(links, "spotify_destination_verified", "false") and _all(links, "stream_attribution_available", "false")
            and links.click_metric_value.eq("").all() and links.click_metric_status.eq("not_collected").all()):
        raise StorageError("Embedded meme links cannot become soundtrack, Spotify destination or click evidence.")
    story_index = stories.set_index("post_id")
    for row in links.itertuples():
        story = story_index.loc[row.post_id]
        destination = urlparse(row.destination_url)
        if (destination.scheme != "https" or destination.hostname != "www.instagram.com" or not destination.path.startswith("/p/")
                or row.archive_story_id != story.archive_story_id or row.destination_url != story.embedded_source_post_url):
            raise StorageError("Source meme URL must match its exact Story link evidence.")
    if any(frame.evidence_ref.str.strip().eq("").any() for frame in (stories, links)):
        raise StorageError("Owner identity and source links need evidence references.")
    return build_evidence_supplement(parent, collection_root, output_dir, zip_path,
                                    version_key=VERSION, label=LABEL, spec=SPEC)
