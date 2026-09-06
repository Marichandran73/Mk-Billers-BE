$ErrorActionPreference = "Stop"

$python = "D:/Global-Bill-app/venv/Scripts/python.exe"

if (-not (Test-Path $python)) {
    throw "Python executable not found at $python"
}

Set-Location $PSScriptRoot
& $python -m uvicorn app.main:app --reload
