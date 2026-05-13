@echo off
REM ============================================================
REM  Build codelang installer:  dist\codelang-<ver>-setup.exe
REM
REM  Prereq: Inno Setup 6 (https://jrsoftware.org/isdl.php)
REM          or:  winget install JRSoftware.InnoSetup
REM
REM  Version handling:
REM    build.bat                  -> bump patch (e.g. 0.1.0 -> 0.1.1), then build
REM    build.bat --minor          -> bump minor (0.1.5 -> 0.2.0), then build
REM    build.bat --major          -> bump major (0.2.7 -> 1.0.0), then build
REM    build.bat 1.2.3            -> set explicit version, then build
REM    build.bat --no-bump        -> build current version without bumping
REM ============================================================

cd /d "%~dp0\.."

if /I "%~1"=="--no-bump" (
  echo [0/3] Skipping version bump per --no-bump
) else (
  echo [0/3] Bumping version...
  py tools\bump_version.py %* || (
    echo Failed to bump version.
    exit /b 1
  )
)

echo [1/3] Regenerating wizard images...
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

echo [2/3] Compiling installer with: %ISCC%
"%ISCC%" installer\codelang.iss || exit /b 1

echo [3/3] Done. Installer:
for /f "delims=" %%V in ('py tools\bump_version.py --show') do echo     dist\codelang-%%V-setup.exe
