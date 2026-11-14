"""FastAPI authenticated client control and scheduler."""
import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .core import connect, init_db, setting, set_setting, DEFAULT_PROFILE
from .pipeline import scan, migrate
from .resume import suggest_skills
from .catalog import COMPANIES,ATS,DISCOVERY_DOMAINS
from .discovery import BUILTIN_FEEDS, SEARCH_SITES

def api_secret():
    supplied=os.getenv("JOBHUNT_API_KEY","")
    if len(supplied)>=24 and supplied!="replace-with-long-random-value":
        return supplied
    path=Path(os.getenv("JOBHUNT_KEY_FILE",".jobhunt-api-key"))
    if path.exists():
        key=path.read_text(encoding="utf-8").strip()
        if len(key)>=24: return key
    key=secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as handle:
        handle.write(key+"\n")
    try: path.chmod(0o600)
    except OSError: pass
    return key

scheduler=AsyncIOScheduler(timezone="UTC")
lock=asyncio.Lock()
async def authorized(authorization: str|None=Header(default=None)):
    secret=api_secret()
    if not authorization or not secrets.compare_digest(authorization,"Bearer "+secret):
        raise HTTPException(401,"Invalid API token")
async def push(uid):
    project=os.getenv("JOBHUNT_FCM_PROJECT")
    credentials=os.getenv("JOBHUNT_FCM_TOKEN_FILE")
    if not project or not credentials: return False
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        creds=service_account.Credentials.from_service_account_file(
            credentials,scopes=["https://www.googleapis.com/auth/firebase.messaging"])
        await asyncio.to_thread(creds.refresh,Request())
        with connect() as db:
            job=db.execute("SELECT * FROM jobs WHERE id=?",(uid,)).fetchone()
            devices=[r["token"] for r in db.execute("SELECT token FROM devices")]
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            for token in devices:
                res=await client.post(f"https://fcm.googleapis.com/v1/projects/{project}/messages:send",
                   headers={"Authorization":"Bearer "+creds.token},
                   json={"message":{"token":token,
                         "notification":{"title":job["title"]+" · "+job["company"],
                                         "body":str(job["score"])+"% match · "+(job["insight"] or "")[:100]},
                         "data":{"job_id":uid,"url":job["url"]}}})
                res.raise_for_status()
        if not devices:return False
        with connect() as db: db.execute("UPDATE jobs SET notified=1 WHERE id=?",(uid,))
        return True
    except Exception as exc:
        print("Push delivery failed:",str(exc)[:200])
        raise
async def run_scan():
    if lock.locked(): return {"status":"already_running"}
    async with lock: return await scan(push)
@asynccontextmanager
async def lifespan(app):
    init_db()
    migrate()
    print("JobHuntAI device pairing key (private):",api_secret())
    scheduler.add_job(run_scan,"interval",
       minutes=max(1,int(os.getenv("JOBHUNT_SCAN_MINUTES","15"))),
       id="job_scan",max_instances=1,coalesce=True)
    scheduler.start()
    # Kick off the first scan promptly instead of idling for 15 minutes.
    asyncio.create_task(run_scan())
    yield
    scheduler.shutdown(wait=False)
app=FastAPI(title="JobHuntAI",version="0.1.0",lifespan=lifespan)
class Profile(BaseModel):
    roles:list[str]=Field(default_factory=lambda:DEFAULT_PROFILE["roles"])
    locations:list[str]=Field(default_factory=lambda:["India","Remote"])
    skills:list[str]=Field(default_factory=list)
    exclude_roles:list[str]=Field(default_factory=list)
    strict:bool=True
    initial_days:int=Field(default=30,ge=1,le=30)
    alert_threshold:int=Field(default=85,ge=0,le=100)
class Feed(BaseModel):
    type:str
    name:str
class Device(BaseModel):
    token:str=Field(min_length=20,max_length=4096)
@app.get("/health")
def health():
    return {"status":"ok","configured":True}
@app.get("/api/status",dependencies=[Depends(authorized)])
def status():
    with connect() as db:
        total=db.execute("SELECT count(*) n FROM jobs").fetchone()["n"]
        latest=db.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    return {"paused":setting("paused",False),"initial_done":setting("initial_done",False),
            "jobs":total,"scan":dict(latest) if latest else None,
            "opencode_url":os.getenv("JOBHUNT_OPENCODE_URL","http://127.0.0.1:4096")}
@app.get("/api/profile",dependencies=[Depends(authorized)])
def get_profile(): return setting("profile",DEFAULT_PROFILE)
@app.put("/api/profile",dependencies=[Depends(authorized)])
def put_profile(data:Profile):
    profile=data.model_dump(); profile["strict"]=True
    set_setting("profile",profile)
    return profile
@app.get("/api/feeds",dependencies=[Depends(authorized)])
def get_feeds(): return setting("feeds",ATS)
@app.put("/api/feeds",dependencies=[Depends(authorized)])
def put_feeds(feeds:list[Feed]):
    if len(feeds)>500: raise HTTPException(400,"Too many feeds")
    import re
    for feed in feeds:
        if feed.type not in ("lever","greenhouse","ashby") or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",feed.name):
            raise HTTPException(422,"Invalid ATS feed")
    set_setting("feeds",[f.model_dump() for f in feeds]); return {"count":len(feeds)}
