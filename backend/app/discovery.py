"""Preconfigured ATS feeds and best-effort indexed job discovery."""
import json
import re
import html
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from .catalog import DISCOVERY_DOMAINS, SEARCH_TERMS as EXPANDED_TERMS

BUILTIN_FEEDS=[
 {"type":"lever","name":"acceldata"},{"type":"lever","name":"safe"},
 {"type":"lever","name":"gohighlevel"},{"type":"lever","name":"jobgether"},
 {"type":"lever","name":"offchainlabs"},{"type":"lever","name":"finix"},
 {"type":"ashby","name":"atlan"},{"type":"ashby","name":"junipersquare"},
 {"type":"ashby","name":"gainsight"},{"type":"ashby","name":"Vultr"},
 {"type":"ashby","name":"pragmatike"},
]
SEARCH_SITES=[
 "jobs.lever.co","jobs.ashbyhq.com","boards.greenhouse.io",
 "job-boards.greenhouse.io","amazon.jobs","careers.microsoft.com",
 "careers.google.com","jobs.apple.com","careers.ibm.com",
 "careers.accenture.com","careers.tcs.com","careers.infosys.com",
 "careers.wipro.com","careers.cognizant.com","careers.capgemini.com",
 "careers.deloitte.com","careers.ey.com","jobs.pwc.com",
 "careers.kpmg.com","careers.oracle.com","careers.salesforce.com",
 "careers.adobe.com","careers.paypal.com","jobs.intuit.com",
 "www.linkedin.com","in.indeed.com","www.naukri.com",
 "www.foundit.in","www.timesjobs.com","www.shine.com",
 "www.instahyre.com","www.hirist.tech","wellfound.com",
 "cutshort.io",
]
SEARCH_TERMS=['"penetration tester" India','"application security" India',
              '"offensive security" India','"red team" India']
def allowed_url(url):
    try:
        parsed=urlparse(url)
        return (parsed.scheme=="https" and parsed.hostname in DISCOVERY_DOMAINS
                and not parsed.username and not parsed.password)
    except ValueError:
        return False

async def fetch_ashby(client,board):
    response=await client.get("https://api.ashbyhq.com/posting-api/job-board/"+board,params={"includeCompensation":"true"})
    response.raise_for_status()
    for item in response.json().get("jobs",[]):
        if item.get("isListed") is False:continue
        yield {"source":"ashby","title":item.get("title",""),
               "company":board,"location":item.get("location",""),
               "description":item.get("descriptionPlain") or "",
               "url":item.get("jobUrl",""),"posted_at":item.get("publishedAt"),
               "salary":(item.get("compensation") or {}).get("compensationTierSummary")}

def salary_from_schema(job):
    base=job.get("baseSalary")
    if not isinstance(base,dict):return None
    value=base.get("value") or {}
    if not isinstance(value,dict):return None
    currency=base.get("currency") or value.get("currency") or ""
    low=value.get("minValue")
    high=value.get("maxValue")
    number=value.get("value")
    if low is not None and high is not None:
        return str(currency)+" "+str(low)+"–"+str(high)+" "+str(value.get("unitText",""))
    if number is not None:
        return str(currency)+" "+str(number)+" "+str(value.get("unitText",""))
    return None

def parse_job_posting(markup,url):
    soup=BeautifulSoup(markup,"html.parser")
    for script in soup.find_all("script",type="application/ld+json"):
        try: obj=json.loads(script.string or script.get_text())
        except (ValueError,TypeError):continue
        stack=obj if isinstance(obj,list) else [obj]
        while stack:
            item=stack.pop()
            if not isinstance(item,dict):continue
            if isinstance(item.get("@graph"),list):stack.extend(item["@graph"])
            typ=item.get("@type","")
            if "JobPosting" not in (typ if isinstance(typ,list) else [typ]):continue
            loc=item.get("jobLocation") or {}
            if isinstance(loc,list):loc=loc[0] if loc else {}
            address=loc.get("address",{}) if isinstance(loc,dict) else {}
            if not isinstance(address,dict):address={}
            org=item.get("hiringOrganization") or {}
            if not isinstance(org,dict):org={}
            return {"source":"indexed","title":html.unescape(str(item.get("title",""))),
                    "company":org.get("name") or urlparse(url).hostname,
                    "location":", ".join(str(address.get(k)) for k in
                    ("addressLocality","addressRegion","addressCountry") if address.get(k)),
                    "description":BeautifulSoup(item.get("description") or "","html.parser").get_text(" ",strip=True),
                    "url":url,"posted_at":item.get("datePosted"),
                    "valid_through":item.get("validThrough"),
                    "salary":salary_from_schema(item)}
    return None

async def indexed_jobs(client):
    """Public Bing RSS dorks; errors and missing results are normal, not guaranteed coverage."""
    seen=set()
    good_responses=0
    # Rotate a bounded portion of the search matrix each quarter hour;
    # avoid hammering public search providers on every scan.
    from datetime import datetime, timezone
    queries=[(term,site) for site in DISCOVERY_DOMAINS for term in EXPANDED_TERMS]
    batch_size=16
    slot=int(datetime.now(timezone.utc).timestamp()//900)
    start=(slot*batch_size)%len(queries)
    selected=[queries[(start+i)%len(queries)] for i in range(batch_size)]
    for term,site in selected:
        try:
            res=await client.get("https://www.bing.com/search",
                                 params={"q":"site:"+site+" "+term,"format":"rss"})
            res.raise_for_status()
            root=ET.fromstring(res.text)
            if root.tag.lower()!="rss":continue
            good_responses+=1
        except (httpx.HTTPError,ET.ParseError):continue
        for item in root.findall(".//item")[:8]:
            url=(item.findtext("link") or "").strip()
            if not allowed_url(url) or url in seen:continue
            seen.add(url)
            try:
                response=await client.get(url)
                if not allowed_url(str(response.url)):continue
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type",""):continue
                job=parse_job_posting(response.text[:500000],str(response.url))
                if job:yield job
            except (httpx.HTTPError,ValueError):continue
    if good_responses==0:
        raise RuntimeError("Bing RSS discovery unavailable for this scan")
