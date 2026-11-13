"""Autonomous discovery, OpenCode evaluation, resume assets and alert orchestration."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET
import httpx
from docx import Document
import opencode_engine as ai

LOG = logging.getLogger("jobhuntai.autonomous")
ATS_HOSTS = {
    "jobs.ashbyhq.com": "ashby",
    "jobs.lever.co": "lever",
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse"
}

def setup(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ai_reviews (
      user_id INTEGER NOT NULL, job_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
      state TEXT NOT NULL, score INTEGER, reason TEXT, highlights TEXT, outreach TEXT,
      error TEXT, attempts INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL,
      PRIMARY KEY(user_id,job_id));
    CREATE TABLE IF NOT EXISTS ai_usage (
      day TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS ai_assets (
      user_id INTEGER NOT NULL, job_id TEXT NOT NULL, path TEXT NOT NULL,
      created TEXT NOT NULL, PRIMARY KEY(user_id,job_id));
    CREATE TABLE IF NOT EXISTS worker_events (
      id INTEGER PRIMARY KEY, event_time TEXT NOT NULL, worker TEXT NOT NULL,
      state TEXT NOT NULL, detail TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS discovery_state (
      name TEXT PRIMARY KEY, last_run TEXT NOT NULL);
    """)

def event(db, ctx, worker, state, detail):
    db.execute("INSERT INTO worker_events(event_time,worker,state,detail) VALUES(?,?,?,?)",
               (ctx.iso(), worker, state, str(detail)[:300]))
    db.execute("DELETE FROM worker_events WHERE id NOT IN (SELECT id FROM worker_events ORDER BY id DESC LIMIT 400)")

def call_budget(db, limit):
    day = datetime.now(timezone.utc).date().isoformat()
    db.execute("INSERT OR IGNORE INTO ai_usage(day,calls) VALUES(?,0)", (day,))
    current = db.execute("SELECT calls FROM ai_usage WHERE day=?", (day,)).fetchone()[0]
    if current >= limit:
        return False
    db.execute("UPDATE ai_usage SET calls=calls+1 WHERE day=?", (day,))
    return True

def build_resume(root, user, job, resume, reviewed):
    if not resume:
        return None
    folder = Path(root) / "auto_resumes" / str(user["id"])
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / (hashlib.sha256(job["id"].encode()).hexdigest()[:24] + ".docx")
    doc = Document()
    doc.add_heading(str(user["name"])[:100], 0)
    doc.add_paragraph("Resume for " + str(job["title"])[:100] + " — " + str(job["company"])[:100])
    doc.add_heading("Relevant verified skills", level=1)
    doc.add_paragraph(", ".join(reviewed["highlights"]) if reviewed["highlights"] else str(user["skills"]))
    doc.add_heading("Original resume experience (preserved)", level=1)
    for line in str(resume["extracted"]).splitlines()[:300]:
        if line.strip():
            doc.add_paragraph(line[:450])
    doc.save(out)
    return str(out)

def candidates(ctx):
    ctx.initialize()
    result = []
    with ctx.database() as db:
        setup(db)
        users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
        jobs = db.execute("SELECT * FROM jobs WHERE active=1 AND published IS NOT NULL ORDER BY published DESC LIMIT 500").fetchall()
        for u in users:
            if not u["ai_consent"]:
                # No profile data leaves the server without explicit consent.
                db.execute("DELETE FROM matches WHERE user_id=?", (u["id"],))
                continue
            resume = db.execute("SELECT * FROM resumes WHERE user_id=? ORDER BY id DESC LIMIT 1", (u["id"],)).fetchone()
            # Registration alone is not enough evidence for professional suitability.
            if not resume and not str(u["skills"] or "").strip():
                continue
            for j in jobs:
                hard = ctx.match_job(u, j)
                if hard is None:
                    db.execute("DELETE FROM matches WHERE user_id=? AND job_id=?", (u["id"], j["id"]))
                    continue
                fp = ai.digest(u, j, resume["id"] if resume else None)
                row = db.execute("SELECT * FROM ai_reviews WHERE user_id=? AND job_id=?", (u["id"], j["id"])).fetchone()
                if row and row["fingerprint"] == fp and row["state"] in ("approved", "rejected"):
                    continue
                if row and row["fingerprint"] == fp and row["state"] == "error":
                    try:
                        since = (ctx.utcnow() - datetime.fromisoformat(row["updated"])).total_seconds()
                    except (ValueError, TypeError):
                        since = 999999
                    # Retry transient provider errors with backoff; never permanently abandon a job.
                    delay = 600 if row["attempts"] <= 1 else 1800 if row["attempts"] == 2 else 43200
                    if since < delay:
                        continue
                # Never allow a previous rule-only match to be presented as AI reviewed.
                db.execute("DELETE FROM matches WHERE user_id=? AND job_id=?", (u["id"], j["id"]))
                result.append((u, j, resume, hard, fp))
        db.execute("""DELETE FROM matches WHERE NOT EXISTS
            (SELECT 1 FROM ai_reviews ar WHERE ar.user_id=matches.user_id
              AND ar.job_id=matches.job_id AND ar.state='approved')""")
    return result

