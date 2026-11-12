import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock
import os
import tempfile

os.environ['JOBHUNTAI_HOME'] = tempfile.mkdtemp(prefix='jh-test-')
spec = importlib.util.spec_from_file_location('jh', Path(__file__).resolve().parents[1] / 'app.py')
jh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jh)


def user(**kw):
    return dict({'role': 'appsec,pentest', 'freshness': 3, 'skills': 'Burp Suite,OWASP', 'locations': ''}, **kw)


def job(**kw):
    return dict({'title': 'Web Application Penetration Tester', 'description': 'Burp Suite', 'published': jh.iso(), 'active': 1, 'location': 'India'}, **kw)


def test_strict_role_matching():
    assert jh.match_job(user(), job()) is not None
    assert jh.match_job(user(), job(title='SOC Analyst')) is None
    assert jh.match_job(user(), job(title='IAM Engineer')) is None
    assert jh.match_job(user(role='appsec'), job(title='Penetration Tester')) is None


def test_freshness_and_provenance():
    assert jh.match_job(user(), job(published=None)) is None
    assert jh.match_job(user(), job(published=(jh.utcnow() - timedelta(days=4)).isoformat())) is None
    assert jh.match_job(user(), job(active=0)) is None
    assert jh.match_job(user(locations='Chennai'), job(location='Hyderabad')) is None


def test_password_and_date():
    secret = jh.password_hash('super_secret_password')
    assert jh.password_valid('super_secret_password', secret)
    assert not jh.password_valid('different-password', secret)
    assert jh.normalize_date(1732000000000).endswith('+00:00')
    assert jh.normalize_date('bad date') is None


def test_feed_parsers():
    client = Mock()
    resp = Mock()
    resp.json.return_value = {'jobs':[{'id':'1','title':'Application Security Engineer','jobUrl':'https://example.com/1','publishedAt':'2026-11-12T12:00:00Z'}]}
    client.get.return_value = resp
    assert jh.fetch_source(client, {'kind':'ashby','slug':'company'})[0]['published']
    resp.json.return_value = {'jobs':[{'id': 12,'title':'Penetration Tester','absolute_url':'https://example.com/12','updated_at':'2026-11-12T12:00:00Z'}]}
    assert jh.fetch_source(client, {'kind':'greenhouse','slug':'company'})[0]['published'] is None


def test_isolation_of_profile_data():
    with jh.database() as db:
        db.execute("INSERT INTO users(email,pwd,name,role) VALUES('a@example.com','hash','A','appsec')")
        db.execute("INSERT INTO users(email,pwd,name,role) VALUES('b@example.com','hash','B','pentest')")
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 2