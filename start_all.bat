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

echo [1/4] Starting Retrieval Service...
start "Retrieval" /d "%PROJECT_ROOT%wjm-search" cmd /k "python api_server.py"

timeout /t 3 /nobreak >nul

echo [2/4] Starting QA Service...
start "QA" /d "%PROJECT_ROOT%lan_shuyang_qa" cmd /k "python run.py"

timeout /t 2 /nobreak >nul

echo [2/4] Starting QA Service...
start "Eval" /d "%PROJECT_ROOT%unified_eval" cmd /k "python run_evaluation.py"

echo [3/4] Starting Web Interface...
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

echo ========================================
echo   Stopping all services...
echo ========================================

taskkill /F /FI "WINDOWTITLE eq Retrieval*" 2>nul
taskkill /F /FI "WINDOWTITLE eq QA*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Eval*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Web*" 2>nul

taskkill /F /IM python.exe /FI "WINDOWTITLE eq *api_server*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *run.py*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *run_evaluation.py*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *streamlit*" 2>nul

echo ========================================
echo   All services stopped!
echo ========================================