"""Public SmartRecruiters postings (active published jobs), no user key needed."""
import re
from bs4 import BeautifulSoup
from .core import ROLE_TERMS

async def fetch_smartrecruiters(client, company):
    base="https://api.smartrecruiters.com/v1/companies/"+company+"/postings"
    for offset in range(0,500,100):
        response=await client.get(base,params={"limit":100,"offset":offset,"country":"IN"})
        response.raise_for_status()
        data=response.json()
        items=data.get("content",[])
        for item in items:
            title=item.get("name","")
            if not any(term in title.lower() for term in ROLE_TERMS):
                continue
            posting_id=str(item.get("id",""))
            if not re.fullmatch(r"[A-Za-z0-9-]{1,100}",posting_id):continue
            detail=await client.get(base+"/"+posting_id)
            detail.raise_for_status()
            j=detail.json()
            loc=j.get("location") or item.get("location") or {}
            parts=[loc.get("city"),loc.get("region"),loc.get("country")]
            location=", ".join(str(x) for x in parts if x)
            sections=(j.get("jobAd") or {}).get("sections") or {}
            description=" ".join(BeautifulSoup((v or {}).get("text",""),"html.parser").get_text(" ",strip=True)
                                 for v in sections.values() if isinstance(v,dict))
            apply_url=j.get("applyUrl")
            if not isinstance(apply_url,str) or not apply_url.startswith("https://"):
                continue
            yield {"source":"smartrecruiters","title":title,
                "company":(j.get("company") or {}).get("name",company),
                "location":location or "India",
                "description":description,
                "url":apply_url,
                "posted_at":j.get("releasedDate") or item.get("releasedDate"),
                "active_check":"published_ats_feed"}
        if offset+len(items)>=data.get("totalFound",0) or not items:break
