@echo off
title DataOps AI Platform Launcher
echo ============================================================
echo   DataOps AI Platform - FastAPI Backend and Frontend
echo ============================================================

echo [1/2] Launching FastAPI Backend on http://127.0.0.1:8000 ...
start "DataOps FastAPI Backend" cmd /k "cd /d %~dp0Backend && python run_server.py"

echo [2/2] Launching Vite Frontend on http://localhost:5173 ...
start "DataOps Frontend" cmd /k "cd /d %~dp0AI Powered && npm run dev"

echo.
echo Both servers have been launched in separate windows!
echo - FastAPI Backend: http://127.0.0.1:8000 (Swagger docs: http://127.0.0.1:8000/docs)
echo - AI Bot & Web App: http://localhost:5173
echo ============================================================
pause
