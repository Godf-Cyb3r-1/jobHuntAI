"""Draft only: no automated sending, and never fabricate resume experience."""
import json
import os
import httpx
from .opencode import models_from_provider

def template(job,profile):
    roles=profile.get("roles",[])
    skills=[str(x) for x in profile.get("skills",[]) if isinstance(x,str)]
    title=job.get("title","the advertised position")
    company=job.get("company","your organization")
    skill_line=("I have worked with "+", ".join(skills[:4])+", which I believe may be relevant to the role."
                if skills else "[Please insert a short, accurate summary of your relevant experience.]")
    return {"subject":"Interest in "+title+" — "+company,
        "body":"Hello Hiring Team,\\n\\n"
        +"I came across the "+title+" opening at "+company+" and wanted to express my interest. "
        +skill_line+"\\n\\n"
        +"I would welcome the opportunity to discuss how my background fits your team's requirements. "
        +"I can share my resume and further details if helpful.\\n\\n"
        +"Regards,\\n[Your name]",
        "ai_generated":False}

async def draft(job,profile,resume):
    fallback=template(job,profile)
    url=os.getenv("JOBHUNT_OPENCODE_URL","http://127.0.0.1:4096").rstrip("/")
    auth=("opencode",os.environ["JOBHUNT_OPENCODE_PASSWORD"]) if os.getenv("JOBHUNT_OPENCODE_PASSWORD") else None
    prompt=("Draft a concise, natural cold application email from an Indian working professional. "
        "No exaggeration, flattery, invented experience, fabricated employers or certifications. "
        "Do not claim familiarity with any tools unless confirmed in the resume or verified skills. "
        "Return only JSON with subject and body; include placeholders for unknown name/contact. "
        "Keep the email around 100-140 words. Do not automatically send it.\\n"+
        json.dumps({"job":job,"profile":profile,"resume":resume[:10000]},ensure_ascii=False)[:18000])
    try:
        async with httpx.AsyncClient(timeout=45,auth=auth) as client:
            res=await client.post(url+"/session",json={});res.raise_for_status()
            sid=res.json()["id"]
            msg=await client.post(url+"/session/"+sid+"/message",json={"parts":[{"type":"text","text":prompt}]})
            msg.raise_for_status()
            text=" ".join(p.get("text","") for p in msg.json().get("parts",[]) if p.get("type")=="text")
            import re
            match=re.search(r"\{[\s\S]*\}",text)
            data=json.loads(match.group()) if match else {}
            subject=data.get("subject","")
            body=data.get("body","")
            if isinstance(subject,str) and isinstance(body,str) and 15<=len(body)<=2500:
                return {"subject":subject[:180],"body":body,"ai_generated":True}
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        pass
    return fallback
