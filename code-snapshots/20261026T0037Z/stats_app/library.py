"""Namespaced dashboard reads over local imports and explicit read-only archives.

No preserved database is migrated. Registry paths move with the data directory
between Windows and Linux; writes remain in the existing local repository.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

import pandas as pd

from stats_app.archive_repository import ImportedArchiveRepository
from stats_app.storage import StorageError


class LibraryRepository:
    def __init__(self, local_repo, registry_path: str | Path | None = None):
        self.local_repo = local_repo
        self.db_path = local_repo.db_path
        self.registry_path = Path(registry_path).resolve() if registry_path else self.db_path.parent / "archive_registry.json"
        self.archives = {}
        self.archive_labels = {}
        if self.registry_path.exists():
            try:
                registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise StorageError("Cannot read the archive registry; preserve it and correct its configuration.") from exc
            if not isinstance(registry, dict) or not isinstance(registry.get("archives"), list):
                raise StorageError("The archive registry must contain an archives list.")
            for item in registry["archives"]:
                if not isinstance(item, dict):
                    raise StorageError("Every archive registry entry must be an object.")
                key = item.get("key", "")
                if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", key) or key == "local" or key in self.archives:
                    raise StorageError("Archive keys must be unique names, excluding the reserved local key.")
                root = self.registry_path.parent

                def resolved(field):
                    raw = item.get(field)
                    if not isinstance(raw, str) or not raw:
                        raise StorageError(f"The archive registry requires {field}.")
                    relative = Path(raw)
                    path = (root / relative).resolve()
                    if relative.is_absolute() or not path.is_relative_to(root):
                        raise StorageError("Archive registry paths must stay relative to the registry data directory.")
                    return path

                database, source_dir = resolved("database"), resolved("source_dir")
                evidence_root = resolved("evidence_root") if item.get("evidence_root") else database.parent
                self.archives[key] = ImportedArchiveRepository(database, source_dir, evidence_root)
                self.archive_labels[key] = str(item.get("label") or key)

    def _route(self, identifier):
        key, delimiter, value = str(identifier).partition("::")
        if not delimiter or not value:
            raise StorageError("Select an identified library snapshot or observation.")
        repo = self.local_repo if key == "local" else self.archives.get(key)
        if repo is None:
            raise StorageError("The selected archive backend is not registered.")
        return key, repo, value

    @staticmethod
    def _catalog_frame(frame, key, backend_label):
        frame = frame.copy()
        frame["stored_label"] = frame["label"]
        frame["stored_is_baseline"] = frame["is_baseline"]
        frame["backend"] = key
        frame["backend_label"] = backend_label
        frame["label"] = key + "::" + frame["stored_label"].astype(str)
        frame["display_label"] = frame["stored_label"]
        if "status" not in frame:
            frame["status"] = "reporting_snapshot"
        if "evidence" not in frame:
            frame["evidence"] = ""
        frame["baseline_status"] = frame["is_baseline"].map({0: "not_verified", 1: "verified"})
        frame.loc[frame["status"].eq("unverified"), "baseline_status"] = "unverified"
        if key == "local":
            legacy = frame["stored_is_baseline"].astype(bool)
            frame.loc[legacy, "display_label"] = "Legacy Windows native archive · baseline unverified"
            frame.loc[legacy, "status"] = "baseline_unverified"
            frame.loc[legacy, "baseline_status"] = "unverified"
            frame.loc[legacy, "evidence"] = (
                "The saved Windows baseline designation is historical metadata. The later handoff establishes "
                "an October 20 reporting endpoint and October 22 collection, but original baseline membership "
                "remains unverified. Original rows and database labels are unchanged."
            )
            frame.loc[legacy, "is_baseline"] = 0
        return frame

    def list_snapshots(self):
        frames = [self._catalog_frame(repo.list_snapshots(), key, self.archive_labels[key])
                  for key, repo in self.archives.items()]
        frames.append(self._catalog_frame(self.local_repo.list_snapshots(), "local", "Windows local imports"))
        return pd.concat(frames, ignore_index=True)

    def observations(self, snapshot_label):
        key, repo, original_label = self._route(snapshot_label)
        data = repo.observations(original_label).copy()
        data["source_observation_id"] = data["observation_id"]
        data["observation_id"] = key + "::" + data["observation_id"].astype(str)
        data["snapshot_label"] = str(snapshot_label)
        data["backend"] = key
        return data

    def observation_provenance(self, observation_id):
        key, repo, original_id = self._route(observation_id)
        try:
            numeric_id = int(original_id)
        except ValueError as exc:
            raise StorageError("The selected observation identifier is invalid.") from exc
        frame = repo.observation_provenance(numeric_id).copy()
        frame["backend"] = key
        return frame

    def import_history(self):
        frames = []
        for key, repo in [*self.archives.items(), ("local", self.local_repo)]:
            frame = repo.import_history().copy()
            if frame.empty:
                continue
            frame["source_import_id"] = frame["import_id"]
            frame["import_id"] = key + "::" + frame["import_id"].astype(str)
            frame["stored_snapshot_label"] = frame["snapshot_label"]
            frame["snapshot_label"] = key + "::" + frame["snapshot_label"].astype(str)
            frame["backend"] = key
            frame["source_label"] = self.archive_labels.get(key, "Windows local imports")
            frame["stored_is_baseline"] = frame["is_baseline"]
            if key == "local":
                frame["is_baseline"] = 0
            frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else self.local_repo.import_history()

    def original_source(self, source_hash):
        # A hash identifies equal bytes across backends. IDs remain namespaced.
        errors = []
        for repo in [self.local_repo, *self.archives.values()]:
            try:
                return repo.original_source(source_hash)
            except StorageError as exc:
                errors.append(exc)
        raise StorageError("The original source is missing or failed verification: " + "; ".join(str(error) for error in errors))

    def coverage_issues(self, snapshot_label):
        key, repo, original_label = self._route(snapshot_label)
        if key == "local":
            return pd.DataFrame()
        frame = repo.coverage_issues(original_label).copy()
        frame["backend"] = key
        return frame

    def collection_queue(self, snapshot_label=None):
        if snapshot_label is not None:
            key, repo, _ = self._route(snapshot_label)
            selected = [] if key == "local" else [(key, repo)]
        else:
            selected = list(self.archives.items())
        frames = []
        for key, repo in selected:
            frame = repo.collection_queue().copy()
            if not frame.empty:
                frame["backend"] = key
                frame["source_queue_id"] = frame["id"]
                frame["id"] = key + "::" + frame["id"].astype(str)
                frame["queue_scope"] = "Historical archive-wide queue; not specific to one snapshot"
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def evidence_reports(self):
        """Return only explicitly supported reports, with qualified source names.

        Values are the original parsed JSON, without rewriting report fields.
        Missing files remain missing; no synthesized coverage is substituted.
        """
        reports = {}
        names = ("spotify_coverage.json", "spotify_import_report.json", "reconciliation/cross_reference.json")
        for key, repo in self.archives.items():
            for name in names:
                path = (repo.evidence_root / name).resolve()
                if not path.is_relative_to(repo.evidence_root):
                    raise StorageError("An evidence report resolves outside the registered archive.")
                if path.is_file():
                    try:
                        reports[f"{key}::{name}"] = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, ValueError) as exc:
                        raise StorageError(f"The archived evidence report {name} could not be read.") from exc
        return reports

    def import_dataset(self, *args, **kwargs):
        args = list(args)
        label = kwargs.get("snapshot_label", args[3] if len(args) > 3 else None)
        if label is not None and "::" in str(label):
            key, _, original_label = self._route(label)
            if key != "local":
                raise StorageError("Recovered archives are read-only. Save new data to a new local snapshot.")
            if "snapshot_label" in kwargs:
                kwargs["snapshot_label"] = original_label
            else:
                args[3] = original_label
        return self.local_repo.import_dataset(*args, **kwargs)

    def seal_snapshot(self, label):
        if "::" in str(label):
            key, repo, original_label = self._route(label)
            if key != "local":
                raise StorageError("Recovered archives are read-only. Save new data to a new local snapshot.")
            return repo.seal_snapshot(original_label)
        return self.local_repo.seal_snapshot(label)

    def backup(self, path):
        """Back up the writable database; archives remain separate fixed files."""
        return self.local_repo.backup(path)
