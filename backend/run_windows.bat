@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 py -3 -m venv .venv
 if errorlevel 1 (
   echo Python 3 is required. Install Python 3.11 or later.
   pause
   exit /b 1
 )
)
if not exist .venv\.jobhunt-deps-ready (
 .venv\Scripts\python.exe -m pip install -r requirements.txt
 if errorlevel 1 (
   echo Dependency installation failed.
   pause
   exit /b 1
 )
 echo installed>.venv\.jobhunt-deps-ready
)
.venv\Scripts\python.exe serve.py
if errorlevel 1 pause
