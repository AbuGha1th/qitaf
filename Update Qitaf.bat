@echo off
rem Gets the latest Qitaf. Your presets, word fixes, videos and lessons are kept.
cd /d "%~dp0"
git pull
.venv\Scripts\pip install -r requirements.txt
call npm install
.venv\Scripts\python.exe -X utf8 check.py
pause
