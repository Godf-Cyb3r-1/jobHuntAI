"""Read-only Model Context Protocol stdio server for OpenCode v1 workers.

Tools intentionally expose public vacancy/source evidence only. No resumes,
user identities, secrets, applications, or unrestricted shell/web functions.
"""
from __future__ import annotations
import json
import re
import sys
from urllib.parse import urlparse

TOOLS = [
    {"name": "public_jobs", "description": "Search already collected public vacancies by title/company. Never returns user data.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query"]}},
    {"name": "source_health", "description": "Show health of registered publicly readable ATS company boards.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "verify_public_board", "description": "Verify a public Ashby, Greenhouse or Lever board slug through its official job feed, without registering or bypassing restrictions.",
     "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["ashby", "greenhouse", "lever"]}, "slug": {"type": "string"}}, "required": ["kind", "slug"]}}
]

def invoke(ctx, name, args):
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object")
    if name == "public_jobs":
        query = str(args.get("query", "")).strip()
        if not query or len(query) > 150:
            raise ValueError("Search query missing or too long")
        limit = min(20, max(1, int(args.get("limit", 8))))
        with ctx.database() as db:
            rows = db.execute("""SELECT company,title,location,url,published,date_evidence,active,last_seen
               FROM jobs WHERE (title LIKE ? OR company LIKE ?) ORDER BY published DESC LIMIT ?""",
               ("%" + query.replace("%", "") + "%", "%" + query.replace("%", "") + "%", limit)).fetchall()
        return {"jobs": [dict(r) for r in rows], "note": "Cached source evidence only. Check the employer's original application link."}
    if name == "source_health":
        with ctx.database() as db:
            rows = db.execute("""SELECT kind,slug,company,success,last_success,last_error
                                   FROM sources ORDER BY company LIMIT 100""").fetchall()
        return {"sources": [dict(r) for r in rows]}
    if name == "verify_public_board":
        kind = str(args.get("kind", ""))
        slug = str(args.get("slug", ""))
        if kind not in ("ashby", "greenhouse", "lever") or not re.fullmatch(r"[A-Za-z0-9_-]{2,80}", slug):
            raise ValueError("Unapproved ATS provider or slug")
        import httpx
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            listings = ctx.fetch_source(client, {"kind": kind, "slug": slug})
        return {"kind": kind, "slug": slug, "reachable": True,
                "published_count": len(listings), "sample_titles": [x["title"] for x in listings[:5]]}
    raise ValueError("Unknown tool name")

def serve(ctx, instream=None, outstream=None):
    instream = instream or sys.stdin
    outstream = outstream or sys.stdout
    # MCP stdio uses newline-delimited JSON-RPC 2.0 messages.
    for line in instream:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            rid = request.get("id")
            method = request.get("method")
            if rid is None:
                continue  # notifications do not get responses
            if method == "initialize":
                result = {"protocolVersion": "2025-03-26",
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "jobhuntai-public-tools", "version": "0.2.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request.get("params") or {}
                try:
                    result_data = invoke(ctx, params.get("name"), params.get("arguments") or {})
                    result = {"content": [{"type": "text", "text": json.dumps(result_data, ensure_ascii=False)}]}
                except Exception as error:
                    result = {"content": [{"type": "text", "text": str(error)[:300]}], "isError": True}
            else:
                raise ValueError("Method not found")
            response = {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as exc:
            if "rid" not in locals() or rid is None:
                continue
            response = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)[:250]}}
        outstream.write(json.dumps(response, ensure_ascii=False) + "\n")
        outstream.flush()
