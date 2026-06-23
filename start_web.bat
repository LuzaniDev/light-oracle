@echo off
cd /d "%~dp0"
echo Instalando dependencias Python...
.\venv\Scripts\pip.exe install -q fastapi uvicorn python-multipart sse-starlette 2>nul
echo Iniciando em http://localhost:8081
.\venv\Scripts\python.exe run_web.py
pause
