"""JobHuntAI Windows-first self-hosted web server (bootstrap edition)."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
import uvicorn
from docx import Document
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from pypdf import PdfReader
from starlette.middleware.sessions import SessionMiddleware

import opencode_engine as ai_engine
import autonomous_worker as autonomy

VERSION = "0.2.0"
ROOT = Path(os.getenv("JOBHUNTAI_HOME") or Path(os.getenv("LOCALAPPDATA") or Path.home()) / "JobHuntAI")
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / "resumes").mkdir(exist_ok=True)
DB = ROOT / "jobhunt.db"
KEYFILE = ROOT / "cookie-key"
if not KEYFILE.exists():
    KEYFILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
SECRET = KEYFILE.read_text(encoding="utf-8").strip()
LOG = ROOT / "jobhunt.log"
logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jobhuntai")
app = FastAPI(title="JobHuntAI", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site="lax", https_only=os.getenv("JOBHUNTAI_SECURE_COOKIES") == "1", max_age=86400 * 7)
SCAN_INTERVAL = max(300, int(os.getenv("JOBHUNTAI_SCAN_SECONDS", "1800")))
STOP = threading.Event()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
 pwd TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'Application Security',
 skills TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', linkedin TEXT NOT NULL DEFAULT '',
 freshness INTEGER NOT NULL DEFAULT 7, locations TEXT NOT NULL DEFAULT '',
 telegram_chat TEXT NOT NULL DEFAULT '', link_code TEXT UNIQUE, admin INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, slug TEXT NOT NULL,
 company TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, success INTEGER NOT NULL DEFAULT 0,
 last_attempt TEXT, last_success TEXT, last_error TEXT, UNIQUE(kind,slug));
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, company TEXT NOT NULL, title TEXT NOT NULL,
 location TEXT, description TEXT, url TEXT, published TEXT, date_evidence TEXT,
 first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 source_id INTEGER NOT NULL, missing_scans INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS matches (user_id INTEGER NOT NULL, job_id TEXT NOT NULL, score INTEGER,
 reason TEXT, created TEXT NOT NULL, PRIMARY KEY(user_id,job_id));
CREATE TABLE IF NOT EXISTS resumes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
 filename TEXT NOT NULL, filepath TEXT NOT NULL, extracted TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
 job_id TEXT NOT NULL, status TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
 created TEXT NOT NULL, updated TEXT NOT NULL, UNIQUE(user_id,job_id));
CREATE TABLE IF NOT EXISTS alerts (user_id INTEGER NOT NULL, job_id TEXT NOT NULL,
 channel TEXT NOT NULL, delivered TEXT NOT NULL, PRIMARY KEY(user_id,job_id,channel));
"""

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def database():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def initialize():
    with database() as db:
        db.executescript(SCHEMA)
        autonomy.setup(db)
        if not db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]:
            # Only examples. Every source's health is confirmed by the first scan.
            db.executemany("INSERT INTO sources(kind,slug,company) VALUES(?,?,?)", [
                ("ashby", "atlan", "Atlan"), ("greenhouse", "gitlab", "GitLab"),
                ("lever", "netlify", "Netlify")])


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ":" + derived.hex()


