"""Build and stage the reviewed October 23 Meta collection without activation."""
from __future__ import annotations

import json
from pathlib import Path

from stats_app.analysis_repository import load_registered_analysis, stage_analysis_package
from stats_app.config import load_settings
from stats_app.meta_content import build_meta_content


def main():
    root = Path(__file__).resolve().parents[1]
    collection = root / "data/collection/meta-content-20261023"
    destination = root / "data/reconciliation/meta_content_20261023"
    settings = load_settings()
    parent = load_registered_analysis(settings.data_dir, "instagram-story-owner-20261023")
    result = build_meta_content(parent, collection, destination / "package",
                                destination / "meta-content-20261023.zip")
    (destination / "build_receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    staged = stage_analysis_package(destination / "package", destination / "meta-content-20261023.zip",
                                    destination / "staged", label=result["label"],
                                    metadata=result["staging_metadata"])
    (destination / "stage_receipt.json").write_text(json.dumps(staged, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"database": staged["database"], "files": staged["files"],
                      "parsed_tables": staged["parsed_tables"], "parsed_records": staged["parsed_records"]}))


if __name__ == "__main__":
    main()
