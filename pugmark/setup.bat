@echo off
cd /d "%~dp0"
where py >nul 2>&1 && (py -3 -m venv .venv) || (python -m venv .venv)
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Package install failed.
  pause
  exit /b 1
)
python manage.py migrate
echo.
echo Pugmark is running. Open http://127.0.0.1:8000
echo.
python manage.py runserver 127.0.0.1:8000
pause
