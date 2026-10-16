# WILD-ID Nexus PowerShell Launcher
Write-Host "===================================================" -ForegroundColor Green
Write-Host "  Starting WILD-ID Nexus (Pugmark)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Green

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptDir "pugmark")

$venvPython = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[1/3] Setting up Python virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
}

Write-Host "[2/3] Applying database migrations..." -ForegroundColor Yellow
& $venvPython manage.py migrate

Write-Host "[3/3] Opening browser and starting server..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:8000/"

Write-Host "`n===================================================" -ForegroundColor Green
Write-Host "  WILD-ID Nexus is running at: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor Yellow
Write-Host "===================================================`n" -ForegroundColor Green

& $venvPython manage.py runserver 127.0.0.1:8000
