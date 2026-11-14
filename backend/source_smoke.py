"""Live ATS availability check. Run explicitly; does not touch the user's database."""
import asyncio
import json
from pathlib import Path
import httpx
from app.catalog import ATS
from app.core import fetch_greenhouse,fetch_lever
from app.discovery import fetch_ashby
from app.smartrecruiters import fetch_smartrecruiters

async def main():
    report=[]
    async with httpx.AsyncClient(timeout=16,follow_redirects=False,
                                  headers={"User-Agent":"JobHuntAI/0.2 validation"}) as client:
        for feed in ATS:
            kind,name=feed["type"],feed["name"]
            try:
                if kind=="lever":stream=fetch_lever(client,name)
                elif kind=="greenhouse":stream=fetch_greenhouse(client,name)
                elif kind=="ashby":stream=fetch_ashby(client,name)
                elif kind=="smartrecruiters":stream=fetch_smartrecruiters(client,name)
                else:continue
                count=0;relevant=0
                async for job in stream:
                    count+=1
                    title=(job.get("title") or "").lower()
                    if any(word in title for word in ("penetration","appsec","application security",
                                                     "red team","offensive security")):
                        relevant+=1
                item={"feed":kind+":"+name,"status":"ok","total_jobs":count,
                      "potentially_relevant":relevant}
            except Exception as exc:
                item={"feed":kind+":"+name,"status":"error","reason":str(exc)[:250]}
            report.append(item)
            print(json.dumps(item,ensure_ascii=False),flush=True)
    path=Path("source-smoke-report.json")
    path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    available=sum(item["status"]=="ok" for item in report)
    print("Sources responding:",available,"of",len(report))
    if available==0:raise SystemExit("No ATS sources reachable")

if __name__=="__main__":
    asyncio.run(main())
