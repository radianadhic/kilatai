@echo off
title Kilat AI
cd /d "%~dp0"
echo Menjalankan Kilat AI...
echo.
python app.py 2>nul || py app.py
echo.
echo (Jendela ini boleh ditutup untuk menghentikan aplikasi)
pause
