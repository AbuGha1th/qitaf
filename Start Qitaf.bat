@echo off
rem Double-click to start Qitaf. Keep this window open while you use it; close it to stop Qitaf.
cd /d "%~dp0"
echo Qitaf is running at http://localhost:8795
echo Keep this window open while you use it. Close it to stop.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8795"
.venv\Scripts\python.exe -X utf8 server.py >> qitaf.log 2>&1
echo.
echo Qitaf stopped. If you did not close it, ask Claude to read qitaf.log.
pause
