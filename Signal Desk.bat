@echo off
setlocal

cd /d "%~dp0"
title Signal Desk

echo Starting Signal Desk...

if not exist ".venv\Scripts\python.exe" (
    echo First launch: setting up the local Python environment.
    call setup.bat
    if errorlevel 1 (
        echo.
        echo Signal Desk setup failed. Check the messages above, then run this launcher again.
        pause
        exit /b 1
    )
) else (
    if not exist ".tgcs\sources.json" (
        echo Preparing the default workspace.
        call tgcs.bat init
        if errorlevel 1 (
            echo Warning: default workspace setup did not complete. Signal Desk can still open.
        )
    )
)

echo.
echo Opening Signal Desk. Keep this window open while you use the app.
call tgcs.bat dashboard --open

echo.
echo Signal Desk stopped.
pause
