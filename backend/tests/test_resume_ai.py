import asyncio
from app.resume_ai import analyze,ALLOWED_ROLES
def test_resume_fallback_without_text():
    result=asyncio.run(analyze(""))
    assert not result["ai_generated"]
    assert result["suggested_skills"]==[]
    assert "Penetration Tester" in ALLOWED_ROLES
