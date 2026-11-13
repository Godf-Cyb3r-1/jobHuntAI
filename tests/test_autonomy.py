"""Autonomous OpenCode integration tests: no external AI key/network required."""
import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
import httpx
import pytest

os.environ["JOBHUNTAI_HOME"] = tempfile.mkdtemp(prefix="jobhuntai-auto-tests-")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("jobhuntai_autonomy_test", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)

import opencode_engine as agent
import autonomous_worker as worker

def seed(title="Application Security Engineer", role="appsec,pentest", name="appsec"):
    with app.database() as db:
        uid = db.execute("INSERT INTO users(email,pwd,name,role,skills,freshness,locations,ai_consent) VALUES(?,?,?,?,?,?,?,1)",
                         (name + "@test.example", "hash", "Test User", role, "Burp Suite", 3, "Chennai")).lastrowid
        sid = db.execute("SELECT id FROM sources LIMIT 1").fetchone()[0]
        jid = "test:" + name
        db.execute("""INSERT INTO jobs(id,company,title,location,description,url,published,date_evidence,
           first_seen,last_seen,source_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
           (jid, "Verified Employer", title, "Chennai", "Burp Suite experience in application security assessments",
            "https://example.com/jobs/1", app.iso(), "test.published_at", app.iso(), app.iso(), sid))
        return uid, jid

class FakeGateway:
    def __init__(self, eligible=True):
        self.eligible = eligible
        self.calls = 0
    def ask(self, agent_name, data):
        assert agent_name == "job-matcher"
        assert "job" in data and "user_profile" in data
        self.calls += 1
        return {"eligible": self.eligible, "score": 88 if self.eligible else 12,
                "reason": "Experience directly fits the application security responsibilities.",
                "highlights": ["Burp Suite", "Fictional Cloud Wizardry"],
                "outreach": "Hi, I noticed the application security role and would like to apply."}

def test_json_response_and_fact_verification():
    parsed = agent.json_reply('some text {"eligible":true,"score":95,"reason":"Strong technical overlap"}')
    checked = agent.verify(dict(parsed, highlights=["Burp Suite", "Made Up Skill"]),
                           "Burp Suite", "Proven Burp Suite work")
    assert checked["highlights"] == ["Burp Suite"]
    with pytest.raises(ValueError):
        agent.verify({"eligible": True, "score": 100}, "", "")

def test_separate_opencode_session_protocol():
    root = Path(tempfile.mkdtemp())
    def fake(request):
        if request.url.path == "/session":
            return httpx.Response(200, json={"id": "abc123"})
        if request.url.path == "/session/abc123/message":
            body = __import__("json").loads(request.content)
            assert body["model"]["providerID"] == "openrouter"
            assert body["agent"] == "job-matcher"
            return httpx.Response(200, json={"parts": [{"type": "text", "text": '{"eligible":true,"score":89,"reason":"Matching application security professional responsibilities"}'}]})
        if request.method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(404)
    output = agent.Gateway(root, transport=httpx.MockTransport(fake)).ask("job-matcher", {"test": 1})
    assert output["eligible"] is True

def test_ai_mandatory_for_job_match():
    uid, jid = seed(name="eligible")
    mock = FakeGateway()
    state = worker.evaluate(app, gateway=mock, limit=5)
    assert state["approved"] >= 1
    with app.database() as db:
        row = db.execute("SELECT score,reason FROM matches WHERE user_id=? AND job_id=?", (uid, jid)).fetchone()
        assert row and row["score"] == 88
        review = db.execute("SELECT state,highlights FROM ai_reviews WHERE user_id=? AND job_id=?", (uid, jid)).fetchone()
        assert review["state"] == "approved"
        assert "Fictional Cloud" not in review["highlights"]
    again = worker.evaluate(app, gateway=mock, limit=5)
    assert mock.calls == 1

def test_rejection_removes_match_and_never_recommends_soc():
    uid, jid = seed(title="SOC Analyst", role="pentest", name="soccheck")
    worker.evaluate(app, gateway=FakeGateway(), limit=5)
    with app.database() as db:
        assert db.execute("SELECT 1 FROM matches WHERE user_id=? AND job_id=?", (uid, jid)).fetchone() is None

def test_unavailable_opencode_does_not_claim_match():
    uid, jid = seed(name="no-model")
    # There is no OpenRouter key in the test HOME.
    result = worker.evaluate(app)
    assert result["state"] == "waiting_for_opencode"
    with app.database() as db:
        assert db.execute("SELECT 1 FROM matches WHERE user_id=? AND job_id=?", (uid, jid)).fetchone() is None

def test_free_source_discovery_protection():
    assert worker.ATS_HOSTS.get("metadata.google.internal") is None
    assert worker.ATS_HOSTS.get("jobs.ashbyhq.com") == "ashby"
