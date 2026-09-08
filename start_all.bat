@echo off
title ThreatIntel - Launcher

echo ========================================
echo   Threat Intelligence QA System
echo   Starting services...
echo ========================================
echo.

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

echo Current dir: %cd%
echo.

echo [1/3] Starting Retrieval Service...
start "Retrieval" /d "%PROJECT_ROOT%wjm-search" cmd /k "python api_server.py"

timeout /t 3 /nobreak >nul

echo [2/3] Starting QA Service...
start "QA" /d "%PROJECT_ROOT%lan_shuyang_qa" cmd /k "python run.py"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Web Interface...
start "Web" /d "%PROJECT_ROOT%web" cmd /k "streamlit run app.py"

timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   All services started!
echo   Retrieval: http://127.0.0.1:8001
echo   QA:        http://127.0.0.1:8000
echo   Web:       http://127.0.0.1:8501
echo ========================================
echo.
echo Press any key to close this window...
pause >nul