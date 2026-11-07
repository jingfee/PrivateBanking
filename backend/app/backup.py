"""Copies of the SQLite database, taken before schema migrations."""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def backup_database(db_path: Path, reason: str, keep: int = 10) -> Path:
    """Consistent online copy (SQLite backup API) to <db dir>/backups/, keeping the newest `keep`."""
    backups = db_path.parent / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backups / f"{db_path.stem}-{stamp}-{reason}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(backups.glob(f"{db_path.stem}-*.db"))[:-keep]:
        old.unlink()
    log.info("database backed up to %s", target)
    return target