def password_valid(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split(":")
        derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(derived, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def escape(value) -> str:
    return html.escape(str(value or ""), quote=True)


def csrf(request: Request) -> str:
    if not request.session.get("csrf"):
        request.session["csrf"] = secrets.token_urlsafe(24)
    return f'<input type="hidden" name="csrf" value="{escape(request.session["csrf"])}">'


def check_csrf(request: Request, supplied: str):
    if not supplied or not hmac.compare_digest(supplied, request.session.get("csrf", "")):
        raise HTTPException(403, "Invalid form token. Reload and retry.")


def current_user(request: Request):
    user_id = request.session.get("uid")
    if not user_id:
        return None
    with database() as db:
        return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def require_user(request: Request):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Please log in")
    return user


def frame(request: Request, title: str, body: str) -> HTMLResponse:
    user = current_user(request)
    links = ('<a href="/">Dashboard</a><a href="/jobs">Matching jobs</a><a href="/applications">Applications</a>'
             '<a href="/profile">My profile</a><a href="/resumes">Resumes</a><a href="/ai-status">AI Workers</a><a href="/settings">Settings</a>'
             '<a href="/logout">Sign out</a>') if user else '<a href="/login">Log in</a><a href="/register">Create account</a>'
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · JobHuntAI</title><style>
:root{{--bg:#0a101b;--panel:#131e30;--edge:#2a394b;--text:#e9f0fa;--muted:#9fb0c2;--brand:#57c9b1}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.55 system-ui,Segoe UI,Arial;background:var(--bg);color:var(--text)}}
a{{color:#8ad8cf;text-decoration:none}}a:hover{{text-decoration:underline}}.top{{display:flex;align-items:center;gap:22px;justify-content:space-between;padding:18px max(22px,calc((100vw - 1150px)/2));border-bottom:1px solid var(--edge)}}
.logo{{font-size:20px;font-weight:800;color:var(--text)}}nav{{display:flex;flex-wrap:wrap;gap:14px}}main{{max-width:1150px;margin:30px auto;padding:0 20px}}h1{{font-size:26px;margin:0 0 10px}}h2{{font-size:18px}}p,.muted{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}}.card{{background:var(--panel);border:1px solid var(--edge);border-radius:13px;padding:20px;margin:12px 0}}.metric{{font-size:30px;font-weight:700;color:var(--brand)}}
label{{display:block;margin:14px 0 5px;color:#d4e1ee;font-weight:600}}input,textarea,select{{width:100%;background:#0b1424;color:var(--text);border:1px solid #41536a;border-radius:8px;padding:10px;font:inherit}}textarea{{min-height:95px}}button,.btn{{display:inline-block;cursor:pointer;border:0;border-radius:8px;background:var(--brand);color:#051d1d;padding:10px 16px;font-weight:700;font:inherit}}.secondary{{background:#263c50;color:var(--text)}}form.inline{{display:inline-block}}form.inline select{{width:auto}}.pill{{background:#14382f;color:#b3ebd6;border-radius:16px;padding:3px 10px;font-size:12px}}.danger{{color:#ffa3ad}}.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}.small{{font-size:12px}}.desc{{white-space:pre-wrap;max-height:260px;overflow:auto;color:var(--muted)}}.footer{{margin-top:50px;padding:25px 20px;border-top:1px solid var(--edge);text-align:center;color:var(--muted)}}
</style></head><body><header class="top"><a class="logo" href="/">◈ JobHuntAI</a><nav>{links}</nav></header><main>{body}</main><footer>Self-hosted Windows edition · v{VERSION} · Source dates must be verified</footer></body></html>'''
    return HTMLResponse(page)


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


REJECT = re.compile(r"\b(soc analyst|security operations center|iam engineer|identity and access management|grc|compliance analyst|network administrator|help.?desk|security monitoring analyst)\b", re.I)
ROLE_GROUPS = {
    "pentest": re.compile(r"\b(penetration test(?:er|ing)?|pentest(?:er|ing)?|vapt|offensive security|web application security test|red team(?:er|ing)?)\b", re.I),
    "appsec": re.compile(r"\b(application security|appsec|product security|api security|software security engineer|secure code review)\b", re.I),
    "llm": re.compile(r"\b(llm security|ai red team|prompt injection|chatbot security|genai security)\b", re.I),
}


def match_job(user, job, now: datetime | None = None):
    """A missing timestamp or failed mandatory rule always rejects the recommendation."""
    now = now or utcnow()
    if not job["active"] or not job["published"]:
        return None
    try:
        pub = datetime.fromisoformat(str(job["published"]).replace("Z", "+00:00"))
        if pub.tzinfo is None:
            return None
        age = (now - pub.astimezone(timezone.utc)).total_seconds()
        if age < -3600 or age > int(user["freshness"]) * 86400:
            return None
    except (ValueError, TypeError):
        return None
    title = str(job["title"])
    desc = str(job["description"] or "")
    if REJECT.search(title):
        return None
    allowed = str(user["role"] or "").lower()
    requested = [k for k in ROLE_GROUPS if k in allowed]
    if not requested:
        requested = [k for k, p in ROLE_GROUPS.items() if p.search(allowed)]
    if not requested:
        return None  # Unsupported role families require explicit mapper registration.
    recognized = [k for k in requested if ROLE_GROUPS[k].search(title)]
    if not recognized:
        return None  # No keyword-only matches on unrelated job titles.
    locations = [x.strip().lower() for x in str(user["locations"] or "").split(",") if x.strip()]
    place = str(job["location"] or "").lower()
    if locations and not any(x in place for x in locations) and not ("remote" in place and "remote" in locations):
        return None
    skills = [x.strip() for x in str(user["skills"] or "").split(",") if x.strip()]
    matched = [s for s in skills if s.lower() in (title + " " + desc).lower()]
    score = min(100, 65 + 5 * min(len(matched), 6) + 5 * (len(recognized) > 1))
    reason = "Matched role: " + ", ".join(recognized) + (". Confirmed skills: " + ", ".join(matched[:6]) if matched else ". Review specific technical requirements.")
    return score, reason


def normalize_date(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 10**11 else value, tz=timezone.utc).isoformat()
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def fetch_source(client: httpx.Client, source):
    kind, slug = source["kind"], source["slug"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,80}", slug):
        raise ValueError("Invalid source slug")
    if kind == "ashby":
        url = f"https://api.ashbyhq.com/posting-api/job-board/{quote(slug)}"
        resp = client.get(url)
        resp.raise_for_status()
        return [{"id": str(j.get("id") or j.get("jobUrl")), "title": j.get("title", ""),
                 "location": j.get("location", ""), "description": j.get("descriptionPlain") or j.get("descriptionHtml", ""),
                 "url": j.get("jobUrl", ""), "published": normalize_date(j.get("publishedAt")), "date_evidence": "ashby.publishedAt"}
                for j in resp.json().get("jobs", []) if j.get("isListed", True)]
    if kind == "greenhouse":
        url = f"https://boards-api.greenhouse.io/v1/boards/{quote(slug)}/jobs?content=true"
        resp = client.get(url)
        resp.raise_for_status()
        return [{"id": str(j.get("id")), "title": j.get("title", ""),
                 "location": (j.get("location") or {}).get("name", ""), "description": j.get("content", ""),
                 "url": j.get("absolute_url", ""), "published": normalize_date(j.get("first_published")),
                 "date_evidence": "greenhouse.first_published" if j.get("first_published") else "UNKNOWN"}
                for j in resp.json().get("jobs", [])]
    if kind == "lever":
        url = f"https://api.lever.co/v0/postings/{quote(slug)}?mode=json"
        resp = client.get(url)
        resp.raise_for_status()
        return [{"id": str(j.get("id")), "title": j.get("text", ""),
                 "location": (j.get("categories") or {}).get("location", ""),
                 "description": j.get("descriptionPlain") or j.get("description", ""),
                 "url": j.get("hostedUrl") or j.get("applyUrl", ""),
                 "published": normalize_date(j.get("createdAt")), "date_evidence": "lever.createdAt (creation, not guaranteed publication)"}
                for j in resp.json()]
    raise ValueError("Unsupported source type")


def scan_all():
    """Run collectors independently; a failed source never invalidates previously stored jobs."""
    initialize()
    with database() as db:
        sources = db.execute("SELECT * FROM sources WHERE enabled=1").fetchall()
    stats = {"sources": len(sources), "ok": 0, "failed": 0, "jobs": 0, "matched": 0}
    with httpx.Client(timeout=24, follow_redirects=False, headers={"User-Agent": "JobHuntAI/0.1 (public job board monitor)"}) as client:
        for source in sources:
            with database() as db:
                db.execute("UPDATE sources SET last_attempt=? WHERE id=?", (iso(), source["id"]))
                try:
                    found = fetch_source(client, source)
                    seen = set()
                    for j in found:
                        url = j["url"]
                        if not url or urlparse(url).scheme != "https" or not j["id"] or not j["title"]:
                            continue
                        jid = f'{source["kind"]}:{source["slug"]}:{j["id"]}'
                        seen.add(jid)
                        db.execute("""INSERT INTO jobs(id,company,title,location,description,url,published,date_evidence,first_seen,last_seen,source_id)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                            title=excluded.title,location=excluded.location,description=excluded.description,
                            url=excluded.url,published=COALESCE(jobs.published,excluded.published),
                            date_evidence=excluded.date_evidence,last_seen=excluded.last_seen,active=1,missing_scans=0""",
                            (jid, source["company"], j["title"], j["location"], str(j["description"])[:30000],
                             url, j["published"], j["date_evidence"], iso(), iso(), source["id"]))
                        stats["jobs"] += 1
                    previous = db.execute("SELECT id,missing_scans FROM jobs WHERE source_id=? AND active=1", (source["id"],)).fetchall()
                    for row in previous:
                        if row["id"] not in seen:
                            misses = row["missing_scans"] + 1
                            db.execute("UPDATE jobs SET missing_scans=?,active=? WHERE id=?", (misses, int(misses < 2), row["id"]))
                    db.execute("UPDATE sources SET success=1,last_success=?,last_error=NULL WHERE id=?", (iso(), source["id"]))
                    stats["ok"] += 1
                except Exception as exc:
                    db.execute("UPDATE sources SET success=0,last_error=? WHERE id=?", (str(exc)[:400], source["id"]))
                    logger.warning("source %s/%s: %s", source["kind"], source["slug"], exc)
                    stats["failed"] += 1
    # The collector never creates a match by itself. Only OpenCode's
    # validated agent decision can promote a hard-filtered candidate.
    with database() as db:
        db.execute("DELETE FROM matches WHERE job_id IN (SELECT id FROM jobs WHERE active=0)")
    logger.info("scan: %s", stats)
    return stats


def send_telegram(chat_id: str, message: str) -> bool:
    token = os.getenv("JOBHUNTAI_TELEGRAM_TOKEN", "")
    if not token or not chat_id:
        return False
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": message[:4000], "disable_web_page_preview": True}, timeout=15)
        r.raise_for_status()
        return bool(r.json().get("ok"))
    except Exception as exc:
        logger.warning("telegram delivery failed: %s", type(exc).__name__)
        return False


def notify_matches():
    with database() as db:
        rows = db.execute("""SELECT u.id AS uid,u.telegram_chat,j.id AS jid,j.company,j.title,j.url,m.score
          FROM matches m JOIN users u ON u.id=m.user_id JOIN jobs j ON j.id=m.job_id
          LEFT JOIN alerts a ON a.user_id=u.id AND a.job_id=j.id AND a.channel='telegram'
          JOIN ai_reviews ar ON ar.user_id=m.user_id AND ar.job_id=m.job_id AND ar.state='approved'
          WHERE a.user_id IS NULL AND u.telegram_chat<>'' AND j.active=1 AND j.published IS NOT NULL
          ORDER BY m.score DESC LIMIT 40""").fetchall()
        for item in rows:
            message = (f"JobHuntAI · {item['score']}% role match\n{item['title']} — {item['company']}\n"
                       f"{item['url']}\nCheck job requirements and application status before applying.")
            if send_telegram(item["telegram_chat"], message):
                db.execute("INSERT OR IGNORE INTO alerts(user_id,job_id,channel,delivered) VALUES(?,?,'telegram',?)",
                           (item["uid"], item["jid"], iso()))


def runner():
    """Autonomous supervisor: independent discovery, collection, AI, and alerts."""
    next_scan = 0
    next_discovery = 0
    while not STOP.is_set():
        current = time.monotonic()
        if current >= next_discovery:
            try:
                autonomy.discover(sys.modules[__name__])
            except Exception:
                logger.exception("autonomous discovery worker failed")
            next_discovery = current + 12 * 3600
        if current >= next_scan:
            try:
                scan_all()
            except Exception:
                logger.exception("job-fetching worker failed")
            next_scan = current + SCAN_INTERVAL
        try:
            ai_engine.launch(ROOT)
            result = autonomy.evaluate(sys.modules[__name__], limit=5)
            logger.info("OpenCode autonomous evaluation: %s", result)
        except Exception:
            logger.exception("OpenCode matching worker failed")
        try:
            notify_matches()
        except Exception:
            logger.exception("alert delivery worker failed")
        STOP.wait(90)


@app.get("/health")
def health():
    with database() as db:
        count = db.execute("SELECT COUNT(*) FROM sources WHERE success=1").fetchone()[0]
    return {"ok": True, "version": VERSION, "healthy_sources": count}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = current_user(request)
    if not user:
        return frame(request, "Welcome", '<div class="card"><h1>Find only jobs that actually fit your career.</h1><p>Multi-user job discovery, strict freshness and role matching, resume management, and application tracking — hosted on your Windows server.</p><a class="btn" href="/register">Create account</a> <a class="btn secondary" href="/login">Log in</a></div>')
    with database() as db:
        m = db.execute("SELECT COUNT(*) FROM matches m JOIN ai_reviews ar ON ar.user_id=m.user_id AND ar.job_id=m.job_id AND ar.state='approved' WHERE m.user_id=?", (user["id"],)).fetchone()[0]
        a = db.execute("SELECT COUNT(*) FROM applications WHERE user_id=?", (user["id"],)).fetchone()[0]
        s = db.execute("SELECT COUNT(*) FROM sources WHERE success=1").fetchone()[0]
        newest = db.execute("""SELECT j.title,j.company,j.id,m.score FROM matches m JOIN jobs j ON j.id=m.job_id
                                  JOIN ai_reviews ar ON ar.user_id=m.user_id AND ar.job_id=m.job_id AND ar.state='approved'
                                  WHERE m.user_id=? ORDER BY j.published DESC LIMIT 5""", (user["id"],)).fetchall()
    rows = "".join(f'<p><a href="/jobs/{quote(j["id"],safe="")}">{escape(j["title"])} — {escape(j["company"])}</a> <span class="pill">{j["score"]}%</span></p>' for j in newest)
    ai_status = autonomy.status(sys.modules[__name__])
    ai_banner = ('OpenCode is evaluating candidates automatically.' if ai_status["running"] else
                 'OpenCode not ready: configure your free OpenRouter key in Settings. No unreviewed matches will be recommended.')

    return frame(request, "Dashboard", f'<h1>Hello, {escape(user["name"])}.</h1><p>Only verified, strictly matching vacancies appear below. No sample counts are shown.</p><div class="cards"><div class="card"><div class="metric">{m}</div>Matching vacancies</div><div class="card"><div class="metric">{a}</div>Tracked applications</div><div class="card"><div class="metric">{s}</div>Healthy sources</div></div><div class="card"><h2>AI worker status</h2><p>{escape(ai_banner)}</p><a href="/ai-status">Agent activity and pending evaluations</a></div><div class="card"><h2>Fresh matching jobs</h2>{rows or "<p>No AI-approved matching vacancies yet. The autonomous engine continues discovering and evaluating.</p>"}<a href="/jobs">Browse all verified matches</a></div>')


@app.get("/register")
def register_page(request: Request):
    return frame(request, "Register", f'<div class="card"><h1>Create an account</h1><form method="post" action="/register">{csrf(request)}<label>Name</label><input name="name" required maxlength="100"><label>Email</label><input type="email" name="email" required maxlength="150"><label>Password (12+ characters)</label><input type="password" name="password" minlength="12" required><p>Use a unique password. Your registration does not expose your resume to other users.</p><button>Create account</button></form></div>')


@app.post("/register")
def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), csrf_token: str = Form("", alias="csrf")):
    check_csrf(request, csrf_token)
    if len(password) < 12 or len(name) > 100 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Invalid registration fields")
    with database() as db:
        try:
            admin = int(db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0)
            cur = db.execute("INSERT INTO users(email,pwd,name,role,admin) VALUES(?,?,?,?,?)",
                             (email.lower().strip(), password_hash(password), name.strip(), "appsec,pentest", admin))
            request.session.clear()
            request.session["uid"] = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Email is already registered") from None
    return redirect("/profile")


@app.get("/login")
def login_page(request: Request):
    return frame(request, "Log in", f'<div class="card"><h1>Log in</h1><form method="post" action="/login">{csrf(request)}<label>Email</label><input type="email" name="email" required><label>Password</label><input type="password" name="password" required><p><button>Log in</button></p></form></div>')


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form("", alias="csrf")):
    check_csrf(request, csrf_token)
    with database() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
    if user is None or not password_valid(password, user["pwd"]):
        raise HTTPException(401, "Invalid email or password")
    request.session.clear()
    request.session["uid"] = user["id"]
    return redirect("/")


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


@app.get("/profile")
def profile_page(request: Request):
    u = require_user(request)
    return frame(request, "My profile", f'''<h1>Professional profile</h1><div class="card"><form method="post" action="/profile">{csrf(request)}
    <label>Strict role families (comma-separated: pentest, appsec, llm)</label><input name="role" value="{escape(u['role'])}" maxlength="120" required>
    <label>Verified skills (comma-separated; never add unfamiliar technology)</label><textarea name="skills">{escape(u['skills'])}</textarea>
    <label>Preferred locations (comma-separated; blank for all)</label><input name="locations" value="{escape(u['locations'])}">
    <label>Freshness limit (days)</label><select name="freshness">{''.join(f'<option value="{d}" {"selected" if u["freshness"] == d else ""}>{d} days</option>' for d in [1,2,3,7,14,21,28,30])}</select>
    <label>LinkedIn public profile URL</label><input name="linkedin" value="{escape(u['linkedin'])}" maxlength="500">
    <label>Custom preferences (notes; advisory, not a substitute for hard filters)</label><textarea name="notes">{escape(u['notes'])}</textarea>
    <button>Save profile</button></form></div>''')


@app.post("/profile")
def profile_save(request: Request, role: str = Form(...), skills: str = Form(""), locations: str = Form(""), freshness: int = Form(7), linkedin: str = Form(""), notes: str = Form(""), csrf_token: str = Form("", alias="csrf")):
    u = require_user(request)
    check_csrf(request, csrf_token)
    tokens = set(x.strip().lower() for x in role.split(","))
    if not tokens or not tokens.issubset(ROLE_GROUPS) or freshness not in {1,2,3,7,14,21,28,30}:
        raise HTTPException(400, "Choose supported strict role families and a valid freshness window")
    if linkedin and not linkedin.startswith("https://www.linkedin.com/"):
        raise HTTPException(400, "Use a public LinkedIn HTTPS URL")
    with database() as db:
        db.execute("UPDATE users SET role=?,skills=?,locations=?,freshness=?,linkedin=?,notes=? WHERE id=?",
                   (",".join(sorted(tokens)), skills[:3000], locations[:300], freshness, linkedin[:500], notes[:2000], u["id"]))
        db.execute("DELETE FROM matches WHERE user_id=?", (u["id"],))
        jobs = db.execute("SELECT * FROM jobs WHERE active=1").fetchall()
        new_user = db.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
        for job in jobs:
            result = match_job(new_user, job)
            if result:
                db.execute("INSERT INTO matches(user_id,job_id,score,reason,created) VALUES(?,?,?,?,?)",
                           (u["id"], job["id"], result[0], result[1], iso()))
    return redirect("/")


@app.get("/jobs")
def jobs_page(request: Request):
    user = require_user(request)
    with database() as db:
        rows = db.execute("""SELECT j.*,m.score,m.reason FROM matches m JOIN jobs j ON j.id=m.job_id
            JOIN ai_reviews ar ON ar.user_id=m.user_id AND ar.job_id=m.job_id AND ar.state='approved'
            WHERE m.user_id=? AND j.active=1 ORDER BY j.published DESC LIMIT 200""", (user["id"],)).fetchall()
    body = '<h1>Verified matches</h1><p>Only active jobs within your freshness window and approved role families. Scores indicate matching signals, not hiring probability.</p>'
    for j in rows:
        body += (f'<div class="card"><span class="pill">{j["score"]}% role fit</span> <span class="muted small">{escape(j["date_evidence"])}</span>'
                 f'<h2><a href="/jobs/{quote(j["id"],safe="")}">{escape(j["title"])} — {escape(j["company"])}</a></h2>'
                 f'<p>{escape(j["location"])} · Posted {escape(j["published"][:10])}</p><p>{escape(j["reason"])}</p>'
                 f'<a href="{escape(j["url"])}" target="_blank" rel="noopener noreferrer">Original employer posting</a></div>')
    return frame(request, "Matching jobs", body if rows else body + '<div class="card">No matching, verifiably fresh jobs yet. Sources may be healthy without offering a suitable vacancy.</div>')


@app.get("/jobs/{job_id:path}")
def job_page(job_id: str, request: Request):
    user = require_user(request)
    with database() as db:
        job = db.execute("""SELECT j.*,m.score,m.reason FROM jobs j JOIN matches m ON m.job_id=j.id
                                 JOIN ai_reviews ar ON ar.user_id=m.user_id AND ar.job_id=m.job_id AND ar.state='approved'
                                 WHERE j.id=? AND m.user_id=? AND j.active=1""", (job_id, user["id"])).fetchone()
        applied = db.execute("SELECT * FROM applications WHERE user_id=? AND job_id=?", (user["id"], job_id)).fetchone()
    if not job:
        raise HTTPException(404, "No verified match found")
    return frame(request, job["title"], f'''<h1>{escape(job['title'])}</h1><p>{escape(job['company'])} · {escape(job['location'])} · {escape(job['published'])}</p>
      <p><span class="pill">{job['score']}% role fit</span> {escape(job['reason'])}</p>
      <p><a class="btn" href="{escape(job['url'])}" target="_blank" rel="noopener noreferrer">Open original posting</a> <a class="btn secondary" href="/resume-tailor/{quote(job_id,safe='')}">Download factual tailored DOCX</a></p>
      <div class="card"><h2>Job description</h2><div class="desc">{escape(re.sub('<[^>]+>', ' ', job['description'] or ''))}</div></div>
      <div class="card"><h2>Track your application</h2><form method="post" action="/apply/{quote(job_id,safe='')}">{csrf(request)}<label>Status</label><select name="status">{''.join(f'<option {"selected" if applied and applied["status"]==s else ""}>{s}</option>' for s in ['Saved','Applied','Under review','Assessment','Interview','Offer','Rejected','Withdrawn'])}</select><label>Notes / recruiter response</label><textarea name="notes">{escape(applied['notes'] if applied else '')}</textarea><p><button>Save status</button></p></form></div>
      <div class="card"><h2>Outreach draft</h2><p>Hi, I came across the {escape(job['title'])} opening at {escape(job['company'])}. My professional experience is in {escape(user['role'])}, and the role looks relevant to my background. I would appreciate an opportunity to discuss whether my profile may be suitable. I can share my resume for reference. Thank you.</p><p class="small">Draft only. Review for accuracy before sending.</p></div>''')


@app.post("/apply/{job_id:path}")
def apply_save(job_id: str, request: Request, status: str = Form(...), notes: str = Form(""), csrf_token: str = Form("", alias="csrf")):
    user = require_user(request)
    check_csrf(request, csrf_token)
    if status not in {'Saved','Applied','Under review','Assessment','Interview','Offer','Rejected','Withdrawn'}:
        raise HTTPException(400, "Invalid status")
    with database() as db:
        ok = db.execute("SELECT 1 FROM matches WHERE user_id=? AND job_id=?", (user["id"], job_id)).fetchone()
        if not ok:
            raise HTTPException(404, "Job not available to your profile")
        db.execute("""INSERT INTO applications(user_id,job_id,status,notes,created,updated) VALUES(?,?,?,?,?,?)
          ON CONFLICT(user_id,job_id) DO UPDATE SET status=excluded.status, notes=excluded.notes, updated=excluded.updated""",
          (user["id"], job_id, status, notes[:5000], iso(), iso()))
    return redirect("/applications")


@app.get("/applications")
def applications_page(request: Request):
    user = require_user(request)
    with database() as db:
        items = db.execute("""SELECT a.*,j.company,j.title,j.url FROM applications a JOIN jobs j ON a.job_id=j.id
              WHERE a.user_id=? ORDER BY a.updated DESC""", (user["id"],)).fetchall()
    body = '<h1>Application tracker</h1><p>Statuses are user-recorded, not claims about a private employer ATS.</p>'
    for j in items:
        body += f'<div class="card"><span class="pill">{escape(j["status"])}</span> <a href="/jobs/{quote(j["job_id"],safe="")}">{escape(j["title"])} — {escape(j["company"])}</a><p class="small">Updated {escape(j["updated"])}</p><p>{escape(j["notes"])}</p></div>'
    return frame(request, "Applications", body if items else body + '<div class="card">No tracked applications yet.</div>')


@app.get("/resumes")
def resumes_page(request: Request):
    user = require_user(request)
    with database() as db:
        resumes = db.execute("SELECT id,filename,created FROM resumes WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    body = f'''<h1>My resumes</h1><div class="card"><form method="post" enctype="multipart/form-data" action="/resumes">{csrf(request)}
    <label>Upload an authentic DOCX or PDF (max 2 MB)</label><input type="file" name="file" accept=".docx,.pdf" required><p><button>Upload resume</button></p></form></div>'''
    for r in resumes:
        body += f'<div class="card">{escape(r["filename"])} · {escape(r["created"])} · <a href="/resumes/{r["id"]}">Download original</a></div>'
    return frame(request, "Resumes", body)


@app.post("/resumes")
async def resume_upload(request: Request, file: UploadFile = File(...), csrf_token: str = Form("", alias="csrf")):
    user = require_user(request)
    check_csrf(request, csrf_token)
    name = Path(file.filename or "").name
    data = await file.read(2_097_153)
    if len(data) > 2_097_152 or not name.lower().endswith((".docx", ".pdf")):
        raise HTTPException(400, "Only DOCX/PDF up to 2 MB")
    try:
        if name.lower().endswith(".pdf"):
            if not data.startswith(b"%PDF"):
                raise ValueError("PDF magic bytes missing")
            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages[:20])
        else:
            if not data.startswith(b"PK"):
                raise ValueError("DOCX signature missing")
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    except Exception:
        raise HTTPException(400, "File is invalid or could not be parsed") from None
    if len(text.strip()) < 30:
        raise HTTPException(400, "Resume has no extractable text. Please upload a text-based document")
    user_folder = ROOT / "resumes" / str(user["id"])
    user_folder.mkdir(parents=True, exist_ok=True)
    file_path = user_folder / (secrets.token_hex(16) + Path(name).suffix.lower())
    file_path.write_bytes(data)
    with database() as db:
        db.execute("INSERT INTO resumes(user_id,filename,filepath,extracted,created) VALUES(?,?,?,?,?)",
                   (user["id"], name[:150], str(file_path), text[:50000], iso()))
    return redirect("/resumes")


@app.get("/resumes/{resume_id:int}")
def resume_download(resume_id: int, request: Request):
    user = require_user(request)
    with database() as db:
        row = db.execute("SELECT * FROM resumes WHERE id=? AND user_id=?", (resume_id, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "Resume not found")
    ext = Path(row["filename"]).suffix.lower()
    return Response(Path(row["filepath"]).read_bytes(), media_type="application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="resume-{resume_id}{ext}"'})


@app.get("/resume-tailor/{job_id:path}")
def resume_tailor(job_id: str, request: Request):
    user = require_user(request)
    with database() as db:
        job = db.execute("SELECT j.* FROM jobs j JOIN matches m ON m.job_id=j.id WHERE j.id=? AND m.user_id=?", (job_id, user["id"])).fetchone()
        resume = db.execute("SELECT * FROM resumes WHERE user_id=? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
    if not job or not resume:
        raise HTTPException(404, "Upload your original resume first")
    # No invented technologies. Original content is preserved verbatim, plus only user-confirmed skills.
    doc = Document()
    doc.add_heading(user["name"], 0)
    doc.add_paragraph(user["email"])
    doc.add_heading("Target role", level=1)
    doc.add_paragraph(job["title"] + " — " + job["company"])
    confirmed = [s.strip() for s in user["skills"].split(",") if s.strip() and s.lower() in (job["title"] + " " + job["description"]).lower()]
    if confirmed:
        doc.add_heading("Relevant verified skills", level=1)
        doc.add_paragraph(", ".join(confirmed[:20]))
    doc.add_heading("Experience and background — original resume text", level=1)
    for para in resume["extracted"].splitlines()[:350]:
        if para.strip():
            doc.add_paragraph(para.strip())
    out = io.BytesIO()
    doc.save(out)
    fname = re.sub(r"[^A-Za-z0-9_-]+", "-", job["company"])[:40] + "-tailored.docx"
    return Response(out.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/settings")
def settings_page(request: Request):
    u = require_user(request)
    with database() as db:
        sources = db.execute("SELECT * FROM sources ORDER BY company").fetchall() if u["admin"] else []
    body = f'''<h1>Settings</h1><div class="card"><h2>Telegram alerts</h2><p>Start your Telegram bot and enter its numeric chat ID. Set JOBHUNTAI_TELEGRAM_TOKEN in your server environment.</p>
       <form method="post" action="/settings/telegram">{csrf(request)}<label>Telegram chat ID</label><input name="chat_id" value="{escape(u['telegram_chat'])}" pattern="-?[0-9]{{4,20}}" placeholder="123456789"><p><button>Save notification setting</button></p></form></div>'''
    if u["admin"]:
        body += f'''<div class="card"><h2>ATS company registry (administrator)</h2><form method="post" action="/settings/source">{csrf(request)}
           <label>ATS provider</label><select name="kind"><option>ashby</option><option>greenhouse</option><option>lever</option></select>
           <label>Board slug (not URL)</label><input name="slug" pattern="[A-Za-z0-9_-]{{2,80}}" required>
           <label>Employer display name</label><input name="company" maxlength="120" required><p><button>Add source</button></p></form>
           <h2>Source health</h2>'''
        for s in sources:
            body += f'<p>{escape(s["company"])} — {escape(s["kind"])}/{escape(s["slug"])} · {"Healthy" if s["success"] else "Not verified"} · <span class="small">{escape(s["last_error"])}</span></p>'
        body += '</div>'
    body += '<div class="card"><h2>Integration status</h2><p>OpenCode v1: optional separately bundled runtime; browser AI automation is not enabled by default. Telegram: ' + ('configured' if os.getenv('JOBHUNTAI_TELEGRAM_TOKEN') else 'needs token') + '. WhatsApp and mailbox OAuth are not connected in this version.</p></div>'
    return frame(request, "Settings", body)


@app.post("/settings/telegram")
def set_telegram(request: Request, chat_id: str = Form(""), csrf_token: str = Form("", alias="csrf")):
    u = require_user(request)
    check_csrf(request, csrf_token)
    if chat_id and not re.fullmatch(r"-?\d{4,20}", chat_id):
        raise HTTPException(400, "Invalid chat ID")
    with database() as db:
        db.execute("UPDATE users SET telegram_chat=? WHERE id=?", (chat_id, u["id"]))
    return redirect("/settings")


@app.post("/settings/source")
def add_source(request: Request, kind: str = Form(...), slug: str = Form(...), company: str = Form(...), csrf_token: str = Form("", alias="csrf")):
    u = require_user(request)
    check_csrf(request, csrf_token)
    if not u["admin"] or kind not in {"ashby", "greenhouse", "lever"} or not re.fullmatch(r"[A-Za-z0-9_-]{2,80}", slug):
        raise HTTPException(403, "Invalid or unauthorized source")
    with database() as db:
        db.execute("INSERT OR IGNORE INTO sources(kind,slug,company) VALUES(?,?,?)", (kind, slug, company[:120]))
    return redirect("/settings")


def main():
    parser = argparse.ArgumentParser(description="JobHuntAI self-hosted Windows web server")
    parser.add_argument("command", nargs="?", choices=["serve", "scan", "health", "agent-status"], default="serve")
    parser.add_argument("--host", default=os.getenv("JOBHUNTAI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("JOBHUNTAI_PORT", "8000")))
    args = parser.parse_args()
    initialize()
    if args.command == "scan":
        print(json.dumps(scan_all(), indent=2))
        ai_engine.launch(ROOT)
        print("OpenCode agent:", json.dumps(autonomy.evaluate(sys.modules[__name__])))
        notify_matches()
    elif args.command == "agent-status":
        print(json.dumps(autonomy.status(sys.modules[__name__]), indent=2))
    elif args.command == "health":
        with database() as db:
            print(json.dumps([dict(x) for x in db.execute("SELECT company,kind,last_success,last_error FROM sources")], indent=2))
    else:
        if os.getenv("JOBHUNTAI_AUTO_SCAN", "1") == "1":
            threading.Thread(target=runner, name="collector", daemon=True).start()
        print(f"JobHuntAI listening at http://{args.host}:{args.port} (data: {ROOT})")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info", proxy_headers=False)


initialize()
if __name__ == "__main__":
    main()