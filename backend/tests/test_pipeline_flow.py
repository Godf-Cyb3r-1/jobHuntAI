"""End-to-end scanner test with deterministic local collectors/models, no real credentials."""
import asyncio
from app.core import init_db,connect,now,set_setting
import app.pipeline as pipeline

def test_complete_scan_and_alert(tmp_path,monkeypatch):
    import app.core as core
    monkeypatch.setattr(core,"DB",str(tmp_path/"state.sqlite"))
    init_db();pipeline.migrate()
    set_setting("profile",{"roles":["Penetration Tester"],"skills":["Burp Suite"],
         "locations":["India"],"initial_days":30,"alert_threshold":85,"strict":True})
    async def collect(process,stats):
        await process({"source":"test","source_ref":"test:test",
            "title":"Penetration Tester","company":"Example",
            "description":"Burp Suite, web penetration testing",
            "location":"Chennai, India","posted_at":now().isoformat(),
            "url":"https://jobs.lever.co/example/abc"})
        stats["ok"]+=1
    async def hydrate(client,job):return job
    async def evaluate(job,profile,resume):
        return {"score":91,"insight":"Matches Burp Suite.","missing":[],
                "model_verified":True}
    async def notify(uid):return True
    monkeypatch.setattr(pipeline,"collect_sources",collect)
    monkeypatch.setattr(pipeline,"hydrate_posting",hydrate)
    monkeypatch.setattr(pipeline,"evaluate",evaluate)
    result=asyncio.run(pipeline.scan(notify))
    assert result["status"]=="complete"
    assert result["new_jobs"]==1
    assert result["lookback_days"]==30
    with connect() as db:
        item=db.execute("SELECT * FROM jobs").fetchone()
        assert item["score"]==91
        assert item["active"]==1
        assert db.execute("SELECT status FROM notifications").fetchone()["status"]=="sent"
    duplicate=asyncio.run(pipeline.scan(notify))
    assert duplicate["new_jobs"]==0
    assert duplicate["seen_again"]==1

def test_closure_after_confirmed_source(tmp_path,monkeypatch):
    import app.core as core
    monkeypatch.setattr(core,"DB",str(tmp_path/"state.sqlite"))
    init_db();pipeline.migrate()
    with connect() as db:
        db.execute("""INSERT INTO jobs(id,source,source_ref,title,company,url,first_seen,active)
            VALUES('a','lever','lever:example','Penetration Tester','Example',
            'https://jobs.lever.co/example/a','2026-11-14',1)""")
    pipeline.close_missing("lever:example",set())
    with connect() as db:
        assert db.execute("SELECT active FROM jobs WHERE id='a'").fetchone()["active"]==0

def test_missing_push_config_does_not_consume_retries(tmp_path,monkeypatch):
    import app.core as core
    monkeypatch.setattr(core,"DB",str(tmp_path/"state.sqlite"))
    init_db();pipeline.migrate()
    with connect() as db:
        db.execute("""INSERT INTO jobs(id,source,title,company,url,first_seen)
            VALUES('a','test','Penetration Tester','Example','https://jobs.lever.co/x/a','2026-11-14')""")
        db.execute("INSERT INTO notifications(job_id,created_at) VALUES('a','2026-11-14')")
    async def empty(process,stats):stats["ok"]+=1
    async def no_push(uid):return False
    monkeypatch.setattr(pipeline,"collect_sources",empty)
    asyncio.run(pipeline.scan(no_push))
    with connect() as db:
        x=db.execute("SELECT attempts,status FROM notifications").fetchone()
        assert x["attempts"]==0 and x["status"]=="pending"
