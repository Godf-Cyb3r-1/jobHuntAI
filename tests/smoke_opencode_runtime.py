"""Windows Actions smoke test: bundled OpenCode v1 local server, no LLM billing.

Requires opencode-v1.exe already downloaded and built JobHuntAI.exe.
"""
import os
import shutil
import tempfile
import time
from pathlib import Path
import sys

base = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(base))
binary = base / "opencode-v1.exe"
if not binary.exists():
    raise RuntimeError("Missing native OpenCode v1 binary for integration test")
shutil.copyfile(binary, base / "opencode.exe")
os.environ["JOBHUNTAI_HOME"] = tempfile.mkdtemp(prefix="jh-oc-runtime-")
os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-ci-not-a-real-key"  # no paid requests
import app
import opencode_engine as oc

reason = oc.launch(app.ROOT, port=43871)
assert reason == "", reason
try:
    for attempt in range(25):
        if oc.ready(app.ROOT, port=43871):
            break
        time.sleep(1)
    assert oc.ready(app.ROOT, port=43871), "Bundled OpenCode v1 server did not become healthy"
    import httpx
    with httpx.Client(auth=("opencode", oc.password(app.ROOT)), timeout=8) as client:
        response = client.post("http://127.0.0.1:43871/session", json={"title": "JobHuntAI v1 server test"})
        assert response.status_code in (200, 201), (response.status_code, response.text[:500])
        assert response.json().get("id"), "Session creation failed"
        mcp_response = client.get("http://127.0.0.1:43871/mcp")
        print("OpenCode MCP status:", mcp_response.status_code, mcp_response.text[:500])
        agent_response = client.get("http://127.0.0.1:43871/agent")
        print("OpenCode agent status:", agent_response.status_code, agent_response.text[:500])
    print("OpenCode v1 server, authenticated health, and session creation verified")
finally:
    if oc._RUNNING is not None:
        oc._RUNNING.terminate()
        oc._RUNNING.wait(timeout=12)
