# Plutus Installer for Windows
# Usage: iwr -useb https://raw.githubusercontent.com/Crypt0nly/plutus/main/install.ps1 | iex
#
# What this script does:
#   1. Checks if Python 3.11+ is installed (installs via winget if not)
#   2. Installs Plutus via pip
#   3. Launches Plutus
#
# WSL is NOT installed by this script. Plutus will walk you through
# setting up WSL from inside the app if you want Linux superpowers.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ____  _       _             " -ForegroundColor Magenta
Write-Host " |  _ \| |_   _| |_ _   _ ___ " -ForegroundColor Magenta
Write-Host " | |_) | | | | | __| | | / __|" -ForegroundColor Magenta
Write-Host " |  __/| | |_| | |_| |_| \__ \" -ForegroundColor Magenta
Write-Host " |_|   |_|\__,_|\__|\__,_|___/" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Plutus Installer" -ForegroundColor White
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ── Step 1: Check Python ──────────────────────────────────

function Get-PythonCommand {
    # Try python first, then python3
    foreach ($cmd in @("python", "python3")) {
        try {
            $version = & $cmd --version 2>&1
            if ($version -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 11) {
                    return $cmd
                }
            }
        } catch {
            continue
        }
    }
    return $null
}

$pythonCmd = Get-PythonCommand

if (-not $pythonCmd) {
    Write-Host "[1/3] Python 3.11+ not found. Installing..." -ForegroundColor Yellow

    # Check if winget is available
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "       Using winget to install Python 3.11..." -ForegroundColor DarkGray
        winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements

        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
                     [System.Environment]::GetEnvironmentVariable("Path", "User")

        $pythonCmd = Get-PythonCommand
        if (-not $pythonCmd) {
            Write-Host ""
            Write-Host "[ERROR] Python was installed but isn't on PATH yet." -ForegroundColor Red
            Write-Host "        Close this terminal, open a new one, and run this installer again." -ForegroundColor Yellow
            Write-Host ""
            exit 1
        }
        Write-Host "       Python installed successfully." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[ERROR] Python 3.11+ is required but not installed." -ForegroundColor Red
        Write-Host "        Install it from https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "        Make sure to check 'Add Python to PATH' during install." -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
} else {
    $pyVer = & $pythonCmd --version 2>&1
    Write-Host "[1/3] $pyVer found." -ForegroundColor Green
}

# ── Step 2: Install Plutus ────────────────────────────────

Write-Host "[2/3] Installing Plutus..." -ForegroundColor Cyan

try {
    & $pythonCmd -m pip install --upgrade pip 2>&1 | Out-Null
    & $pythonCmd -m pip install plutus 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed"
    }
    Write-Host "       Plutus installed successfully." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "[ERROR] Failed to install Plutus." -ForegroundColor Red
    Write-Host "        Try running: pip install plutus" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# ── Step 3: Launch ────────────────────────────────────────

Write-Host "[3/3] Launching Plutus..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host "  Plutus will open in your browser at http://localhost:7777" -ForegroundColor White
Write-Host "  First time? The setup wizard will guide you through everything." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Tip: After setup, go to Settings to enable Linux Superpowers (WSL)." -ForegroundColor DarkGray
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

plutus start
