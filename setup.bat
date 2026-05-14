@echo off
REM Install T-Sense dependencies (Windows)
REM Requires: Python 3.12+

cd /d "%~dp0"

echo === T-Sense Setup ===

REM Check Python version (require 3.12+)
python --version 2>nul || (
    echo Error: Python not found. Install from https://python.org
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do set "PYMAJOR=%%a"& set "PYMINOR=%%b"

if %PYMAJOR% lss 3 (
    echo Error: Python 3.12+ required. Found %PYVER%. Install from https://python.org
    exit /b 1
)
if %PYMAJOR% equ 3 if %PYMINOR% lss 12 (
    echo Error: Python 3.12+ required. Found %PYVER%. Install from https://python.org
    exit /b 1
)

echo Found Python %PYVER%

if "%TG_SCANNER_SETUP_SKIP_INSTALL%"=="1" (
    echo Skipping dependency install because TG_SCANNER_SETUP_SKIP_INSTALL=1.
    goto configure_scanner
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Failed to activate .venv.
    exit /b 1
)

python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo pip not found in venv; bootstrapping with ensurepip...
    python -m ensurepip --upgrade >nul
    if errorlevel 1 (
        echo Error: failed to bootstrap pip with ensurepip.
        exit /b 1
    )
)

echo Installing pinned core dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

echo Installing optional pinned LLM dependencies (openai for summarize.py)...
python -m pip install -r requirements-llm.txt --quiet 2>nul || echo   ^(openai not installed - summarize.py will need it later^)

if exist "requirements-desktop.txt" (
    echo Installing optional desktop integration dependencies...
    python -m pip install -r requirements-desktop.txt --quiet 2>nul || echo   ^(desktop keyring extras not installed - environment variables still work^)
)

set "TELETHON_VERSION="
for /f "delims=" %%v in ('python -c "import telethon; print(telethon.__version__)" 2^>nul') do set "TELETHON_VERSION=%%v"
if "%TELETHON_VERSION%"=="" (
    echo Error: telethon not importable. Check requirements.txt and venv.
    exit /b 1
)
echo telethon %TELETHON_VERSION% OK

:configure_scanner
REM Configure scanner (default path kept for backward compatibility)
set "TGCLI_DIR="
if not "%TG_SCANNER_CONFIG_DIR%"=="" set "TGCLI_DIR=%TG_SCANNER_CONFIG_DIR%"
if "%TGCLI_DIR%"=="" if not "%TGCLI_CONFIG_DIR%"=="" set "TGCLI_DIR=%TGCLI_CONFIG_DIR%"
if "%TGCLI_DIR%"=="" set "TGCLI_DIR=%USERPROFILE%\.config\tgcli"
set "TGCLI_CONFIG=%TGCLI_DIR%\config.toml"

if exist "%TGCLI_CONFIG%" goto config_exists

if exist "%TGCLI_DIR%" goto config_dir_ready
mkdir "%TGCLI_DIR%"
if not errorlevel 1 goto config_dir_ready
echo Error: Failed to create config directory: %TGCLI_DIR%
exit /b 1

:config_dir_ready
copy config.example.toml "%TGCLI_CONFIG%" >nul
if not errorlevel 1 goto config_copied
echo Error: Failed to copy config.example.toml to %TGCLI_CONFIG%
exit /b 1

:config_copied
echo.
echo === Next Steps ===
echo 1. Open Signal Desk:
echo    Signal Desk.bat
echo.
echo 2. In the Start tab, save your Telegram app ID/hash, connect Telegram,
echo    run the offline demo, and start the first AI review.
echo    Telegram app credentials come from: https://my.telegram.org/apps
echo    ^(If the form shows ERROR, see docs\getting-api-credentials.md^)
goto config_done

:config_exists
echo Scanner config already exists at %TGCLI_CONFIG% - skipping.
echo To reconfigure, edit: %TGCLI_CONFIG%

:config_done

if not exist "output" mkdir output

echo.
echo Initializing local project defaults (jobs starter)...
call tgcs.bat init --starter jobs
if errorlevel 1 (
    echo Warning: local project defaults were not initialized. Run tgcs.bat init --starter jobs after setup.
) else (
    echo Local project defaults ready.
)

echo.
echo Setup complete. Next: open Signal Desk
echo   Config:  %TGCLI_CONFIG%
echo   Open:    Signal Desk.bat
echo   Expert CLI fallback: tgcs.bat quickstart jobs
