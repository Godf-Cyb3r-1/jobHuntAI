"""FCM HTTP v1 sender; server-side credentials only, separate test message support."""
import asyncio
import os
from pathlib import Path
import httpx
from .core import connect

def configured():
    path=os.getenv("JOBHUNT_FCM_TOKEN_FILE")
    return bool(os.getenv("JOBHUNT_FCM_PROJECT") and path and Path(path).is_file())

async def send_notification(title,body,data=None):
    if not configured():return {"status":"not_configured","sent":0,"failed":0}
    with connect() as db:
        devices=[r["token"] for r in db.execute("SELECT token FROM devices")]
    if not devices:return {"status":"no_devices","sent":0,"failed":0}
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    creds=service_account.Credentials.from_service_account_file(
        os.environ["JOBHUNT_FCM_TOKEN_FILE"],
        scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    await asyncio.to_thread(creds.refresh,Request())
    project=os.environ["JOBHUNT_FCM_PROJECT"]
    url=f"https://fcm.googleapis.com/v1/projects/{project}/messages:send"
    sent=0;failed=0;errors=[]
    async with httpx.AsyncClient(timeout=15) as client:
        for token in devices:
            payload={"message":{"token":token,
                "notification":{"title":title[:120],"body":body[:220]},
                "data":{k:str(v) for k,v in (data or {}).items()}}}
            try:
                res=await client.post(url,headers={"Authorization":"Bearer "+creds.token},
                                      json=payload)
                if res.is_success:
                    sent+=1
                else:
                    failed+=1
                    detail=res.text[:300]
                    errors.append(f"{res.status_code}: {detail}")
                    if res.status_code in (400,404) and "UNREGISTERED" in detail:
                        with connect() as db:db.execute("DELETE FROM devices WHERE token=?",(token,))
            except httpx.HTTPError as exc:
                failed+=1;errors.append(str(exc)[:200])
    return {"status":"sent" if sent>0 else "delivery_failed",
            "sent":sent,"failed":failed,"errors":errors[:5]}
