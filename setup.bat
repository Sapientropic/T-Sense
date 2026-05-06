@echo off
REM Install tg-channel-scanner dependencies (Windows)
REM Requires: Python 3.12+

cd /d "%~dp0"

echo === TG Channel Scanner Setup ===

REM Check Python version (require 3.12+)
python --version 2>nul || (
    echo Error: Python not found. Install from https://python.org
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do set PYMAJOR=%%a& set PYMINOR=%%b

if %PYMAJOR% lss 3 (
    echo Error: Python 3.12+ required. Found %PYVER%. Install from https://python.org
    exit /b 1
)
if %PYMAJOR% equ 3 if %PYMINOR% lss 12 (
    echo Error: Python 3.12+ required. Found %PYVER%. Install from https://python.org
    exit /b 1
)

echo Found Python %PYVER%

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing pinned core dependencies...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo Installing optional pinned LLM dependencies (openai for summarize.py)...
pip install -r requirements-llm.txt --quiet 2>nul || echo   ^(openai not installed - summarize.py will need it later^)

set EXPECTED_TG_VERSION=0.9.0
set TG_VERSION=
for /f "delims=" %%v in ('tg --version 2^>nul') do set TG_VERSION=%%v
if not "%TG_VERSION%"=="%EXPECTED_TG_VERSION%" (
    echo Error: expected tgcli %EXPECTED_TG_VERSION%, got "%TG_VERSION%".
    echo Check requirements.txt before continuing.
    exit /b 1
)

REM Configure tgcli (writes to %USERPROFILE%\.config\tgcli\)
set TGCLI_DIR=%USERPROFILE%\.config\tgcli
set TGCLI_CONFIG=%TGCLI_DIR%\config.toml

if not exist "%TGCLI_CONFIG%" (
    if not exist "%TGCLI_DIR%" mkdir "%TGCLI_DIR%"
    copy config.example.toml "%TGCLI_CONFIG%" >nul
    echo.
    echo === Next Steps ===
    echo 1. Edit Telegram API credentials:
    echo    %TGCLI_CONFIG%
    echo    Get your api_id and api_hash from: https://my.telegram.org/apps
    echo    ^(If the form shows ERROR, see docs\getting-api-credentials.md^)
    echo.
    echo 2. Login to Telegram:
    echo    call .venv\Scripts\activate.bat
    echo    tg auth login
    echo.
    echo 3. Run a scan:
    echo    scripts\scan.bat channel_lists\example.txt
) else (
    echo tgcli config already exists at %TGCLI_CONFIG% - skipping.
    echo To reconfigure, edit: %TGCLI_CONFIG%
)

if not exist "output" mkdir output

echo.
echo Setup complete. Next: edit config and run 'tg auth login'
echo   Config:  %TGCLI_CONFIG%
echo   Verify:  call .venv\Scripts\activate.bat ^&^& tg auth status
