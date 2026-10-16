@echo off
setlocal
echo ===================================================
echo   Starting WILD-ID Nexus (Pugmark)
echo ===================================================
echo.

cd /d "%~dp0pugmark"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Setting up Python virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo [2/3] Applying database migrations...
python manage.py migrate

echo [3/3] Opening browser and starting server...
start http://127.0.0.1:8000/
echo.
echo ===================================================
echo  WILD-ID Nexus is running at: http://127.0.0.1:8000
echo  Press Ctrl+C to stop the server.
echo ===================================================
echo.
python manage.py runserver 127.0.0.1:8000

pause
