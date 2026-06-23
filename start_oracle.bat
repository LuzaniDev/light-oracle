@echo off
cd /d "C:\Users\Suporte\Documents\Projetos ECO\Laboratório\light-oracle"
start "" ".\venv\Scripts\streamlit.exe" run app.py --server.port 8501 --server.headless true
timeout /t 15 /nobreak >nul
start http://localhost:8501
