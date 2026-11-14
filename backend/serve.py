"""One-command Windows startup; opt-in automatic OpenCode child startup."""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
import uvicorn

HERE=Path(__file__).resolve().parent
os.chdir(HERE)
def load_env():
    file=HERE/".env"
    if not file.is_file():return
    for line in file.read_text(encoding="utf-8-sig").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:continue
        key,val=line.split("=",1)
        os.environ.setdefault(key.strip(),val.strip().strip('"').strip("'"))
def port_open(host,port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host,port))==0
def start_opencode():
    if os.getenv("JOBHUNT_AUTOSTART_OPENCODE","1")!="1":return
    url=urlparse(os.getenv("JOBHUNT_OPENCODE_URL","http://127.0.0.1:4096"))
    if url.hostname not in ("localhost","127.0.0.1"):return
    port=url.port or 4096
    if port_open("127.0.0.1",port):return
    cli=shutil.which("opencode")
    if not cli:
        print("OpenCode CLI not on PATH; job matching will fall back until started.")
        return
    command=[cli,"serve","--hostname","127.0.0.1","--port",str(port)]
    if os.name=="nt" and cli.lower().endswith((".cmd",".bat")):
        command=["cmd.exe","/c"]+command
    flags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name=="nt" else 0)
    log=open(HERE/"opencode.log","a",encoding="utf-8")
    try:
        subprocess.Popen(command,cwd=HERE,stdin=subprocess.DEVNULL,
                         stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        print("Started OpenCode server in background at port",port)
    except OSError as exc:
        print("Could not start OpenCode:",exc)
    finally:
        log.close()
if __name__=="__main__":
    load_env()
    start_opencode()
    uvicorn.run("app.main:app",host="127.0.0.1",
                port=int(os.getenv("JOBHUNT_PORT","8765")),log_level="info")
