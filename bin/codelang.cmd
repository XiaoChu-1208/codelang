@echo off
REM codelang CLI launcher. After running install.bat once, this file's
REM directory is on your PATH, so typing "codelang" in any CMD/PowerShell
REM window starts the app silently (no visible console).
REM
REM Logs go to %USERPROFILE%\.codelang\codelang.log (open via tray menu).

cd /d "%~dp0\.."
start "" pythonw -m desktop.app
exit /b 0
