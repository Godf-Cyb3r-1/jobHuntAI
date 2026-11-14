from app.resume import suggest_skills
from app.opencode import parse_model_json,models_from_provider
def test_skill_suggestions():
    skills=suggest_skills("Experienced using Burp Suite, OWASP Top 10 and Python.")
    assert "Burp Suite" in skills and "Python" in skills
    assert "AWS" not in skills
def test_model_json():
    result=parse_model_json([{"type":"text","text":'Here: {"score":88,"insight":"Relevant.","missing":["AWS"]}'}])
    assert result["score"]==88 and result["model_verified"]
    assert parse_model_json([{"type":"text","text":'{"score":200}'}]) is None
def test_free_selection():
    data={"all":[{"id":"opencode","models":{"free-x":{"cost":{"input":0,"output":0}},
             "paid":{"cost":{"input":1,"output":2}}}}],"connected":["opencode"]}
    assert models_from_provider(data)==[{"providerID":"opencode","modelID":"free-x"}]
