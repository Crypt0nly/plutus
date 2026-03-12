# Plutus Installer for Windows
# Usage: iwr -useb https://useplutus.ai/install.ps1 | iex
#
# What this script does:
#   1. Checks if Python 3.11+ is installed (installs via winget if not)
#   2. Installs Plutus via pip
#   3. Creates Desktop & Start Menu shortcuts for easy launching
#   4. Launches Plutus in the background and opens the browser
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
$pythonFull = $null  # Will hold the absolute path to the chosen Python

if (-not $pythonCmd) {
    Write-Host "[1/4] Python 3.11+ not found. Installing..." -ForegroundColor Yellow

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
    Write-Host "[1/4] $pyVer found." -ForegroundColor Green
}

# Resolve the absolute path to the Python interpreter so shortcuts and
# verification always use the exact binary we installed into, even when
# multiple Python versions are on PATH.
$pythonFull = (Get-Command $pythonCmd -ErrorAction SilentlyContinue).Source
if (-not $pythonFull) { $pythonFull = $pythonCmd }

# ── Step 2: Install Plutus ────────────────────────────────

Write-Host "[2/4] Installing Plutus..." -ForegroundColor Cyan

try {
    # pip writes progress/warnings to stderr. With $ErrorActionPreference = "Stop",
    # PowerShell converts stderr lines into terminating ErrorRecords when merged via
    # 2>&1, causing a spurious failure. Temporarily relax the preference so that
    # only genuine failures (non-zero exit code) are treated as errors.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    & $pythonFull -m pip install --upgrade pip 2>&1 | Out-Null
    & $pythonFull -m pip install --upgrade "plutus-ai[all]" 2>&1 | Out-Null

    $ErrorActionPreference = $prevEAP

    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed"
    }
    Write-Host "       Plutus installed successfully." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "[ERROR] Failed to install Plutus." -ForegroundColor Red
    Write-Host "        Try running: pip install plutus-ai" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# Refresh PATH so the plutus command is available in this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
             [System.Environment]::GetEnvironmentVariable("Path", "User")

# Verify the `plutus` command works with the correct Python.
# If another Python version has a stale plutus.exe on PATH, `plutus start`
# will fail with "No module named 'plutus'".  Detect this and warn/fix.
$plutusOk = $false
try {
    $verifyOut = & $pythonFull -m plutus --version 2>&1
    if ($LASTEXITCODE -eq 0) { $plutusOk = $true }
} catch {}

if (-not $plutusOk) {
    Write-Host ""
    Write-Host "[WARN] Plutus installed but could not be verified." -ForegroundColor Yellow
    Write-Host "       The shortcuts will use '$pythonFull -m plutus' directly." -ForegroundColor DarkGray
}

# Check if the bare `plutus` command resolves to a different Python version
$stalePlutus = $false
try {
    $plutusExe = (Get-Command plutus -ErrorAction SilentlyContinue).Source
    if ($plutusExe) {
        # The entry-point exe lives in a Python version's Scripts/ dir.
        # If that dir doesn't match our $pythonFull, it's stale.
        $expectedScripts = Split-Path (Split-Path $pythonFull) -ErrorAction SilentlyContinue
        $actualScripts   = Split-Path $plutusExe -ErrorAction SilentlyContinue
        if ($expectedScripts -and $actualScripts -and
            $expectedScripts.ToLower() -ne $actualScripts.ToLower()) {
            $stalePlutus = $true
            Write-Host ""
            Write-Host "  [!] Found a stale 'plutus' command from a different Python:" -ForegroundColor Yellow
            Write-Host "      $plutusExe" -ForegroundColor DarkGray
            Write-Host "      Removing it so the correct version is used..." -ForegroundColor DarkGray
            try {
                Remove-Item $plutusExe -Force -ErrorAction Stop
                Write-Host "      Removed successfully." -ForegroundColor Green
            } catch {
                Write-Host "      Could not remove automatically." -ForegroundColor Yellow
                Write-Host "      You can delete it manually or use: $pythonFull -m plutus start" -ForegroundColor DarkGray
            }
        }
    }
} catch {}

