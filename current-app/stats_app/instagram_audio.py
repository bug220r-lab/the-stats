"""Package later Instagram post audio evidence without changing Story mappings."""
from __future__ import annotations

from pathlib import Path

from stats_app.analysis_repository import AnalysisRepository
from stats_app.meta_collection import _read_csv, validate_collection_table
from stats_app.meta_followup import SupplementSpec, build_evidence_supplement
from stats_app.storage import StorageError


VERSION = "instagram-audio-20261023"
LABEL = "Instagram audio review · October 23, 2026 · post evidence; Stories unresolved"
PREFIX = "social/instagram_audio_20261023/"
RAW_PREFIX = "raw/instagram_audio_20261023/"
PREDECESSOR_PREFIX = "raw/instagram_audio_20261023_predecessor_metadata/"
STORY_IDS = {"17965560240198897", "18117197771279451", "18114350993331569",
             "18078399140713885", "18430983631182631", "18216593050358711"}
SPEC = SupplementSpec(
    namespace="instagram_audio_20261023", lineage_key="instagram_audio",
    title="Instagram audio review", handoff_filename="INSTAGRAM_AUDIO_HANDOFF.md",
    evidence_type="Native Instagram post audio evidence and separate unresolved Story review; previous snapshots unchanged",
    limitations=(
        "A verified native audio label belongs to the inspected post, not to a separate Story.",
        "Native labels are current at capture; historical audio revisions and exact Spotify recording identity remain unverified.",
        "Six retained October Stories remain unconfirmed; a similar image or publication date cannot establish their audio.",
        "An Instagram audio label does not establish Spotify conversion, paid exposure or a causal effect.",
        "Original October 20 baseline membership remains unverified.",
    ),
)


def build_instagram_audio(parent, collection_root, output_dir, zip_path):
    """Build an additive package; source interpretation is independently audited."""
    if not isinstance(parent, AnalysisRepository):
        parent = AnalysisRepository(parent)
    if parent.metadata.get("analysis_version") != "meta-followup-20261023":
        raise StorageError("This Instagram audio review must preserve the meta-followup-20261023 predecessor.")
    normalized = Path(collection_root) / "normalized"
    tables = {}
    for filename in ("post_audio_evidence.csv", "story_match_status.csv", "collection_status.csv"):
        if not (normalized / filename).is_file():
            raise StorageError("Instagram audio review requires normalized/" + filename)
        tables[filename] = validate_collection_table(_read_csv((normalized / filename).read_bytes(), filename), filename)
    _validate_scope(tables, parent)
    return build_evidence_supplement(parent, collection_root, output_dir, zip_path,
                                    version_key=VERSION, label=LABEL, spec=SPEC)


def _validate_scope(tables, parent):
    """Reject promoted Story claims or recording certainty absent from this review."""
    posts, stories = tables["post_audio_evidence.csv"], tables["story_match_status.csv"]
    post_columns = {"post_id", "native_audio_label", "native_audio_title", "native_audio_artist",
                    "native_audio_url", "native_audio_id", "native_audio_label_verified", "audio_evidence_status",
                    "spotify_catalog_candidate_id", "catalog_match_status", "spotify_recording_identity_verified",
                    "story_relationship_status", "evidence_ref"}
    story_columns = {"post_id", "mapping_status", "assigned_song_id", "audio_use_verified",
                     "matched_feed_post_id", "evidence_ref"}
    if not post_columns.issubset(posts) or not story_columns.issubset(stories):
        raise StorageError("Instagram audio evidence is missing explicit identity or verification fields.")
    if len(posts) != 3 or posts.post_id.str.strip().eq("").any() or posts.post_id.duplicated().any():
        raise StorageError("This review requires three distinct inspected posts.")
    if len(stories) != 6 or set(stories.post_id) != STORY_IDS:
        raise StorageError("Story status must retain the six exact predecessor Story IDs once each.")
    if not (stories.mapping_status.eq("unresolved_after_personal_post_search").all()
            and stories.audio_use_verified.str.lower().eq("false").all()
            and stories.assigned_song_id.eq("").all() and stories.matched_feed_post_id.eq("").all()):
        raise StorageError("This post inspection cannot assign audio or a feed match to the unresolved Stories.")
    if not posts.spotify_recording_identity_verified.str.lower().eq("false").all():
        raise StorageError("A native title and artist cannot establish exact Spotify recording identity.")
    if not posts.story_relationship_status.eq("no_verified_link_to_six_stories").all():
        raise StorageError("Post audio must remain separate from the six Story relationships.")
    flags = posts.native_audio_label_verified.str.lower()
    if not flags.isin({"true", "false"}).all() or flags.eq("true").sum() != 1:
        raise StorageError("This review contains exactly one verified native post audio label.")
    verified = posts[flags.eq("true")]
    unseen = posts[flags.eq("false")]
    for column in ("native_audio_label", "native_audio_title", "native_audio_artist", "native_audio_url",
                   "native_audio_id", "evidence_ref", "spotify_catalog_candidate_id"):
        if verified[column].str.strip().eq("").any():
            raise StorageError("Verified native post audio needs its label, native identity and source evidence.")
    if not (verified.audio_evidence_status.eq("native_label_verified").all()
            and verified.catalog_match_status.eq("unique_title_artist_match").all()
            and unseen.audio_evidence_status.eq("not_visible_in_inspected_post").all()
            and unseen.catalog_match_status.eq("not_applicable").all()
            and unseen.spotify_catalog_candidate_id.eq("").all()):
        raise StorageError("Post audio status must distinguish native labels from unavailable labels.")
    if any(frame.evidence_ref.str.strip().eq("").any() for frame in (posts, stories)):
        raise StorageError("Every inspected post and unresolved Story needs a source evidence reference.")
    catalog_path = "spotify/cleaned/recordings.csv"
    if catalog_path not in parent.tables:
        raise StorageError("The parent Spotify catalog is required to check recording candidates.")
    catalog = parent.table(catalog_path, raw=True)
    for row in verified.itertuples():
        match = catalog[catalog.song_id.eq(row.spotify_catalog_candidate_id)]
        if len(match) != 1 or match.title.iloc[0].casefold().strip() != row.native_audio_title.casefold().strip():
            raise StorageError("The proposed Spotify candidate must match a retained catalog title and ID.")
