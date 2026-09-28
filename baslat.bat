@echo off
title TurkAnime Yerel Arsiv Portali
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi! Lutfen Python yukleyin veya PATH'e ekleyin.
    pause
    exit /b 1
)
python server.py
pause