@app.get("/api/sources",dependencies=[Depends(authorized)])
def source_status():
    with connect() as db:
        health=[dict(x) for x in db.execute("SELECT * FROM source_health ORDER BY checked_at DESC")]
    return {"feeds":setting("feeds",ATS),"search_domains":DISCOVERY_DOMAINS,
            "catalog_size":len(COMPANIES),"source_health":health,
            "search_enabled":setting("search_enabled",True)}
@app.post("/api/feeds/reset",dependencies=[Depends(authorized)])
def reset_feeds():
    set_setting("feeds",ATS)
    return {"count":len(ATS)}
@app.get("/api/companies",dependencies=[Depends(authorized)])
def companies():
    return [{"name":c.name,"tier":c.tier,"domain":c.domain}
            for c in COMPANIES]
@app.get("/api/resume/suggestions",dependencies=[Depends(authorized)])
def resume_suggestions():
    text=setting("resume_text","")
    confirmed=setting("profile",DEFAULT_PROFILE).get("skills",[])
    return {"suggested":suggest_skills(text),"confirmed":confirmed,
            "note":"Suggestions are not asserted as experience until manually confirmed"}
class Feedback(BaseModel):
    value:str
    reason:str=""
@app.post("/api/jobs/{uid}/feedback",dependencies=[Depends(authorized)])
def feedback(uid:str,data:Feedback):
    if data.value not in ("relevant","irrelevant","dismiss","applied","interviewing"):
        raise HTTPException(422,"Invalid feedback")
    from .core import now
    with connect() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=?",(uid,)).fetchone():
            raise HTTPException(404,"Job not found")
        db.execute("INSERT INTO feedback(job_id,value,reason,created) VALUES(?,?,?,?)",
                   (uid,data.value,data.reason[:500],now().isoformat()))
        if data.value in ("dismiss","irrelevant"):
            db.execute("UPDATE jobs SET dismissed=1 WHERE id=?",(uid,))
        elif data.value=="relevant":
            db.execute("UPDATE jobs SET dismissed=0 WHERE id=?",(uid,))
    return {"status":"saved"}
@app.get("/api/scan/history",dependencies=[Depends(authorized)])
def scan_history(limit:int=25):
    with connect() as db:
        return [dict(x) for x in db.execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?",
                                          (max(1,min(limit,100)),))]
@app.get("/api/alerts",dependencies=[Depends(authorized)])
def alerts():
    with connect() as db:
        return [dict(x) for x in db.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 50")]
@app.get("/api/jobs",dependencies=[Depends(authorized)])
def jobs(min_score:int=0,limit:int=100,include_dismissed:bool=False):
    with connect() as db:
        items=db.execute("SELECT id,source,title,company,location,url,posted_at,first_seen,"
          "verified_at,active,score,insight,missing,saved,model_verified,dismissed FROM jobs WHERE score>=? AND (dismissed=0 OR ?=1) "
          "ORDER BY first_seen DESC LIMIT ?",(min_score,int(include_dismissed),min(max(limit,1),500))).fetchall()
    return [dict(row) for row in items]
@app.post("/api/jobs/{uid}/save",dependencies=[Depends(authorized)])
def save(uid:str):
    with connect() as db:
        res=db.execute("UPDATE jobs SET saved=1 WHERE id=?",(uid,))
        if not res.rowcount: raise HTTPException(404,"Not found")
    return {"saved":True}
@app.post("/api/scan",dependencies=[Depends(authorized)])
async def trigger_scan(): return await run_scan()
@app.post("/api/pause",dependencies=[Depends(authorized)])
def pause(): set_setting("paused",True); return {"paused":True}
@app.post("/api/resume",dependencies=[Depends(authorized)])
async def resume(): set_setting("paused",False); return {"paused":False}
@app.post("/api/device",dependencies=[Depends(authorized)])
def register(device:Device):
    from .core import now
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO devices(token,created) VALUES (?,?)",
                   (device.token,now().isoformat()))
    return {"registered":True}
@app.post("/api/resume/upload",dependencies=[Depends(authorized)])
async def upload_resume(file:UploadFile=File(...)):
    name=(file.filename or "").lower()
    if not name.endswith((".pdf",".docx")): raise HTTPException(415,"PDF or DOCX only")
    raw=await file.read(3_000_001)
    if len(raw)>3_000_000: raise HTTPException(413,"Max 3 MB")
    from io import BytesIO
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader=PdfReader(BytesIO(raw)); text="\n".join(p.extract_text() or "" for p in reader.pages[:12])
        else:
            from docx import Document
            text="\n".join(p.text for p in Document(BytesIO(raw)).paragraphs)
    except Exception: raise HTTPException(422,"Cannot parse file")
    if not text.strip(): raise HTTPException(422,"No extractable text")
    # Resume text stored locally; explicit profile skills remain user verified.
    set_setting("resume_text",text[:30000])
    return {"parsed_characters":min(len(text),30000),
            "suggested_skills":suggest_skills(text),
            "note":"Confirm actual skills in profile before matching"}
