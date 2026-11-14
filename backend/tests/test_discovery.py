from app.discovery import BUILTIN_FEEDS,allowed_url,parse_job_posting
def test_seeds():
    assert len(BUILTIN_FEEDS)>=10
def test_url_guard():
    assert allowed_url("https://jobs.lever.co/acceldata/abc")
    assert not allowed_url("https://jobs.lever.co.evil.example/abc")
def test_schema():
    content='<script type="application/ld+json">{"@type":"JobPosting","title":"Penetration Tester","datePosted":"2026-11-14","hiringOrganization":{"name":"Test"}}</script>'
    job=parse_job_posting(content,"https://jobs.lever.co/acceldata/abc")
    assert job["title"]=="Penetration Tester"
    assert job["posted_at"]=="2026-11-14"

def test_salary_from_schema():
    from app.discovery import salary_from_schema
    s=salary_from_schema({"baseSalary":{"currency":"INR","value":{
        "minValue":1200000,"maxValue":1800000,"unitText":"YEAR"}}})
    assert "INR" in s and "1200000" in s
