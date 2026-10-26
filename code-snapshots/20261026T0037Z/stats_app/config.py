"""Portable, explicit configuration. No credentials or data bundled in code."""
from dataclasses import dataclass
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    mode: str
    data_dir: Path
    import_dir: Path | None
    approved_users_file: Path | None
    expected_issuer: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "stats.sqlite3"


def _path(value: str) -> Path:
    path = Path(value).expanduser()
    return (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def load_settings() -> Settings:
    mode = os.environ.get("STATS_MODE", "local").strip().lower()
    if mode not in {"local", "hosted"}:
        raise ValueError("STATS_MODE must be local or hosted.")
    if mode == "hosted" and not os.environ.get("STATS_DATA_DIR"):
        raise ValueError("Hosted mode requires STATS_DATA_DIR on durable storage.")
    if os.name == "nt":
        default = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "TheStats"
    else:
        default = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "the-stats"
    return Settings(
        mode, _path(os.environ.get("STATS_DATA_DIR", str(default))),
        _path(os.environ["STATS_IMPORT_DIR"]) if os.environ.get("STATS_IMPORT_DIR") else None,
        _path(os.environ["STATS_APPROVED_USERS_FILE"]) if os.environ.get("STATS_APPROVED_USERS_FILE") else None,
        os.environ.get("STATS_EXPECTED_ISSUER", ""),
    )
