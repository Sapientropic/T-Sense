@echo off
setlocal
REM Thin Windows wrapper for the cross-platform Python scanner.
REM Usage: scripts\scan.bat <channel_list.txt> [hours] [scan.py options]

cd /d "%~dp0\.."

if "%~1"=="" (
    echo Error: Missing channel list argument.
    echo Usage: scripts\scan.bat ^<channel_list.txt^> [hours] [scan.py options]
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo Error: .venv not found. Run setup.bat first.
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo Error: Failed to activate .venv.
    exit /b 1
)

where tg >nul 2>nul
if errorlevel 1 (
    echo Error: tg command not found in venv. Run setup.bat first.
    exit /b 1
)

python "scripts\scan.py" %*
exit /b %ERRORLEVEL%
