@echo off
cd /d %~dp0backend
if not exist ..\.venv (
  python -m venv ..\.venv
)
call ..\.venv\Scripts\activate.bat
pip install -r requirements.txt -q
set PYTHONPATH=%CD%
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
