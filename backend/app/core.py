"""JobHuntAI persistence, safe role filters, source adapters and evaluation."""
import asyncio
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
def role_matches(job, profile):
    title=job.get("title","").lower()
    desc=(job.get("description") or "").lower()
    if any(term in title for term in EXCLUDED+tuple(s.lower() for s in profile.get("exclude_roles",[]))):
        return False
    if not profile.get("strict",True):
        return True
    # A relevant security job must be described by a relevant title, not keyword-stuffed body.
    return any(term in title for term in ROLE_TERMS) or any(
        re.search(r"\b"+re.escape(role.lower())+r"\b",title) for role in profile.get("roles",[]))
def posted_recent(iso, days):
    if not iso: return False
    try:
        ts=datetime.fromisoformat(iso.replace("Z","+00:00"))
        if ts.tzinfo is None: return False
        return now()-timedelta(days=days) <= ts <= now()+timedelta(hours=2)
    except (ValueError,TypeError): return False
async def fetch_greenhouse(client, board):
    url=f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    response=await client.get(url); response.raise_for_status()
    for j in response.json().get("jobs",[]):
        # Greenhouse updated_at is NOT a reliable created_at: do not assert posting freshness.
        yield {"source":"greenhouse","title":j.get("title",""),"company":board,
               "location":(j.get("location") or {}).get("name",""),
               "description":re.sub("<[^>]+>"," ",j.get("content") or ""),
               "url":j.get("absolute_url",""),"posted_at":None}
async def fetch_lever(client, site):
    response=await client.get(f"https://api.lever.co/v0/postings/{site}?mode=json")
    response.raise_for_status()
    for j in response.json():
        categories=j.get("categories") or {}
        yield {"source":"lever","title":j.get("text",""),"company":site,
               "location":categories.get("location",""),
               "description":(j.get("descriptionPlain") or "")+" "+(j.get("additionalPlain") or ""),
               "url":j.get("hostedUrl",""),"posted_at":None}
async def sources():
    feeds=setting("feeds", [])
    async with httpx.AsyncClient(timeout=20,follow_redirects=True,
             headers={"User-Agent":"JobHuntAI/0.1 (personal job discovery)"}) as client:
        for feed in feeds:
            kind=feed.get("type"); name=feed.get("name","")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",name): continue
            try:
                if kind=="greenhouse":
                    async for job in fetch_greenhouse(client,name): yield job
                elif kind=="lever":
                    async for job in fetch_lever(client,name): yield job
            except (httpx.HTTPError,ValueError,KeyError):
                continue
def heuristic(job,profile):
    text=(job.get("title","")+" "+job.get("description","")).lower()
    skills=[s for s in profile.get("skills",[]) if isinstance(s,str) and len(s)<80]
    matching=[s for s in skills if s.lower() in text]
    missing=[s for s in skills if s not in matching]
    # No resume or configured skills => no unfounded high match.
    score=round(40+min(40,60*len(matching)/max(len(skills),1))) if skills else 0
    return {"score":score,"insight":"Matched skills: "+(", ".join(matching) or "none verified"),
            "missing":missing[:10]}
async def evaluate(job,profile):
    fallback=heuristic(job,profile)
    url=os.getenv("JOBHUNT_OPENCODE_URL","").rstrip("/")
    if not url: return fallback
    instructions=("Assess this job against ONLY the verified skills provided. Strict cybersecurity "
      "role-family matching. Never invent experience. Return ONLY JSON: "
      '{"score":0,"insight":"short evidence-based reason","missing":["requirements"]}. '
      "Score 0-100; be conservative and mark insufficient evidence low.")
    payload={"parts":[{"type":"text","text":instructions+"\n"+json.dumps({
        "profile":profile,"job":{k:job.get(k) for k in ("title","company","description","location")}},
        ensure_ascii=False)[:15000]}]}
    try:
        auth=None
        if os.getenv("JOBHUNT_OPENCODE_PASSWORD"):
            auth=("opencode",os.environ["JOBHUNT_OPENCODE_PASSWORD"])
        async with httpx.AsyncClient(timeout=45,auth=auth) as client:
            session=await client.post(url+"/session",json={})
            session.raise_for_status()
            sid=session.json()["id"]
            data=await client.post(url+f"/session/{sid}/message",json=payload)
            data.raise_for_status()
        parts=data.json().get("parts",[])
        output=" ".join(p.get("text","") for p in parts if p.get("type")=="text")
        match=re.search(r"\{[\s\S]*\}",output)
        parsed=json.loads(match.group()) if match else {}
        score=int(parsed.get("score",-1))
        if not 0<=score<=100: return fallback
        return {"score":score,"insight":str(parsed.get("insight",""))[:400],
                "missing":[str(x)[:100] for x in parsed.get("missing",[])][:10]}
    except (httpx.HTTPError,KeyError,ValueError,TypeError,OverflowError):
        return fallback
async def scan(notify=None):
    if setting("paused",False): return {"status":"paused"}
    profile=setting("profile",DEFAULT_PROFILE)
    started=now().isoformat()
    with connect() as db:
        cur=db.execute("INSERT INTO scans(started,status) VALUES (?,?)",(started,"running"))
        scan_id=cur.lastrowid
    count=0; failures=[]
    try:
        async for job in sources():
            if not job.get("url","").startswith("https://"): continue
            if not role_matches(job,profile): continue
            days=int(profile.get("initial_days",INITIAL_DAYS)) if not setting("initial_done",False) else 1
            # Keep undated jobs unverified, not push-alert eligible; first-seen captures new discovery.
            if job.get("posted_at") and not posted_recent(job["posted_at"],days): continue
            uid=job_id(job["url"])
            with connect() as db:
                if db.execute("SELECT 1 FROM jobs WHERE id=?",(uid,)).fetchone(): continue
            result=await evaluate(job,profile)
            verified=bool(job.get("posted_at")) and posted_recent(job["posted_at"],days)
            with connect() as db:
                db.execute("""INSERT OR IGNORE INTO jobs
                (id,source,title,company,location,description,url,posted_at,first_seen,
                verified_at,active,score,insight,missing) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid,job["source"],job["title"],job["company"],job["location"],
                 job["description"][:20000],normalize_url(job["url"]),job.get("posted_at"),
                 now().isoformat(),now().isoformat() if verified else None,1,
                 result["score"],result["insight"],json.dumps(result["missing"])))
            count+=1
            if verified and result["score"]>=int(profile.get("alert_threshold",ALERT_SCORE)) and notify:
                try: await notify(uid)
                except Exception as exc: failures.append(str(exc)[:150])
        set_setting("initial_done",True)
        status="complete" if not failures else "partial"
    except Exception as exc:
        failures.append(str(exc)[:200]); status="error"
    with connect() as db:
        db.execute("UPDATE scans SET ended=?,status=?,found=?,error=? WHERE id=?",
                   (now().isoformat(),status,count,"; ".join(failures),scan_id))
    return {"status":status,"new_jobs":count,"errors":failures}
