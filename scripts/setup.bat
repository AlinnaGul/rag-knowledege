@echo off
setlocal
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

if not exist .env copy .env.example .env

if not exist data\raw mkdir data\raw
if not exist data\chroma mkdir data\chroma
if not exist logs mkdir logs

echo Setup complete.
endlocal
