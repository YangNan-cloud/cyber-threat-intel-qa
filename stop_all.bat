@echo off
title ThreatIntel - Stopper

echo ========================================
echo   Stopping all services...
echo ========================================

taskkill /F /FI "WINDOWTITLE eq Retrieval*" 2>nul
taskkill /F /FI "WINDOWTITLE eq QA*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Web*" 2>nul

taskkill /F /IM python.exe /FI "WINDOWTITLE eq *api_server*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *run.py*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *streamlit*" 2>nul

echo ========================================
echo   All services stopped!
echo ========================================
pause