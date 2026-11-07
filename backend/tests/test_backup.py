import sqlite3

from app.backup import backup_database
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_backup_copies_and_prunes(tmp_path):
    db = tmp_path / "pb.db"
    con = sqlite3.connect(db)
    con.execute("create table t (x)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()
    paths = [backup_database(db, reason=f"r{i}", keep=3) for i in range(5)]
    left = sorted((tmp_path / "backups").iterdir())
    assert len(left) == 3
    assert sqlite3.connect(paths[-1]).execute("select x from t").fetchone() == (42,)


def _start(path):
    s = Settings(database_path=path, scheduler_enabled=False, frontend_dir=path.parent / "x")
    with TestClient(create_app(s)):
        pass


def test_backup_only_when_migration_pending(tmp_path):
    db = tmp_path / "pb.db"
    _start(db)  # fresh database: nothing to back up
    assert not (tmp_path / "backups").exists()
    _start(db)  # already at head: no backup
    assert not (tmp_path / "backups").exists()

    con = sqlite3.connect(db)  # pretend the database is on an older schema version
    con.execute("update alembic_version set version_num = 'older'")
    con.commit()
    con.close()
    try:
        _start(db)
    except Exception:
        pass  # alembic can't upgrade from an unknown revision; the backup must exist anyway
    assert len(list((tmp_path / "backups").iterdir())) == 1
