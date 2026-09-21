<#
.SYNOPSIS
Windows Task Runner for Voice-Fraud Detection System.

.DESCRIPTION
Provides cross-platform development commands when 'make' is unavailable on Windows.
Runs pytest, linting, Docker, or standalone service runners using the local environment.

.EXAMPLE
.\run.ps1 test
.\run.ps1 lint
.\run.ps1 up
.\run.ps1 down
.\run.ps1 run-gateway
#>

param(
    [Parameter(Position=0, Mandatory=$false)]
    [ValidateSet("test", "test-audit", "lint", "up", "down", "build", "run-gateway", "clean")]
    [string]$Command = "test"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Locate Python runner (uv or local virtualenv or system python)
$UvBin = "$HOME\.local\bin\uv.exe"
$VenvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Invoke-PyCommand([string[]]$PyArgs) {
    if (Test-Path $UvBin) {
        & $UvBin run @PyArgs
    } elseif (Test-Path $VenvPy) {
        & $VenvPy -m @PyArgs
    } else {
        python @PyArgs
    }
}

switch ($Command) {
    "test" {
        Write-Host "==> Running pytest test suite..." -ForegroundColor Cyan
        Invoke-PyCommand @("pytest", "tests/", "-v", "--tb=short")
    }
    "test-audit" {
        Write-Host "==> Running audit trail tests with PostgreSQL..." -ForegroundColor Cyan
        Invoke-PyCommand @("pytest", "tests/test_audit.py", "-v", "--tb=short")
    }
    "lint" {
        Write-Host "==> Running lint / syntax compilation..." -ForegroundColor Cyan
        Invoke-PyCommand @("-m", "compileall", "-q", ".")
        Write-Host "All files compiled successfully!" -ForegroundColor Green
    }
    "up" {
        Write-Host "==> Starting Docker Compose services..." -ForegroundColor Cyan
        docker-compose up -d
    }
    "down" {
        Write-Host "==> Stopping Docker Compose services..." -ForegroundColor Cyan
        docker-compose down
    }
    "build" {
        Write-Host "==> Building Docker images..." -ForegroundColor Cyan
        docker-compose build
    }
    "run-gateway" {
        Write-Host "==> Starting Gateway on 127.0.0.1:8000..." -ForegroundColor Cyan
        Invoke-PyCommand @("uvicorn", "gateway.app:app", "--host", "127.0.0.1", "--port", "8000", "--reload")
    }
    "clean" {
        Write-Host "==> Cleaning cache directories..." -ForegroundColor Cyan
        Get-ChildItem -Path $ProjectRoot -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem -Path $ProjectRoot -Filter ".pytest_cache" -Recurse -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Clean completed." -ForegroundColor Green
    }
}
