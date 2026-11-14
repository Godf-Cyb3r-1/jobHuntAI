from app.main import api_secret
def test_pairing_key_is_stable(monkeypatch,tmp_path):
    monkeypatch.delenv("JOBHUNT_API_KEY",raising=False)
    monkeypatch.setenv("JOBHUNT_KEY_FILE",str(tmp_path/"pair"))
    first=api_secret()
    assert len(first)>=24
    assert first==api_secret()
    assert first==(tmp_path/"pair").read_text().strip()
