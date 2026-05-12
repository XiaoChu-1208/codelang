@echo off
REM Debug launch — keeps the console window open so you can watch the live log.
REM Use this only when investigating an issue; for normal use run.bat is silent.

cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
py -m desktop.app
pause
