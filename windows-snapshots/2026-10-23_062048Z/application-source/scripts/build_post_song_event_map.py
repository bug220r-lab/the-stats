"""Build a separate, conservative post/song/event evidence bridge, without network access.

Read an immutable registered analysis package and write only a new output folder.
References describe what a caption/link says; they do not establish audio use,
exposure, listening, conversion, or event attendance. No performance metrics join
to the many-to-many bridge and no artist streams are allocated to posts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stats_app.analysis_repository import AnalysisRepository, load_registered_analysis

VERSION = "1.1.0"
POSTS = "social/posts_latest.csv"
SNAPSHOTS = "social/post_snapshots.csv"
RECORDINGS = "spotify/cleaned/recordings.csv"
RELEASES = "spotify/cleaned/release_metadata.csv"
IDENTITY = ["platform_selected", "selected_account_id", "account_handle", "post_id",
            "author_account_id", "author_username", "author_scope", "published_local",
            "publication_date", "published_utc", "reporting_timezone", "post_type",
            "permalink", "source_file", "source_url", "source_record", "snapshot_timestamp",
            "snapshot_class", "reporting_window_start", "reporting_window_end"]
TRACK_URL = re.compile(r"(?:https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/|spotify:track:)([A-Za-z0-9]{22})(?![A-Za-z0-9])", re.I)
EXACT_DATE = re.compile(r"(?<!\d)(\d{1,2})([/\.])(\d{1,2})\2(\d{4}|\d{2})(?!\d)")
MONTH_DATE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th|t)?(?:,?\s+(20\d{2}))?\b", re.I)
RESOLVED = {"verified_spotify_link", "verified_catalog_identifier", "explicit_caption_reference"}


def text(value):
    return "" if value is None else str(value)


def normalized(value):
    value = unicodedata.normalize("NFKC", text(value)).casefold()
    return " ".join(re.findall(r"[^\W_]+", value, re.UNICODE))


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def stable_id(prefix, *parts):
    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
    return prefix + "_" + hashlib.sha256(raw).hexdigest()[:20]


def contains_title(caption, title):
    return (" " + normalized(title) + " ") in (" " + normalized(caption) + " ")


def excerpt(caption, needle="", length=800):
    # Complete original captions remain in the evidence table/JSON.
    start = caption.casefold().find(needle.casefold()) if needle else 0
    start = max(0, start - 160)
    return caption[start:start + length]


def song_references(caption, recordings):
    """Resolve only known IDs or title references, retaining version ambiguity.

    Punctuation/case normalization is not fuzzy matching. Generic-word titles
    require a song/music/live cue or a title-led hashtag caption. Nickname uses
    such as 'Meet Jude, The Funny Guy' are candidates, not song assignments.
    """
    caption = text(caption)
    by_id = {r["song_id"]: r for r in recordings}
    groups = defaultdict(list)
    for recording in recordings:
        groups[normalized(recording["title"])].append(recording)
    refs, covered_ids = [], set()
    for match in TRACK_URL.finditer(caption):
        song_id = match.group(1)
        row = by_id.get(song_id)
        refs.append(dict(song_id=song_id if row else "", candidate_song_ids=[song_id],
                         recording_label=row["recording_label"] if row else "",
                         status="verified_spotify_link" if row else "uncatalogued_spotify_link",
                         evidence_text=match.group(0), evidence_excerpt=excerpt(caption, match.group(0)),
                         reason="Exact retained catalog ID in explicit Spotify track URL/URI; no destination request made." if row else "Track ID is explicit but absent from the retained catalog; requires identity review."))
        covered_ids.add(song_id)
    for song_id, row in by_id.items():
        if song_id not in covered_ids and re.search(r"(?<![A-Za-z0-9])" + re.escape(song_id) + r"(?![A-Za-z0-9])", caption):
            refs.append(dict(song_id=song_id, candidate_song_ids=[song_id], recording_label=row["recording_label"],
                             status="verified_catalog_identifier", evidence_text=song_id,
                             evidence_excerpt=excerpt(caption, song_id), reason="Exact stable catalog ID appears in caption; no live verification."))
            covered_ids.add(song_id)
    for title, candidates in groups.items():
        if not contains_title(caption, title):
            continue
        available = [r for r in candidates if r["song_id"] not in covered_ids]
        if not available:
            continue
        normalized_caption = normalized(caption)
        # A matching version label or explicit Lab Tapes qualification can resolve
        # a title shared by two recordings; bare release years never resolve it.
        qualified = [r for r in candidates if normalized(r["recording_label"]) != title and contains_title(caption, r["recording_label"])]
        if not qualified and re.search(re.escape(title) + r"\s+(?:from\s+)?lab tapes\b", normalized_caption) and len(candidates) > 1:
            qualified = [r for r in candidates if "lab tapes" in normalized(r.get("release_memberships", ""))]
        if not qualified and any(r["song_id"] in covered_ids for r in candidates):
            # A bare title repeats the explicitly linked recording, not every
            # other recording of the same title.
            continue
        chosen = qualified if len(qualified) == 1 else candidates
        status, reason = "explicit_caption_reference", "Exact normalized title reference to one retained recording; does not establish audio use."
        if len(chosen) != 1:
            status, reason = "ambiguous_recording_version", "This exact title has multiple retained recordings; caption does not identify a version."
        elif title == "funny guy" and re.search(r"\bmeet\b.{0,70}\bfunny guy\b|\bfunny guy\b.{0,25}\blead singer\b", caption, re.I | re.S):
            status, reason = "candidate_non_song_context", "Title also describes a person/nickname in this caption; no song assignment."
        elif title in {"crawl", "this machine", "john doe", "waste away", "method acting"}:
            title_led = normalized_caption.startswith(title) and ("#" in caption or normalized_caption == title)
            musical = bool(re.search(r"\b(songs?|tracks?|single|album|listen|stream|music|live)\b", caption, re.I))
            if not (title_led or musical or qualified):
                status, reason = "candidate_generic_phrase", "Exact words found without an unambiguous musical context."
        assigned = chosen[0] if status in RESOLVED else None
        refs.append(dict(song_id=assigned["song_id"] if assigned else "", candidate_song_ids=[r["song_id"] for r in chosen],
                         recording_label=assigned["recording_label"] if assigned else "",
                         status=status, evidence_text=candidates[0]["title"], evidence_excerpt=excerpt(caption, candidates[0]["title"]), reason=reason))
    # Shortened titles are review hints only, even if there is one candidate.
    aliases = {"docs": "the devil wears docs", "son": "son hidden track", "the cut": "the cut starts tomorrow"}
    for alias, full_title in aliases.items():
        candidates = groups.get(full_title, [])
        if candidates and contains_title(caption, alias) and not contains_title(caption, full_title):
            if any(set(r["candidate_song_ids"]) & {s["song_id"] for s in candidates} for r in refs):
                continue
            refs.append(dict(song_id="", candidate_song_ids=[r["song_id"] for r in candidates], recording_label="",
                             status="candidate_short_title", evidence_text=alias,
                             evidence_excerpt=excerpt(caption, alias), reason="Abbreviated title is only a review candidate; no stable recording assigned."))
    if not refs:
        status = "explicit_no_song_claim" if re.search(r"\bno (?:song|music|audio)\b", caption, re.I) else "unknown_no_identified_song"
        refs.append(dict(song_id="", candidate_song_ids=[], recording_label="", status=status,
                         evidence_text="", evidence_excerpt=excerpt(caption),
                         reason="Caption explicitly claims no song/music/audio; not independently verified." if status == "explicit_no_song_claim" else "No explicit catalog link or unambiguous title reference in retained text. Unknown does not mean no song."))
    return refs


def caption_dates(caption):
    """Only fully specified source dates become event dates; never add a year."""
    dates, occupied = [], []
    for match in EXACT_DATE.finditer(caption):
        year = int(match.group(4)); year = year + 2000 if year < 100 else year
        try:
            parsed = date(year, int(match.group(1)), int(match.group(3))).isoformat()
        except ValueError:
            continue
        dates.append((parsed, "explicit_caption_date", match.group(0)))
        occupied.append(match.span())
    for match in MONTH_DATE.finditer(caption):
        raw_month = match.group(1)[:3].title()
        month = datetime.strptime(raw_month, "%b").month
        try:
            parsed = date(int(match.group(3)), month, int(match.group(2))).isoformat() if match.group(3) else ""
        except ValueError:
            continue
        dates.append((parsed, "explicit_caption_date" if parsed else "year_not_stated", match.group(0)))
        occupied.append(match.span())
    for match in re.finditer(r"(?<!\d)\d{1,2}/\d{1,2}(?![/\d])", caption):
        if not any(lo <= match.start() < hi for lo, hi in occupied):
            # 'part 2/3' is not a date candidate.
            preceding = caption[max(0, match.start() - 12):match.start()].casefold()
            if "part" not in preceding:
                dates.append(("", "year_not_stated", match.group(0)))
    return list(dict.fromkeys(dates))


def caption_events(caption, recordings):
    """Return explicitly described promotions/event mentions, never occurrence proof."""
    stripped = caption
    for recording in recordings:
        stripped = re.sub(re.escape(recording["title"]), "[catalog title]", stripped, flags=re.I)
    kinds = []
    if re.search(r"\b(music video|lyric video)\b", stripped, re.I):
        kinds.append("music_video_promotion")
    elif (re.search(r"\b(release|released|unreleased|out now|out everywhere|new song|new single|new album|comes out|is out|will be out)\b", stripped, re.I)
          or (re.search(r"\bnew\b", stripped, re.I) and caption_dates(stripped) and "[catalog title]" in stripped)):
        kinds.append("music_release_promotion")
    if re.search(r"\b(show|shows|doors|tickets|playing|live at|presale|pre.?show)\b|porch.?rokr|@therialtotheatre|@ziggysypsilanti|@thewinchesterbar", stripped, re.I):
        kinds.append("show_or_live_event_mention")
    if re.search(r"\b(merch|episode|canvas|playlist|campaign)\b", stripped, re.I):
        kinds.append("other_promotion_mention")
    if not kinds:
        return []
    event_kind = kinds[0] if len(kinds) == 1 else "mixed_promotion_or_event_mention"
    dates = caption_dates(stripped)
    if not dates:
        relative = re.findall(r"\b(?:today|tonight|tomorrow|yesterday|next\s+\w+|this\s+(?:Friday|Saturday|Sunday|Monday|Tuesday|Wednesday|Thursday))\b", stripped, re.I)
        dates = [("", "relative_date_unresolved" if relative else "event_date_not_stated", " | ".join(dict.fromkeys(relative)))]
    return [dict(event_kind=event_kind, mentioned_event_kinds=kinds,
                 event_date=day if len(kinds) == 1 else "",
                 candidate_event_date=day if len(kinds) > 1 else "",
                 event_date_status="explicit_date_event_association_unresolved" if day and len(kinds) > 1 else status, date_evidence=source,
                 event_occurrence_status="caption_claim_not_independently_verified", evidence_excerpt=excerpt(caption),
                 time_evidence=" | ".join(re.findall(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", caption, re.I)),
                 reason="Publication is a dated promotion/mention. Claimed event date remains separate; absent years and relative dates are not guessed.")
            for day, status, source in dates]


def records(repo, path):
    # JSON conversion gives explicit None, not pandas missing sentinels.
    return json.loads(repo.table(path).to_json(orient="records", force_ascii=False))


def csv_value(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    value = "" if value is None else value
    # JSON carries exact source text. CSV gets formula-injection protection.
    return "'" + value if isinstance(value, str) and value[:1] in "=+-@\t\r" else value


def write_rows(output, name, rows):
    (output / (name + ".json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = list(dict.fromkeys(k for row in rows for k in row)) or ["no_records"]
    with (output / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: csv_value(v) for k, v in row.items()} for row in rows)


def build(repo, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output must be a new directory; nothing is overwritten.")
    if output == repo.db_path or repo.db_path.is_relative_to(output):
        raise ValueError("Output cannot contain the input database.")
    before = digest(repo.db_path)
    input_paths = [POSTS, SNAPSHOTS, RECORDINGS, RELEASES, "social/excluded_records.csv"]
    inputs = {path: hashlib.sha256(repo.original_bytes(path)).hexdigest() for path in input_paths}
    assets = {r["path"]: r["sha256"] for r in records_from_frame(repo.file_catalog())}
    posts, recordings, releases = (records(repo, p) for p in [POSTS, RECORDINGS, RELEASES])
    if len({(p["platform_selected"], p["selected_account_id"], p["post_id"]) for p in posts}) != len(posts):
        raise ValueError("Latest post identity grain is not unique.")
    post_rows, links, events, queue, evidence = [], [], [], [], []
    snapshots_by_key = defaultdict(list)
    for snap in records(repo, SNAPSHOTS):
        key = tuple(text(snap.get(k)) for k in ["platform_selected", "selected_account_id", "post_id"])
        snapshots_by_key[key].append({k: snap.get(k) for k in IDENTITY + ["description"] if k in snap})
    for post in posts:
        identity = {k: post.get(k) for k in IDENTITY}
        key = tuple(text(post.get(k)) for k in ["platform_selected", "selected_account_id", "post_id"])
        post_key = stable_id("post", *key)
        caption = text(post.get("description"))
        raw_path = "raw/meta/" + text(post.get("source_file"))
        source_hash = assets.get(raw_path, "")
        if not source_hash:
            raise ValueError("Missing retained native source asset: " + raw_path)
        # Force verification of each source's bytes before citing it.
        if hashlib.sha256(repo.original_bytes(raw_path)).hexdigest() != source_hash:
            raise ValueError("Source verification failed: " + raw_path)
        refs = song_references(caption, recordings)
        resolved = sorted({r["song_id"] for r in refs if r["status"] in RESOLVED})
        candidates = sorted({s for r in refs if r["status"] not in RESOLVED for s in r["candidate_song_ids"]})
        base = dict(post_key=post_key, **identity, retained_source_path=raw_path, retained_source_sha256=source_hash)
        evidence.append(dict(**base, description=caption, retained_snapshot_references=snapshots_by_key[key]))
        post_rows.append(dict(**base, assigned_song_ids=resolved, candidate_song_ids=candidates,
                              assigned_song_count=len(resolved), song_cardinality="multiple" if len(resolved) > 1 else "one" if resolved else "no_identified_song",
                              has_unresolved_reference=any(r["status"] not in RESOLVED for r in refs),
                              reference_statuses=sorted({r["status"] for r in refs}), caption_present=bool(caption.strip()),
                              audio_use_verified=False, stream_attribution_available=False))
        for ref in refs:
            row = dict(mapping_id=stable_id("mapping", post_key, ref), post_key=post_key, **identity, **ref,
                       retained_source_path=raw_path, retained_source_sha256=source_hash,
                       evidence_grain="retained_caption_or_link_reference", audio_use_verified=False, stream_attribution_available=False)
            links.append(row)
            if ref["status"] not in RESOLVED and ref["status"] != "explicit_no_song_claim":
                queue.append(dict(review_id=stable_id("review", row["mapping_id"]), record_type="song_mapping", record_id=row["mapping_id"],
                                  post_key=post_key, platform_selected=post.get("platform_selected"), post_id=post.get("post_id"),
                                  priority="identity_or_version" if ref["candidate_song_ids"] else "optional_content_inspection",
                                  reason=ref["reason"], candidate_song_ids=ref["candidate_song_ids"], evidence_excerpt=ref["evidence_excerpt"],
                                  required_evidence="Explicit recording/version or retained post audio/creative identification; do not infer from nearby posts."))
        for event in caption_events(caption, recordings):
            event_id = stable_id("event", post_key, event)
            row = dict(event_id=event_id, post_key=post_key, **identity,
                       promotion_date=post.get("publication_date"), song_ids=resolved, candidate_song_ids=candidates,
                       **event, retained_source_path=raw_path, retained_source_sha256=source_hash)
            events.append(row)
            if event["event_date_status"] != "explicit_caption_date":
                queue.append(dict(review_id=stable_id("review", event_id), record_type="event_date", record_id=event_id,
                                  post_key=post_key, platform_selected=post.get("platform_selected"), post_id=post.get("post_id"),
                                  priority="event_calendar", reason=event["event_date_status"], evidence_excerpt=event["evidence_excerpt"],
                                  required_evidence="Dated announcement/ticket/calendar or documented publication-relative resolution; distinguish planned from occurred."))
    for release in releases:
        released = text(release.get("release_date"))
        if date.fromisoformat(released).isoformat() != released:
            raise ValueError("Release metadata date must be an exact calendar date.")
        title = text(release["release_title"])
        ids = [r["song_id"] for r in recordings if title in text(r.get("release_memberships")).split(" | ")]
        events.append(dict(event_id=stable_id("release", release["release_id"]), event_kind="catalog_release", release_id=release["release_id"],
                           release_title=title, song_ids=sorted(ids), event_date=released, event_date_status="retained_release_metadata",
                           event_occurrence_status="source_reported_release_date", promotion_date="", reporting_timezone=release.get("reporting_timezone"),
                           snapshot_timestamp=release.get("retrieved_at"), snapshot_class=release.get("snapshot_class"),
                           retained_source_path=RELEASES, retained_source_sha256=inputs[RELEASES],
                           source_file=release.get("source_file"), source_record=release.get("source_row"),
                           evidence_excerpt=json.dumps({k: release.get(k) for k in ["release_id", "release_title", "release_type", "release_date", "source"]}, ensure_ascii=False),
                           reason="Retained release metadata; does not establish an original-baseline membership or marketing event."))
    excluded = records(repo, "social/excluded_records.csv")
    for source in excluded:
        queue.append(dict(review_id=stable_id("excluded", source.get("source_file"), source.get("source_record")),
                          record_type="quarantined_source", record_id=text(source.get("post_id")),
                          platform_selected=source.get("platform_selected"), post_id=source.get("post_id"), priority="source_recovery",
                          reason=source.get("reason"), source_file=source.get("source_file"), source_record=source.get("source_record"),
                          required_evidence="Valid native export or independently verified per-post evidence. Malformed field alignment is not guessed."))
    after = digest(repo.db_path)
    if after != before:
        raise ValueError("Input database changed during read; no output written.")
    coverage = dict(version=VERSION, script_sha256=digest(__file__), generated_at_utc=datetime.now(timezone.utc).isoformat(), source_database=str(repo.db_path),
                    source_database_sha256_before=before, source_database_sha256_after=after, input_assets_sha256=inputs,
                    canonical_posts=len(posts), retained_post_snapshots=sum(map(len, snapshots_by_key.values())),
                    quarantined_records_excluded=len(excluded), catalog_recordings=len(recordings),
                    posts_with_resolved_reference=sum(bool(p["assigned_song_ids"]) for p in post_rows),
                    posts_with_multiple_resolved_references=sum(p["assigned_song_count"] > 1 for p in post_rows),
                    posts_without_resolved_reference=sum(not p["assigned_song_ids"] for p in post_rows),
                    posts_with_unresolved_candidates=sum(bool(p["candidate_song_ids"]) for p in post_rows),
                    reference_status_counts=dict(Counter(r["status"] for r in links)),
                    event_kind_counts=dict(Counter(r["event_kind"] for r in events)),
                    event_date_status_counts=dict(Counter(r["event_date_status"] for r in events)), review_queue_rows=len(queue),
                    limitations=["No browser, network, audio/video, new analytics or live destination verification.",
                                 "Explicit caption/link references do not prove audio use, exposure, stream conversion or causal effects.",
                                 "No performance metrics joined; bridge rows must never multiply lifetime metrics or allocate aggregate streams.",
                                 "Unknown is not no song; malformed Story records remain excluded and separately queued.",
                                 "Event mentions are not verified occurrences. Publication/promotion date is separate from claimed event date.",
                                 "No year or ambiguous relative event date is filled in. Release membership does not establish baseline status.",
                                 "CSV formula-leading strings are apostrophe protected; JSON retains exact source text."])
    output.mkdir(parents=True)
    for name, rows in [("post_song_map", post_rows), ("post_song_references", links), ("post_evidence", evidence), ("event_map", events), ("review_queue", queue)]:
        write_rows(output, name, rows)
    (output / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text("# Post/song/event evidence bridge\n\nBuilt from the active immutable analysis package using `scripts/build_post_song_event_map.py`. "
        "The source DB and all source assets are read only. `coverage.json` records hashes and rules.\n\n"
        "- `post_song_map`: one row per platform/account/post, including unknown and multiple references.\n"
        "- `post_song_references`: evidence bridge; resolved IDs versus candidates/unknowns. Do not join metrics across these many-to-many rows.\n"
        "- `post_evidence`: exact retained captions, source identities and all snapshot references.\n"
        "- `event_map`: source release dates and caption event/promotion mentions. Publication is not the event date.\n"
        "- `review_queue`: candidate/version/context/date questions, unknown captions and excluded malformed Stories.\n\n"
        "`verified_spotify_link` means an explicit retained link matches a known stable ID; no live URL was opened. "
        "Caption-only assignments are `explicit_caption_reference`, never verified audio use. None of these mappings measures conversion. "
        "Relative dates and missing years remain unresolved. No date-derived year or proximity-derived song assignment is made. "
        "Repeated posts mentioning an event are evidence rows, not independent events to count. CSV text is formula protected; JSON is exact.\n", encoding="utf-8")
    files = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / "output_manifest.json").write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
    return coverage


def records_from_frame(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data-dir", type=Path, help="Application data directory containing the registry")
    source.add_argument("--database", type=Path, help="Explicit immutable analysis database")
    parser.add_argument("--output", required=True, type=Path, help="New output directory; existing directories are refused")
    args = parser.parse_args()
    repository = AnalysisRepository(args.database) if args.database else load_registered_analysis(args.data_dir)
    if repository is None:
        parser.error("No analysis package is registered in this data directory")
    print(json.dumps(build(repository, args.output), ensure_ascii=False, indent=2))
