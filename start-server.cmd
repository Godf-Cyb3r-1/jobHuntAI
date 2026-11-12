@echo off
set "JOBHUNTAI_HOME=C:\ProgramData\JobHuntAI"
if exist "C:\ProgramData\JobHuntAI\secrets.cmd" call "C:\ProgramData\JobHuntAI\secrets.cmd"
cd /d "C:\Program Files\JobHuntAI"
"C:\Program Files\JobHuntAI\JobHuntAI.exe" serve --host 127.0.0.1 --port 8000 >>"C:\ProgramData\JobHuntAI\stdout.log" 2>&1