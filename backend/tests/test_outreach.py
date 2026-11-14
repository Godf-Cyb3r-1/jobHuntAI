from app.outreach import template
from app.resume import suggest_roles
def test_outreach_never_fabricates():
    draft=template({"title":"Penetration Tester","company":"Example"},{"skills":[]})
    assert not draft["ai_generated"]
    assert "[Please insert" in draft["body"]
    assert "Example" in draft["subject"]
def test_role_suggestions():
    assert "Application Security Engineer" in suggest_roles("Worked on application security and OWASP testing")
