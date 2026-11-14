import asyncio
from app.opencode import evaluate
from app.main import app
from fastapi.testclient import TestClient
import httpx
def test_fallback_is_visible(monkeypatch):
    monkeypatch.setenv("JOBHUNT_OPENCODE_URL","http://127.0.0.1:1")
    item={"title":"Penetration Tester","description":"Burp Suite"}
    profile={"roles":["Penetration Tester"],"skills":["Burp Suite"],"strict":True}
    result=asyncio.run(evaluate(item,profile))
    assert not result["model_verified"]
def test_diagnostics_response_shape():
    from app.opencode import record_ai,LAST_AI_DIAGNOSTIC
    assert record_ai("test","synthetic error")["status"]=="test"
