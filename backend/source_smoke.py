"""Live ATS availability check. Run explicitly; does not touch the user's database."""
import asyncio
import json
from pathlib import Path
import httpx
from app.catalog import ATS
from app.core import fetch_greenhouse,fetch_lever
from app.discovery import fetch_ashby
from app.smartrecruiters import fetch_smartrecruiters
from app.core import role_matches,DEFAULT_PROFILE,posted_recent
from app.pipeline import in_region,hydrate_posting
import xml.etree.ElementTree as ET

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
                count=0;relevant=0;in_india=0;fresh=0;created_fresh=0;samples=[]
                async for job in stream:
                    count+=1
                    title=(job.get("title") or "").lower()
                    if role_matches(job,DEFAULT_PROFILE):
                        relevant+=1
                        if in_region(job.get("location","")):
                            in_india+=1
                            if posted_recent(job.get("created_at"),30):
                                created_fresh+=1
                            if len(samples)<3:
                                enhanced=await hydrate_posting(client,dict(job))
                                postdate=enhanced.get("posted_at") if enhanced else None
                                if posted_recent(postdate,30):fresh+=1
                                samples.append({"title":job.get("title"),
                                                "location":job.get("location"),
                                                "posted_at":postdate,
                                                "created_at":job.get("created_at"),
                                                "page_status":enhanced.get("active_check","unverified") if enhanced else "closed",
                                                "url":job.get("url")})
                item={"feed":kind+":"+name,"status":"ok","total_jobs":count,
                      "potentially_relevant":relevant,"india_role_matches":in_india,
                      "dated_last_30_days":fresh,"created_within_30_days":created_fresh,
                      "samples":samples}
            except Exception as exc:
                item={"feed":kind+":"+name,"status":"error","reason":str(exc)[:250]}
            report.append(item)
            print(json.dumps(item,ensure_ascii=False),flush=True)
        try:
            response=await client.get("https://www.bing.com/search",params={
                "q":'site:jobs.lever.co "application security" India',"format":"rss"})
            response.raise_for_status()
            root=ET.fromstring(response.text)
            if root.tag.lower()!="rss":raise ValueError("Response is not RSS")
            count=len(root.findall(".//item"))
            report.append({"feed":"indexed:bing","status":"ok","indexed_items":count})
        except Exception as exc:
            report.append({"feed":"indexed:bing","status":"error","reason":str(exc)[:250]})
        print(json.dumps(report[-1]),flush=True)
        for name in ("BoschGroup","Visa","NielsenIQ"):
            try:
                response=await client.get("https://api.smartrecruiters.com/v1/companies/"+name+"/postings",
                                          params={"limit":1})
                response.raise_for_status()
                total=response.json().get("totalFound",0)
                report.append({"feed":"smartrecruiters:"+name+":global-count",
                               "status":"ok","totalFound":total})
            except Exception as exc:
                report.append({"feed":"smartrecruiters:"+name+":global-count",
                               "status":"error","reason":str(exc)[:250]})
            print(json.dumps(report[-1]),flush=True)
    path=Path("source-smoke-report.json")
    path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    available=sum(item["status"]=="ok" for item in report)
    print("Sources responding:",available,"of",len(report))
    if available==0:raise SystemExit("No ATS sources reachable")

if __name__=="__main__":
    asyncio.run(main())