def evaluate(ctx, gateway=None, limit=5):
    """Model is required to approve a match. Offline state is visible in dashboard."""
    all_candidates = candidates(ctx)
    mocked = gateway is not None
    if not mocked and not ai.ready(ctx.ROOT):
        return {"state": "waiting_for_opencode", "pending": len(all_candidates), "processed": 0, "approved": 0}
    gateway = gateway or ai.Gateway(ctx.ROOT)
    max_per_cycle = max(1, min(10, int(limit)))
    day_limit = max(1, min(50, int(os.getenv("JOBHUNTAI_AI_DAILY_LIMIT", "30"))))
    approved = rejected = processed = 0
    for u, j, resume, hard, fp in all_candidates:
        if processed >= max_per_cycle:
            break
        with ctx.database() as db:
            setup(db)
            if not mocked and not call_budget(db, day_limit):
                event(db, ctx, "matching", "quota", "Free OpenCode provider budget reached")
                break
            previous = db.execute("SELECT attempts FROM ai_reviews WHERE user_id=? AND job_id=?", (u["id"], j["id"])).fetchone()
            attempts = 1 + (previous["attempts"] if previous and previous["fingerprint"] == fp else 0) if previous else 1
            db.execute("""INSERT INTO ai_reviews(user_id,job_id,fingerprint,state,attempts,updated)
                VALUES(?,?,?,'processing',?,?)
                ON CONFLICT(user_id,job_id) DO UPDATE SET fingerprint=excluded.fingerprint,
                attempts=excluded.attempts,state='processing',error=NULL,updated=excluded.updated""",
                (u["id"], j["id"], fp, attempts, ctx.iso()))
        processed += 1
        resume_text = str(resume["extracted"]) if resume else ""
        payload = {
            "decision": "Decide if responsibilities are a genuine professional match. Strict family filtering already passed. Reply JSON: eligible, score, reason, highlights, outreach. If unsure, reject.",
            "user_profile": {"role": u["role"], "skills": u["skills"],
                             "preferences": ai.scrub(u["notes"]), "resume_evidence": ai.scrub(resume_text)},
            "job": {"title": j["title"], "company": j["company"],
                    "description": str(j["description"] or "")[:5000], "location": j["location"]},
            "deterministic": {"eligibility_passed": True, "rules_score": hard[0]}
        }
        try:
            review = ai.verify(gateway.ask("job-matcher", payload), u["skills"], resume_text)
            min_score = max(65, min(95, int(os.getenv("JOBHUNTAI_MIN_AI_SCORE", "78"))))
            if review["eligible"] and review["score"] < min_score:
                review["eligible"] = False
                review["reason"] = "Below strict match threshold. " + review["reason"]
            with ctx.database() as db:
                if review["eligible"]:
                    approved += 1
                    db.execute("""INSERT INTO matches(user_id,job_id,score,reason,created)
                        VALUES(?,?,?,?,?) ON CONFLICT(user_id,job_id) DO UPDATE SET
                        score=excluded.score,reason=excluded.reason,created=excluded.created""",
                        (u["id"], j["id"], review["score"], review["reason"], ctx.iso()))
                    path = build_resume(ctx.ROOT, u, j, resume, review)
                    if path:
                        db.execute("""INSERT INTO ai_assets(user_id,job_id,path,created)
                            VALUES(?,?,?,?) ON CONFLICT(user_id,job_id)
                            DO UPDATE SET path=excluded.path,created=excluded.created""",
                            (u["id"], j["id"], path, ctx.iso()))
                    event(db, ctx, "matching", "approved", j["title"])
                else:
                    rejected += 1
                    event(db, ctx, "matching", "rejected", j["title"])
                db.execute("""UPDATE ai_reviews SET state=?,score=?,reason=?,highlights=?,
                    outreach=?,error=NULL,updated=? WHERE user_id=? AND job_id=?""",
                    ("approved" if review["eligible"] else "rejected", review["score"],
                     review["reason"], json.dumps(review["highlights"]), review["outreach"],
                     ctx.iso(), u["id"], j["id"]))
        except Exception as exc:
            LOG.warning("OpenCode evaluation error: %s", str(exc)[:240])
            with ctx.database() as db:
                db.execute("""UPDATE ai_reviews SET state='error',error=?,updated=?
                     WHERE user_id=? AND job_id=?""",
                    (str(exc)[:240], ctx.iso(), u["id"], j["id"]))
                event(db, ctx, "matching", "error", str(exc)[:240])
    return {"state": "running" if processed else "idle", "pending": len(all_candidates),
            "processed": processed, "approved": approved, "rejected": rejected}

