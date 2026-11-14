import asyncio
from app.fcm import send_notification,configured
def test_fcm_missing_credentials(monkeypatch):
    monkeypatch.delenv("JOBHUNT_FCM_PROJECT",raising=False)
    monkeypatch.delenv("JOBHUNT_FCM_TOKEN_FILE",raising=False)
    assert not configured()
    result=asyncio.run(send_notification("JobHuntAI test","Test"))
    assert result["status"]=="not_configured" and result["sent"]==0