# ── Step 3: Create Shortcuts ─────────────────────────────

Write-Host "[3/4] Creating shortcuts..." -ForegroundColor Cyan

$plutusDir = "$env:USERPROFILE\.plutus"
if (-not (Test-Path $plutusDir)) {
    New-Item -ItemType Directory -Path $plutusDir -Force | Out-Null
}

# Create launcher VBS script.
# This runs Plutus without a visible console window.
# If Plutus is already running, it just opens the browser instead.
$vbsPath = "$plutusDir\start.vbs"
$vbsContent = @"
' Plutus Launcher
' Double-click to start Plutus or open it in your browser.

Set WshShell = CreateObject("WScript.Shell")

' Check if Plutus is already running
alreadyRunning = False
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP")
http.Open "GET", "http://localhost:7777/api/config", False
http.Send
If Err.Number = 0 Then
    If http.Status = 200 Then alreadyRunning = True
End If
On Error GoTo 0

If alreadyRunning Then
    ' Already running - just open the browser
    WshShell.Run "http://localhost:7777"
Else
    ' Start Plutus in the background (hidden console window)
    ' Uses the full Python path to avoid issues with multiple Python versions
    WshShell.Run "cmd /c ""$pythonFull"" -m plutus start", 0, False
End If
"@
Set-Content -Path $vbsPath -Value $vbsContent -Encoding ASCII

# Create Desktop shortcut
$shortcutCreated = $false
try {
    $WshShell = New-Object -ComObject WScript.Shell

    # Desktop shortcut
    $desktopPath = [System.Environment]::GetFolderPath("Desktop")
    $shortcut = $WshShell.CreateShortcut("$desktopPath\Plutus.lnk")
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$vbsPath`""
    $shortcut.Description = "Launch Plutus AI Agent"
    $shortcut.WorkingDirectory = $plutusDir
    $shortcut.Save()

    # Start Menu shortcut
    $startMenuPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
    $startShortcut = $WshShell.CreateShortcut("$startMenuPath\Plutus.lnk")
    $startShortcut.TargetPath = "wscript.exe"
    $startShortcut.Arguments = "`"$vbsPath`""
    $startShortcut.Description = "Launch Plutus AI Agent"
    $startShortcut.WorkingDirectory = $plutusDir
    $startShortcut.Save()

    $shortcutCreated = $true
    Write-Host "       Desktop shortcut created." -ForegroundColor Green
    Write-Host "       Start Menu shortcut created." -ForegroundColor Green
} catch {
    Write-Host "       Could not create shortcuts (non-critical)." -ForegroundColor Yellow
    Write-Host "       You can always start Plutus by running: plutus start" -ForegroundColor DarkGray
}

# ── Step 4: Launch ────────────────────────────────────────

Write-Host "[4/4] Launching Plutus..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Plutus is starting in the background..." -ForegroundColor White
Write-Host "  Your browser will open to http://localhost:7777" -ForegroundColor White
Write-Host "  First time? The setup wizard will guide you through everything." -ForegroundColor DarkGray
Write-Host ""

if ($shortcutCreated) {
    Write-Host "  To start Plutus anytime:" -ForegroundColor White
    Write-Host "    - Double-click 'Plutus' on your Desktop" -ForegroundColor DarkGray
    Write-Host "    - Or search 'Plutus' in the Start Menu" -ForegroundColor DarkGray
} else {
    Write-Host "  To start Plutus anytime, run:" -ForegroundColor White
    Write-Host "    $pythonFull -m plutus start" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Tip: After setup, go to Settings to enable Linux Superpowers (WSL)." -ForegroundColor DarkGray
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# Launch in the background via the VBS launcher
Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`""
