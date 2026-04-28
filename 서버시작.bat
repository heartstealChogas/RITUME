@echo off
chcp 65001 > nul
title 가차 발주 시스템
echo.
echo ============================================
echo   가차 발주 시스템 서버 시작
echo   http://localhost:8000 으로 접속하세요
echo ============================================
echo.
cd /d "%~dp0"
start "" "http://localhost:8000"
python app.py
pause
