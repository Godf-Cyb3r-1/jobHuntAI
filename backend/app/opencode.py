"""OpenCode model discovery and conservative job evaluation with retries."""
import asyncio
import json
import os
import re
import httpx
from .resume import suggest_skills

def models_from_provider(payload):
    """Only models advertised as free and available; keep user-selected model first."""
    provider_list=payload.get("all",[]) if isinstance(payload,dict) else []
    connected=set(payload.get("connected",[])) if isinstance(payload,dict) else set()
    found=[]
    for p in provider_list:
        if not isinstance(p,dict):continue
        pid=p.get("id")
        if connected and pid not in connected:continue
        for mid,m in (p.get("models") or {}).items():
            cost=m.get("cost",{}) if isinstance(m,dict) else {}
            free=(isinstance(cost,dict) and cost.get("input")==0 and cost.get("output")==0)
            if free or mid.endswith("-free"):
                found.append({"providerID":pid,"modelID":mid})
    return found

def parse_model_json(parts):
    text="\n".join(p.get("text","") for p in parts if isinstance(p,dict) and p.get("type")=="text")
    # Strip code fences and parse first valid JSON object.
    decoder=json.JSONDecoder()
    for start in (m.start() for m in re.finditer(r"\{",text)):
        try:
            output,_=decoder.raw_decode(text[start:])
            if not isinstance(output,dict):continue
            score=output.get("score")
            if isinstance(score,bool) or not isinstance(score,(int,float)):continue
            if not 0<=score<=100:continue
            missing=output.get("missing",[])
            if not isinstance(missing,list):missing=[]
            return {"score":round(score),"insight":str(output.get("insight",""))[:500],
                    "missing":[str(x)[:100] for x in missing[:12]],
                    "model_verified":True}
        except (ValueError,TypeError):continue
    return None

async def evaluate(job, profile, resume_text=""):
    skills=[x for x in profile.get("skills",[]) if isinstance(x,str)]
    doc=(job.get("title","")+" "+job.get("description","")).lower()
    matched=[s for s in skills if s.lower() in doc]
    # User-verified skills only. Never automatically claim extracted text is verified.
    fallback={"score":round(30+min(45,45*len(matched)/max(len(skills),1))) if skills else 0,
        "insight":"AI unavailable; preliminary keyword overlap only: "+(", ".join(matched) or "not enough verified skills"),
        "missing":[],"model_verified":False}
    endpoint=os.getenv("JOBHUNT_OPENCODE_URL","http://127.0.0.1:4096").rstrip("/")
    auth=("opencode",os.environ["JOBHUNT_OPENCODE_PASSWORD"]) if os.getenv("JOBHUNT_OPENCODE_PASSWORD") else None
    prompt=(
        "You are scoring Indian cybersecurity job relevance. Evaluate only the supplied, verified "
        "skills and resume evidence. Do not invent any experience. Roles outside offensive security, "
        "application security or penetration testing must score 0. Missing requirements must be based "
        "on the job text. Avoid claiming a 100% match. Respond exclusively as JSON with keys "
        "score (integer 0-100), insight (two concise factual sentences), missing (string array).\n"
        +json.dumps({"profile":profile,"resume":resume_text[:11000],
                     "job":{k:job.get(k) for k in ("title","company","location","description")}},ensure_ascii=False)[:22000])
    payload={"parts":[{"type":"text","text":prompt}]}
    try:
        async with httpx.AsyncClient(timeout=50,auth=auth) as client:
            explicit=os.getenv("JOBHUNT_OPENCODE_MODEL","").strip()
            candidates=[]
            if explicit and "/" in explicit:
                provider,model=explicit.split("/",1)
                candidates.append({"providerID":provider,"modelID":model})
            try:
                resp=await client.get(endpoint+"/provider",timeout=7)
                if resp.is_success:
                    candidates.extend(models_from_provider(resp.json()))
            except (httpx.HTTPError,ValueError):pass
            # A configured OpenCode default still works without model selection.
            candidates.append(None)
            unique=[]; seen=set()
            for model in candidates:
                key=json.dumps(model,sort_keys=True)
                if key not in seen:
                    unique.append(model);seen.add(key)
            session=await client.post(endpoint+"/session",json={})
            session.raise_for_status()
            sid=session.json()["id"]
            for model in unique[:5]:
                body=dict(payload)
                if model:body["model"]=model
                try:
                    answer=await client.post(endpoint+"/session/"+sid+"/message",json=body)
                    if answer.status_code in (429,500,502,503,504):continue
                    answer.raise_for_status()
                    parsed=parse_model_json(answer.json().get("parts",[]))
                    if parsed:return parsed
                except (httpx.HTTPError,ValueError,TypeError):continue
    except (httpx.HTTPError,ValueError,TypeError,KeyError):
        pass
    return fallback
