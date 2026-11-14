"""Durable, observable scan lifecycle. Source errors never masquerade as zero vacancies."""
import asyncio
import json
import os
import re
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import httpx
from .core import (
    now,connect,setting,set_setting,normalize_url,job_id,posted_recent,role_matches,
    fetch_greenhouse,fetch_lever,DEFAULT_PROFILE
)
from .catalog import ATS
from .discovery import fetch_ashby,indexed_jobs,parse_job_posting,allowed_url
from .opencode import evaluate
from .smartrecruiters import fetch_smartrecruiters

def migrate():
    with connect() as db:
        for col,kind in [("last_seen","TEXT"),("model_verified","INTEGER NOT NULL DEFAULT 0"),
                          ("dismissed","INTEGER NOT NULL DEFAULT 0"), ("active_check","TEXT NOT NULL DEFAULT 'unverified'"),
                          ("source_ref","TEXT"),("closed_at","TEXT")]:
            existing={r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
            if col not in existing:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {col} {kind}")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS source_health(
          name TEXT PRIMARY KEY, checked_at TEXT, status TEXT,
          items INTEGER DEFAULT 0,error TEXT, failures INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS feedback(
          id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,
          value TEXT NOT NULL,reason TEXT, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications(
          id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT, sent_at TEXT, created_at TEXT NOT NULL);
        """)

def source_report(name,status,items=0,error=""):
    with connect() as db:
        old=db.execute("SELECT failures FROM source_health WHERE name=?",(name,)).fetchone()
        failures=(old["failures"] if old else 0)+1 if status=="error" else 0
        db.execute("""INSERT INTO source_health VALUES(?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET checked_at=excluded.checked_at,
            status=excluded.status, items=excluded.items, error=excluded.error,
            failures=excluded.failures""",(name,now().isoformat(),status,items,error[:500],failures))



def close_missing(key, seen):
    """Only a successful complete ATS board response may close absent jobs."""
    with connect() as db:
        records=db.execute("SELECT id FROM jobs WHERE source_ref=? AND active=1",(key,)).fetchall()
        for row in records:
            if row["id"] not in seen:
                db.execute("UPDATE jobs SET active=0,closed_at=? WHERE id=?",
                           (now().isoformat(),row["id"]))

def feedback_adjustment(job):
    """Bounded preference adjustment; never overrides strict role-family filtering."""
    with connect() as db:
        votes=db.execute("""SELECT f.value FROM feedback f JOIN jobs j ON j.id=f.job_id
          WHERE lower(j.company)=lower(?) ORDER BY f.id DESC LIMIT 25""",
          (job.get("company",""),)).fetchall()
    bad=sum(x["value"] in ("dismiss","irrelevant") for x in votes)
    good=sum(x["value"]=="relevant" for x in votes)
    return max(-20,min(10,good*3-bad*5))

async def hydrate_posting(client,job):
    """Read JobPosting metadata from allowlisted pages, without following redirects."""
    url=job.get("url","")
    if not allowed_url(url):return job
    try:
        page=await client.get(url,timeout=12,follow_redirects=False)
        if page.status_code in (404,410):return None
        if page.status_code!=200:return job
        if "text/html" not in page.headers.get("content-type",""):return job
        markup=page.text[:500000]
        lowered=markup.lower()
        if any(x in lowered for x in ("this job is no longer accepting applications",
            "this position has been filled","this job is no longer available")):
            return None
        structured=parse_job_posting(markup,url)
        if structured:
            if structured.get("posted_at") and not job.get("posted_at"):
                job["posted_at"]=structured["posted_at"]
            if structured.get("valid_through"):job["valid_through"]=structured["valid_through"]
        job["active_check"]="listed_page_responds"
    except (httpx.HTTPError,ValueError,TypeError):
        pass
    return job

def in_region(location):
    if not location:return True
    normalized=location.casefold()
    cities=("india","indian","bengaluru","bangalore","hyderabad","chennai","pune","mumbai",
            "delhi","noida","gurugram","gurgaon","kolkata","bhubaneswar","kochi",
            "coimbatore","tamil nadu","erode","trivandrum","thiruvananthapuram")
    if any(x in normalized for x in cities) or normalized.strip().endswith(", in"):return True
    # Remote jobs require more validation before being considered eligible in India.
    if "remote" in normalized:
        excluded=("united states","usa only","us only","north america only",
                  "europe only","uk only","canada only")
        return not any(x in normalized for x in excluded)
    return False


def location_allowed(location,profile):
    preferences=[str(x).casefold() for x in profile.get("locations",["India","Remote"])]
    if not location:return True   # Unknown must be marked, not misrepresented.
    name=location.casefold()
    if not in_region(location):return False
    if not preferences:return True
    if "india" in preferences and in_region(location):return True
    if "remote" in preferences and "remote" in name:return True
    synonyms={"tamil nadu":("chennai","coimbatore","erode","madurai","salem","trichy","tiruchirappalli"),
              "karnataka":("bengaluru","bangalore","mysuru","mysore"),
              "telangana":("hyderabad",),
              "maharashtra":("pune","mumbai","nagpur"),
              "odisha":("bhubaneswar","cuttack","berhampur","brahmapur")}
    return any(pref in name or any(city in name for city in synonyms.get(pref,()))
               for pref in preferences)

def experience_eligible(job,profile):
    years=profile.get("years_experience")
    if years is None:return True
    try:years=float(years)
    except (ValueError,TypeError):return True
    text=(job.get("description") or "").lower()
    patterns=[r"(?:minimum|at least|min\.?)\s*(\d{1,2})\+?\s*(?:years|yrs)",
              r"(\d{1,2})\s*\+\s*(?:years|yrs)\s+(?:of\s+)?experience",
              r"(\d{1,2})\s*[-–]\s*\d{1,2}\s*(?:years|yrs)"]
    req=[]
    for pattern in patterns:
        req.extend(int(m) for m in re.findall(pattern,text))
    return not req or min(req)<=years+1.0

def valid_until(value):
    if not value:return True
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt>=now()
    except (ValueError,TypeError):return True

async def collect_sources(process, diagnostics):
    feeds=setting("feeds",ATS)
    async with httpx.AsyncClient(timeout=18,follow_redirects=False,
         headers={"User-Agent":"JobHuntAI/0.2 (personal job search; contact repository owner)"}) as client:
        for feed in feeds:
            kind,name=feed.get("type"),feed.get("name","")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",name):continue
            key=kind+":"+name
            count=0
            seen=set()
            try:
                if kind=="lever": stream=fetch_lever(client,name)
                elif kind=="greenhouse":stream=fetch_greenhouse(client,name)
                elif kind=="ashby":stream=fetch_ashby(client,name)
                elif kind=="smartrecruiters":stream=fetch_smartrecruiters(client,name)
                else:continue
                async for job in stream:
                    count+=1
                    if job.get("url"):seen.add(job_id(job["url"]))
                    job["source_ref"]=key
                    await process(job)
                close_missing(key,seen)
                source_report(key,"ok",count); diagnostics["ok"]+=1
            except (httpx.HTTPError,ValueError,TypeError,KeyError) as error:
                source_report(key,"error",count,str(error))
                diagnostics["error"]+=1
        # Indexed discovery works on a bounded rotating subset each scan.
        if setting("search_enabled",True):
            count=0
            try:
                async for job in indexed_jobs(client):
                    count+=1
                    await process(job)
                # This means the query completed, NOT that all searches were indexed.
                source_report("indexed:bing","ok",count);diagnostics["ok"]+=1
            except (httpx.HTTPError,ValueError,TypeError) as error:
                source_report("indexed:bing","error",count,str(error));diagnostics["error"]+=1

async def scan(notify=None):
    if setting("paused",False):return {"status":"paused"}
    profile=setting("profile",DEFAULT_PROFILE)
    started=now()
    migrate()
    with connect() as db:
        scan_id=db.execute("INSERT INTO scans(started,status) VALUES(?,?)",
                           (started.isoformat(),"running")).lastrowid
    first=not setting("initial_done",False)
    # Recover downtime: do not lose jobs posted after last successful scan.
    with connect() as db:
        last=db.execute("SELECT ended FROM scans WHERE status IN ('complete','partial') AND id<>? ORDER BY id DESC LIMIT 1",
                        (scan_id,)).fetchone()
    days=min(30,int(profile.get("initial_days",30))) if first else 1
    if not first and last and last["ended"]:
        try:
            elapsed=now()-datetime.fromisoformat(last["ended"])
            days=min(30,max(1,int(elapsed.total_seconds()//86400)+1))
        except (ValueError,TypeError):pass
    added=0;updated=0;skipped=0;errors=[]
    page_client=httpx.AsyncClient(timeout=12,follow_redirects=False)
    async def ingest(job):
        nonlocal added,updated,skipped
        url=job.get("url","")
        if not url.startswith("https://"):skipped+=1;return
        if not role_matches(job,profile) or not location_allowed(job.get("location",""),profile) or not experience_eligible(job,profile):
            skipped+=1;return
        if not valid_until(job.get("valid_through")):skipped+=1;return
        uid=job_id(url)
        with connect() as db:
            existing=db.execute("SELECT id FROM jobs WHERE id=?",(uid,)).fetchone()
        if existing:
            with connect() as db:
                db.execute("UPDATE jobs SET last_seen=?,active=1,closed_at=NULL WHERE id=?",
                           (now().isoformat(),uid))
            updated+=1
            return
        job=await hydrate_posting(page_client,job)
        if job is None:skipped+=1;return
        if not valid_until(job.get("valid_through")):skipped+=1;return
        posted=job.get("posted_at")
        if posted and not posted_recent(posted,days):skipped+=1;return
        result=await evaluate(job,profile,setting("resume_text",""))
        adjustment=feedback_adjustment(job)
        if adjustment:
            result["score"]=max(0,min(100,result["score"]+adjustment))
            result["insight"]+=f" (Past feedback adjustment: {adjustment:+d} points.)"
        verified=posted_recent(posted,days) if posted else False
        with connect() as db:
            cur=db.execute("""INSERT OR IGNORE INTO jobs
              (id,source,title,company,location,description,url,posted_at,first_seen,
               last_seen,verified_at,active,score,insight,missing,model_verified,active_check,source_ref)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (uid,job.get("source","unknown"),job.get("title",""),job.get("company",""),
                job.get("location",""),(job.get("description") or "")[:25000],
                normalize_url(url),posted,now().isoformat(),now().isoformat(),
                now().isoformat() if verified else None,1,result["score"],
                result["insight"],json.dumps(result["missing"]),int(result["model_verified"]),
                job.get("active_check","source_listing_only"),job.get("source_ref")))
            created=cur.rowcount>0
            if created and verified and result["model_verified"] and result["score"]>=int(profile.get("alert_threshold",85)):
                db.execute("INSERT OR IGNORE INTO notifications(job_id,created_at) VALUES(?,?)",
                           (uid,now().isoformat()))
        if created:added+=1
    status="complete"
    diagnostics={"ok":0,"error":0}
    try:
        await collect_sources(ingest,diagnostics)
        if diagnostics["ok"]==0:
            status="error"
            errors.append("All sources failed or are unavailable; initial scan remains pending")
        elif diagnostics["error"]:
            status="partial"
        if diagnostics["ok"] and first:
            set_setting("initial_done",True)
        # Notification sending is a separate retryable queue. Failures never lose jobs.
        if notify:
            with connect() as db:
                pending=db.execute("""SELECT id,job_id,attempts FROM notifications
                     WHERE status='pending' AND attempts<5 ORDER BY id LIMIT 30""").fetchall()
            for item in pending:
                try:
                    sent=await notify(item["job_id"])
                    if sent is not True:
                        # Missing Firebase/device setup must not permanently exhaust retries.
                        with connect() as db:
                            db.execute("UPDATE notifications SET last_error=? WHERE id=?",
                                       ("Firebase or phone device not configured",item["id"]))
                        continue
                    with connect() as db:
                        db.execute("UPDATE notifications SET status='sent',sent_at=?,attempts=attempts+1 WHERE id=?",
                                   (now().isoformat(),item["id"]))
                except Exception as exc:
                    with connect() as db:
                        db.execute("""UPDATE notifications SET attempts=attempts+1,
                            status=CASE WHEN attempts+1>=5 THEN 'failed' ELSE 'pending' END,
                            last_error=? WHERE id=?""",(str(exc)[:300],item["id"]))
    except Exception as exc:
        status="error";errors.append(str(exc)[:500])
    await page_client.aclose()
    with connect() as db:
        db.execute("UPDATE scans SET ended=?,status=?,found=?,error=? WHERE id=?",
                   (now().isoformat(),status,added,"; ".join(errors),scan_id))
    return {"status":status,"new_jobs":added,"seen_again":updated,
            "filtered":skipped,"source_health":diagnostics,"errors":errors,"lookback_days":days}
