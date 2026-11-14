import os
from app.core import connect,init_db
from app.pipeline import migrate,in_region,valid_until,source_report
def test_regions():
    assert in_region("Bengaluru, Karnataka")
    assert in_region("Remote - India")
    assert not in_region("Remote - USA only")
    assert not in_region("San Francisco")
def test_expired():
    assert not valid_until("2022-01-01T00:00:00Z")
def test_migrations(tmp_path,monkeypatch):
    import app.core as core
    monkeypatch.setattr(core,"DB",str(tmp_path/"t.db"))
    init_db();migrate();migrate()
    with connect() as db:
        names={r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
        assert {"last_seen","model_verified","dismissed"}.issubset(names)
        assert db.execute("SELECT name FROM sqlite_master WHERE name='source_health'").fetchone()
