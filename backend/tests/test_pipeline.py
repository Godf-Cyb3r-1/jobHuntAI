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

from app.pipeline import location_allowed,experience_eligible
def test_preferences():
    assert location_allowed("Chennai, India",{"locations":["Tamil Nadu"]})
    assert not location_allowed("Bengaluru, India",{"locations":["Tamil Nadu"]})
    assert location_allowed("Remote - India",{"locations":["Remote"]})
    assert not location_allowed("Remote - USA only",{"locations":["Remote"]})
def test_experience():
    job={"description":"Minimum 6 years of experience in penetration testing."}
    assert not experience_eligible(job,{"years_experience":2})
    assert experience_eligible(job,{"years_experience":5})
