"""JobHuntAI persistence, safe role filters, source adapters and evaluation."""
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import httpx

DB = os.getenv("JOBHUNT_DB", "jobhunt.db")
INITIAL_DAYS = int(os.getenv("JOBHUNT_INITIAL_DAYS", "30"))
ALERT_SCORE = int(os.getenv("JOBHUNT_ALERT_SCORE", "85"))
ROLE_TERMS = ("penetration test", "pentest", "pen test", "application security",
              "appsec", "offensive security", "security researcher", "red team",
              "vulnerability research", "web security", "product security")
EXCLUDED = ("soc analyst", "security operations center", "iam analyst",
            "identity and access management", "grc analyst", "compliance analyst",
            "security governance", "network operations", "security auditor")
DEFAULT_PROFILE = {"roles": ["Penetration Tester", "Application Security Engineer", "Offensive Security Engineer"],
                   "locations": ["India", "Remote"], "skills": [], "exclude_roles": [],
                   "strict": True, "initial_days": INITIAL_DAYS, "alert_threshold": ALERT_SCORE}
def now():
    return datetime.now(timezone.utc)
def connect():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    return con
def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,source TEXT NOT NULL,title TEXT NOT NULL,
          company TEXT NOT NULL,location TEXT,description TEXT,url TEXT NOT NULL,posted_at TEXT,
          first_seen TEXT NOT NULL,verified_at TEXT,active INTEGER NOT NULL DEFAULT 1,
          score INTEGER,insight TEXT,missing TEXT,notified INTEGER NOT NULL DEFAULT 0,
          saved INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY AUTOINCREMENT,
          started TEXT,ended TEXT,status TEXT,found INTEGER DEFAULT 0,error TEXT);
        CREATE TABLE IF NOT EXISTS devices(token TEXT PRIMARY KEY, created TEXT NOT NULL);
        """)
        if not db.execute("SELECT 1 FROM settings WHERE key='profile'").fetchone():
            db.execute("INSERT INTO settings VALUES (?,?)",("profile", json.dumps(DEFAULT_PROFILE)))
def setting(key, default=None):
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default
def set_setting(key, value):
    with connect() as db:
        db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key,json.dumps(value)))
def normalize_url(url):
    p=urlparse(url)
    safe=[(k,v) for k,v in parse_qsl(p.query) if k.lower() not in
          ("utm_source","utm_medium","utm_campaign","utm_term","utm_content","ref","source")]
    return urlunparse((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/"),"",urlencode(safe),""))
def job_id(url):
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()[:24]
ROLE_ALIASES = {
    "penetration tester": ("penetration test","pentest","pen test","vapt","ethical hacker"),
    "application security engineer": ("application security","appsec","web application security"),
    "appsec engineer": ("application security","appsec","web application security"),
    "offensive security engineer": ("offensive security","red team","adversary emulation"),
    "red team engineer": ("red team","red teaming","adversary emulation"),
    "product security engineer": ("product security",),
    "security researcher": ("security researcher","vulnerability researcher",
                            "vulnerability research"),
    "web application security tester": ("web application security","web penetration test","web pentest"),
}
def role_matches(job, profile):
    """Strict: only user-selected role families and their title synonyms qualify."""
    title=(job.get("title") or "").casefold()
    exclusions=EXCLUDED+tuple(s.casefold() for s in profile.get("exclude_roles",[])
                              if isinstance(s,str))
    if any(term in title for term in exclusions):return False
    if not profile.get("strict",True):return True
    roles=profile.get("roles") or DEFAULT_PROFILE["roles"]
    for role in roles:
        if not isinstance(role,str):continue
        synonyms=ROLE_ALIASES.get(role.casefold(),(role.casefold(),))
        if any(alias in title for alias in synonyms):return True
    return False

def posted_recent(iso, days):
    if not iso: return False
    try:
        ts=datetime.fromisoformat(iso.replace("Z","+00:00"))
        if ts.tzinfo is None:
            # JobPosting datePosted often uses YYYY-MM-DD without a timezone.
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}",iso):
                ts=ts.replace(tzinfo=timezone.utc)
            else:return False
        return now()-timedelta(days=days) <= ts <= now()+timedelta(hours=2)
    except (ValueError,TypeError): return False
async def fetch_greenhouse(client, board):
    url=f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    response=await client.get(url); response.raise_for_status()
    for j in response.json().get("jobs",[]):
        # The list can omit first_published; retrieve details for relevant titles.
        if not j.get("first_published") and j.get("id") and any(
                term in (j.get("title") or "").lower() for term in ROLE_TERMS):
            try:
                detail=await client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{j['id']}")
                detail.raise_for_status()
                expanded=detail.json()
                j["first_published"]=expanded.get("first_published")
                j["application_deadline"]=expanded.get("application_deadline")
            except (httpx.HTTPError,ValueError,TypeError):
                pass
        # first_published is publication evidence; updated_at is not.
        yield {"source":"greenhouse","title":j.get("title",""),"company":board,
               "location":(j.get("location") or {}).get("name",""),
               "description":re.sub("<[^>]+>"," ",j.get("content") or ""),
               "url":j.get("absolute_url",""),"posted_at":j.get("first_published"),
               "valid_through":j.get("application_deadline")}
async def fetch_lever(client, site):
    response=await client.get(f"https://api.lever.co/v0/postings/{site}?mode=json")
    response.raise_for_status()
    for j in response.json():
        categories=j.get("categories") or {}
        created=j.get("createdAt")
        try:
            created_at=datetime.fromtimestamp(float(created)/1000,timezone.utc).isoformat() if created else None
        except (TypeError,ValueError,OverflowError):created_at=None
        salary_range=j.get("salaryRange") or {}
        if isinstance(salary_range,dict) and salary_range.get("min") is not None:
            salary=f'{salary_range.get("currency","")} {salary_range.get("min")}–{salary_range.get("max","")} {salary_range.get("interval","")}'
        else:
            salary=j.get("salaryDescription")
        yield {"source":"lever","title":j.get("text",""),"company":site,
               "location":categories.get("location",""),
               "description":(j.get("descriptionPlain") or "")+" "+(j.get("additionalPlain") or ""),
               "url":j.get("hostedUrl",""),"posted_at":None,
               "created_at":created_at,"salary":salary}
