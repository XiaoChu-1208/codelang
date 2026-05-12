@echo off
REM Launch codelang desktop app. Double-click to start.
REM A console window stays open showing logs; close it to stop the app.

cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
py -m desktop.app
pause
