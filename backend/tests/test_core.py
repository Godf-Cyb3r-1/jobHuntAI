from datetime import timedelta
from app.core import job_id, normalize_url, role_matches, posted_recent, now, DEFAULT_PROFILE

def test_role_strict():
    assert role_matches({"title":"Senior Penetration Tester"},DEFAULT_PROFILE)
    assert not role_matches({"title":"SOC Analyst - penetration testing experience"},DEFAULT_PROFILE)
    assert not role_matches({"title":"IAM Analyst"},DEFAULT_PROFILE)
def test_url_dedup():
    assert job_id("https://example.com/jobs/1?utm_source=xx")==job_id("https://example.com/jobs/1")
def test_freshness():
    assert posted_recent(now().isoformat(),30)
    assert not posted_recent((now()-timedelta(days=31)).isoformat(),30)
    assert not posted_recent(None,30)
