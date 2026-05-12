@echo off
REM Launch codelang silently — no console window.
REM Logs go to %USERPROFILE%\.codelang\codelang.log
REM Open the log via tray menu "查看日志".

cd /d "%~dp0\.."
start "" pythonw -m desktop.app
exit
