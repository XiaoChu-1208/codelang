@echo off
REM ============================================================
REM  Build codelang installer:  dist\codelang-<ver>-setup.exe
REM
REM  Prereq: Inno Setup 6 (https://jrsoftware.org/isdl.php)
REM          or:  winget install JRSoftware.InnoSetup
REM ============================================================

cd /d "%~dp0\.."

echo [1/2] Regenerating wizard images...
py tools\build_installer_assets.py || (
  echo.
  echo Failed to build wizard assets. Make sure Pillow is installed:
  echo     py -m pip install -r requirements.txt
  exit /b 1
)

REM Locate ISCC.exe
set "ISCC="
for %%P in (
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 5\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
) do (
  if exist %%~P set "ISCC=%%~P"
)
if "%ISCC%"=="" (
  where iscc.exe >nul 2>&1 && for /f "delims=" %%G in ('where iscc.exe') do set "ISCC=%%G"
)

if "%ISCC%"=="" (
  echo.
  echo ISCC.exe not found. Install Inno Setup 6:
  echo     winget install JRSoftware.InnoSetup
  echo Or download:
  echo     https://jrsoftware.org/isdl.php
  exit /b 1
)

echo [2/2] Compiling installer with: %ISCC%
"%ISCC%" installer\codelang.iss || exit /b 1

echo.
echo Done. Installer: dist\codelang-0.1.0-setup.exe
