from fastapi.testclient import TestClient
from app.main import app,api_secret
from app.core import init_db
from app.pipeline import migrate

def test_api_access(tmp_path,monkeypatch):
    import app.core as core
    monkeypatch.setattr(core,"DB",str(tmp_path/"db.sqlite"))
    monkeypatch.setenv("JOBHUNT_KEY_FILE",str(tmp_path/"key"))
    init_db();migrate()
    client=TestClient(app)
    assert client.get("/health").status_code==200
    assert client.get("/api/status").status_code==401
    hdr={"Authorization":"Bearer "+api_secret()}
    assert client.get("/api/status",headers=hdr).status_code==200
    assert client.get("/api/companies",headers=hdr).json()
    assert client.get("/api/sources",headers=hdr).json()["catalog_size"]>=60
    assert client.get("/api/resume/suggestions",headers=hdr).status_code==200
    assert client.get("/api/scan/history",headers=hdr).status_code==200
