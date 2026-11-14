@echo off
cd /d "%~dp0"
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt
if not exist .env (
 echo Copy .env.example to .env and configure JOBHUNT_API_KEY
 pause
 exit /b 1
)
for /f "usebackq tokens=1,* delims==" %%A in (".env") do if not "%%A"=="" set "%%A=%%B"
uvicorn app.main:app --host 127.0.0.1 --port 8765
