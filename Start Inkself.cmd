@echo off
cd /d "%~dp0"
if not exist ".local\model-env\Scripts\python.exe" (
  echo Please run setup-web.ps1 first. See docs\web-guide.md.
  pause
  exit /b 1
)
".local\model-env\Scripts\python.exe" launch.py
if errorlevel 1 pause
