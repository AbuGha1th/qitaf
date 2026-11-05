@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File setup.ps1
pause