def discover(ctx, gateway=None, force=False):
    """Optional zero-cost ATS index discovery using public search RSS. Avoid paywalls/logins."""
    ctx.initialize()
    with ctx.database() as db:
        setup(db)
        last = db.execute("SELECT last_run FROM discovery_state WHERE name='ats'").fetchone()
        if last and not force:
            try:
                if (ctx.utcnow() - datetime.fromisoformat(last["last_run"])).total_seconds() < 12 * 3600:
                    return {"state": "not_due", "added": 0}
            except (ValueError, TypeError):
                pass
        db.execute("""INSERT INTO discovery_state(name,last_run) VALUES('ats',?)
            ON CONFLICT(name) DO UPDATE SET last_run=excluded.last_run""", (ctx.iso(),))
    queries = [
        "site:jobs.ashbyhq.com penetration tester India",
        "site:jobs.lever.co application security India",
        "site:job-boards.greenhouse.io api security India",
        "site:boards.greenhouse.io offensive security India",
    ]
    # Discovery worker may propose additional searches, but cannot approve feeds itself.
    if gateway is not None and ai.ready(ctx.ROOT):
        try:
            response = gateway.ask("job-discovery", {"task": "Suggest up to three ATS site queries for new India appsec/pentest jobs"})
            queries.extend(q for q in response.get("queries", [])[:3]
                           if isinstance(q, str) and q.startswith("site:") and len(q) < 150)
        except Exception:
            pass
    found = set()
    with httpx.Client(timeout=12, follow_redirects=False,
                      headers={"User-Agent": "JobHuntAI/0.2 public ATS discovery"}) as client:
        for query in queries[:6]:
            try:
                response = client.get("https://www.bing.com/search", params={"q": query, "format": "rss"})
                response.raise_for_status()
                xml = ET.fromstring(response.text)
                for item in xml.iter("item"):
                    link = item.findtext("link") or ""
                    parsed = urlparse(link)
                    kind = ATS_HOSTS.get((parsed.hostname or "").lower())
                    paths = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
                    if kind and parsed.scheme == "https" and paths and re.fullmatch(r"[A-Za-z0-9_-]{2,80}", paths[0]):
                        found.add((kind, paths[0]))
            except (httpx.HTTPError, ET.ParseError):
                continue
        added = 0
        for kind, slug in sorted(found)[:20]:
            with ctx.database() as db:
                if db.execute("SELECT 1 FROM sources WHERE kind=? AND slug=?", (kind, slug)).fetchone():
                    continue
            try:
                ctx.fetch_source(client, {"kind": kind, "slug": slug})
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                continue
            with ctx.database() as db:
                db.execute("INSERT OR IGNORE INTO sources(kind,slug,company) VALUES(?,?,?)",
                           (kind, slug, slug.replace("-", " ").title()))
            added += 1
            if added >= 8:
                break
    with ctx.database() as db:
        event(db, ctx, "discovery", "completed", "New validated public ATS boards: %d" % added)
    return {"state": "completed", "added": added}

def status(ctx):
    ctx.initialize()
    with ctx.database() as db:
        setup(db)
        statuses = {r["state"]: r["c"] for r in db.execute("SELECT state, COUNT(*) AS c FROM ai_reviews GROUP BY state")}
        today = datetime.now(timezone.utc).date().isoformat()
        usage = db.execute("SELECT calls FROM ai_usage WHERE day=?", (today,)).fetchone()
        events = [dict(row) for row in db.execute("SELECT * FROM worker_events ORDER BY id DESC LIMIT 12")]
    return {"model": ai.model(ctx.ROOT), "key_set": bool(ai.key(ctx.ROOT)),
            "running": ai.ready(ctx.ROOT), "calls_today": usage["calls"] if usage else 0,
            "reviews": statuses, "events": events}
