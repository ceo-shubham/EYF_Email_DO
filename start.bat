@echo off
title EaseYourFiling Outreach System
color 0A

echo.
echo  ==========================================
echo   EaseYourFiling -- Smart Outreach System
echo  ==========================================
echo.
echo  Starting... please wait
echo.

cd /d "%~dp0"

start "" "http://localhost:8501"

streamlit run app.py --server.port 8501 --server.headless true

pause
