#!/usr/bin/env bash
#
# Laqta — Windows setup (PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#
# Creates the backend virtual environment, installs the pinned dependencies
# and the frontend packages, then prints the next steps. The equivalent of
# scripts/setup.sh.
#
# Requirements: Python 3.11+, Node.js 22.12+, FFmpeg (with libass) on PATH.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$VenvDir = Join-Path $BackendDir ".venv"

function Write-Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Write-Fail($message) { Write-Host "xx  $message" -ForegroundColor Red; exit 1 }

# --- Python -----------------------------------------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Fail "python was not found. Install Python 3.11+ from python.org." }

$versionText = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
$versionOk = & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Fail "Python 3.11+ is required (found $versionText)." }
Write-Step "Python $versionText"

# --- Node -------------------------------------------------------------------
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) { Write-Fail "npm was not found. Install Node.js 22.12+ from nodejs.org." }
Write-Step "Node $((node --version))"

# --- FFmpeg -----------------------------------------------------------------
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "!!  FFmpeg was not found on PATH. Install it (winget install Gyan.FFmpeg) - rendering needs it." -ForegroundColor Yellow
}

# --- Backend ----------------------------------------------------------------
if (-not (Test-Path $VenvDir)) {
    Write-Step "Creating the backend virtual environment"
    & python -m venv $VenvDir
} else {
    Write-Step "Reusing the existing virtual environment"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { Write-Fail "The virtual environment is broken. Delete $VenvDir and run this script again." }

Write-Step "Upgrading pip"
& $VenvPython -m pip install --quiet --upgrade pip

Write-Step "Installing the backend (ASR profile)"
& $VenvPython -m pip install --quiet -r (Join-Path $BackendDir "requirements-asr.txt")

Write-Step "Installing the backend development tools"
& $VenvPython -m pip install --quiet -r (Join-Path $BackendDir "requirements-dev.txt")

Write-Step "Installing Laqta (core package + CLI)"
& $VenvPython -m pip install --quiet -e $RepoRoot

# --- Frontend ---------------------------------------------------------------
Write-Step "Installing the frontend dependencies"
Push-Location $FrontendDir
try {
    if (Test-Path "package-lock.json") { & npm ci --silent } else { & npm install --silent }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "  Start the API:     cd backend; .\.venv\Scripts\uvicorn app.main:app --reload"
Write-Host "  Start the studio:  cd frontend; npm run dev"
Write-Host "  Check the machine: .\.venv\Scripts\laqta doctor"
Write-Host ""
Write-Host "  Docs: $RepoRoot\docs"
Write-Host ""
