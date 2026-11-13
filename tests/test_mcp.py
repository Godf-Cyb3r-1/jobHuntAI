"""Protocol-level MCP regression tests for bundled JobHuntAI tools."""
import io
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_bridge

class EmptyContext:
    def database(self):
        raise AssertionError("Initialization and tools/list must not query user data")

def test_mcp_initialization_and_tool_catalog():
    inp = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}}) + "\n" +
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n" +
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n"
    )
    output = io.StringIO()
    mcp_bridge.serve(EmptyContext(), instream=inp, outstream=output)
    responses = [json.loads(row) for row in output.getvalue().splitlines()]
    assert len(responses) == 2
    assert responses[0]["result"]["serverInfo"]["name"] == "jobhuntai-public-tools"
    names = {x["name"] for x in responses[1]["result"]["tools"]}
    assert names == {"public_jobs", "source_health", "verify_public_board"}
    assert all("password" not in n and "resume" not in n for n in names)

def test_mcp_rejects_unlisted_tools():
    inp = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                  "params": {"name": "arbitrary_execute", "arguments": {"command": "whoami"}}}) + "\n")
    output = io.StringIO()
    mcp_bridge.serve(EmptyContext(), instream=inp, outstream=output)
    response = json.loads(output.getvalue())
    assert response["result"]["isError"] is True
