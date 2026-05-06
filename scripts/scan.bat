@echo off
REM Batch-read Telegram channels (Windows)
REM Usage: scripts\scan.bat <channel_list.txt> [hours]

cd /d "%~dp0\.."

set LIST=%1
set HOURS=%2
if "%HOURS%"=="" set HOURS=24

if "%LIST%"=="" (
    echo Error: Missing channel list argument.
    echo Usage: scripts\scan.bat ^<channel_list.txt^> [hours]
    exit /b 1
)

if not exist "%LIST%" (
    echo Error: Channel list not found: %LIST%
    exit /b 1
)

call .venv\Scripts\activate.bat

for /f %%i in ('python -c "from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(hours=%HOURS%)).strftime('%%Y-%%m-%%d'))"') do set AFTER=%%i

if not exist "output" mkdir output
for /f %%i in ('python -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%%Y%%m%%d_%%H%%M'))"') do set TS=%%i
set OUTPUT=output\scan_%TS%.jsonl
set ERRORS=output\scan_%TS%.errors.log

echo Time window: past %HOURS%h (since %AFTER%)
echo Output: %OUTPUT%
echo ---

set CHANNELS=0
set FAILURES=0
for /f "usebackq eol=# delims=" %%ch in ("%LIST%") do (
    set /a CHANNELS+=1
    echo [!CHANNELS!] Reading: %%ch
    tg read "%%ch" --after %AFTER% --limit 100 >> "%OUTPUT%" 2>>"%ERRORS%"
    if errorlevel 1 (
        echo   WARNING: Failed: %%ch (see %ERRORS%)
        set /a FAILURES+=1
    )
    timeout /t 1 /nobreak >nul
)

for /f %%i in ('python -c "import sys; print(sum(1 for _ in open(r'%OUTPUT%', encoding='utf-8')))"') do set COUNT=%%i

echo ---
echo Done. %CHANNELS% channels scanned, %COUNT% messages collected.
if %FAILURES% gtr 0 (
    echo WARNING: %FAILURES% channels failed. See: %ERRORS%
)
echo Output: %OUTPUT%
echo.
echo Next: Summarize with your preferred AI:
echo   OpenAI/DeepSeek: python scripts\summarize.py --input %OUTPUT% --profile profiles\YOUR_PROFILE.md
echo   Codex/Claude:    Point your agent at %OUTPUT% + profiles\YOUR_PROFILE.md
