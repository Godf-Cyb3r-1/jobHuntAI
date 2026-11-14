from datetime import timedelta
from app.core import job_id, normalize_url, role_matches, posted_recent, now, DEFAULT_PROFILE

def test_role_strict():
    assert role_matches({"title":"Senior Penetration Tester"},DEFAULT_PROFILE)
    assert not role_matches({"title":"SOC Analyst - penetration testing experience"},DEFAULT_PROFILE)
    assert not role_matches({"title":"IAM Analyst"},DEFAULT_PROFILE)
def test_url_dedup():
    assert job_id("https://example.com/jobs/1?utm_source=xx")==job_id("https://example.com/jobs/1")
def test_freshness():
    assert posted_recent(now().isoformat(),30)
    assert not posted_recent((now()-timedelta(days=31)).isoformat(),30)
    assert not posted_recent(None,30)

import asyncio
import httpx
from app.core import fetch_lever
def test_lever_created_at_is_not_published_at():
    def handle(request):
        return httpx.Response(200,json=[{"text":"Penetration Tester",
            "hostedUrl":"https://jobs.lever.co/example/123",
            "createdAt":1794652800000,
            "categories":{"location":"Chennai, India"}}])
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return [item async for item in fetch_lever(client,"example")]
    job=asyncio.run(run())[0]
    assert job["posted_at"] is None
    assert job["created_at"] is not None

def test_only_selected_role_family_matches():
    profile={"roles":["Penetration Tester"],"strict":True}
    assert role_matches({"title":"Senior Pentest Consultant"},profile)
    assert not role_matches({"title":"Product Security Engineer"},profile)
    assert not role_matches({"title":"Security Researcher"},profile)
    profile["roles"]=["Application Security Engineer"]
    assert role_matches({"title":"AppSec Engineer"},profile)
    assert not role_matches({"title":"Red Team Operator"},profile)
