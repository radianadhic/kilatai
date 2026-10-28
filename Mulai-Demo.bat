@echo off
title Kilat AI - MODE DEMO
cd /d "%~dp0"
echo Membuka mode demo (jawaban simulasi, tanpa Ollama)...
echo.
start "Mock Ollama (Demo)" cmd /k python mock-ollama.py
timeout /t 2 /nobreak >nul
python app.py 2>nul || py app.py
echo.
pause
