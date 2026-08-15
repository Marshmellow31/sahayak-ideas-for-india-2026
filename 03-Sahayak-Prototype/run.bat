@echo off
cd /d "%~dp0backend"
echo Starting Sahayak on http://localhost:8000  (dashboard: /dashboard)
python -m uvicorn main:app --port 8000
