<#[
PowerShell setup script for the Data Nucleus project.

This script creates a Python virtual environment, installs dependencies,
creates required directories and copies the .env example file if necessary.

Usage:
    ./scripts/setup.ps1

Make sure your PowerShell execution policy allows running scripts.  You can
temporarily change it with:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
#>

$ErrorActionPreference = 'Stop'

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

# Activate the venv
& .\.venv\Scripts\Activate.ps1

Write-Host "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy .env.example to .env if .env doesn't exist
if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "Copied .env.example to .env"
}

# Create data directories
$dirs = @("data\raw", "data\chroma", "logs")
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d | Out-Null
        Write-Host "Created directory: $d"
    }
}

Write-Host "Setup complete."