@echo off
REM Alternative pinyin command for codelang. Identical to codelang.cmd.

cd /d "%~dp0\.."
start "" pythonw -m desktop.app
exit /b 0
