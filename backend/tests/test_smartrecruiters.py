import asyncio
import httpx
from app.smartrecruiters import fetch_smartrecruiters
def test_smart_recruiters_pagination():
    def handler(request):
        if request.url.path.endswith("/postings"):
            return httpx.Response(200,json={"totalFound":1,"content":[{
              "id":"123","name":"Application Security Engineer","releasedDate":"2026-11-14T12:00:00Z"}]})
        return httpx.Response(200,json={"company":{"name":"Example"},
            "applyUrl":"https://jobs.smartrecruiters.com/Example/123",
            "releasedDate":"2026-11-14T12:00:00Z",
            "location":{"city":"Chennai","country":"IN"},
            "jobAd":{"sections":{"jobDescription":{"text":"<p>Web application pentest</p>"}}}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return [x async for x in fetch_smartrecruiters(client,"Example")]
    jobs=asyncio.run(run())
    assert len(jobs)==1
    assert jobs[0]["posted_at"]=="2026-11-14T12:00:00Z"
    assert "Chennai" in jobs[0]["location"]
