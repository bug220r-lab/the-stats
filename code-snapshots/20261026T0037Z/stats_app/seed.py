"""Explicitly import the locally preserved original baseline package."""
from stats_app.access import Principal
from stats_app.config import load_settings
from stats_app.service import load_collected_baseline
from stats_app.storage import SQLiteRepository

if __name__ == "__main__":
    settings = load_settings()
    if settings.mode != "local":
        raise SystemExit("Use the authenticated admin interface for hosted imports.")
    repo = SQLiteRepository(settings.database_path)
    results = load_collected_baseline(repo, Principal("Local operator", "admin"))
    print(f"Archive protected; original baseline unverified. Added {sum(r.imported_rows for r in results):,} observations; {sum(r.duplicate_import for r in results)} duplicate files.")
    print(f"Database: {settings.database_path}")
