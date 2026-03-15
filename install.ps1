# Plutus Installer for Windows
# Usage: iwr -useb https://useplutus.ai/install.ps1 | iex
# (The -useb flag avoids a security warning prompt on older PowerShell versions)
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

# ── Pipeline-safe re-launch ─────────────────────────────────
# When invoked via `iwr ... | iex`, the script text flows through stdin.
# Child processes (pip, python) inherit that handle and consume part of
# the script, which corrupts the iex pipeline and crashes the terminal.
# Fix: save to a temp file and re-run from disk so stdin is clean.
if (-not $PSCommandPath) {
    $tmpPs1 = Join-Path ([System.IO.Path]::GetTempPath()) "plutus-install-$PID.ps1"
    $MyInvocation.MyCommand.ScriptBlock.ToString() | Set-Content -LiteralPath $tmpPs1 -Encoding UTF8
    try     { & powershell.exe -ExecutionPolicy Bypass -File $tmpPs1 }
    finally { Remove-Item -LiteralPath $tmpPs1 -Force -ErrorAction SilentlyContinue }
    return
}

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

# ── Spinner helper ───────────────────────────────────────────
# Runs a script block in a background job and displays an animated
# spinner on the current line until the job completes.  Returns the
# exit code captured inside the job.
function Invoke-WithSpinner {
    param(
        [string]$Label,
        [scriptblock]$Action
    )

    # Write the label without a newline so the spinner appears on the same line
    Write-Host "`r       $Label " -NoNewline -ForegroundColor DarkGray

    $frames = @('|', '/', '-', '\')
    $frameIdx = 0

    # Start the work in a background job
    $job = Start-Job -ScriptBlock $Action

    # Animate while the job is running
    while ($job.State -eq 'Running') {
        Write-Host "`r       $Label $($frames[$frameIdx])" -NoNewline -ForegroundColor DarkGray
        $frameIdx = ($frameIdx + 1) % $frames.Count
        Start-Sleep -Milliseconds 120
    }

    # Collect output and clean up
    $result = Receive-Job -Job $job
    Remove-Job -Job $job -Force

    # Clear the spinner character
    Write-Host "`r       $Label  " -NoNewline -ForegroundColor DarkGray
    Write-Host ""

    return $result
}

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
            Read-Host "Press Enter to close"
            exit 1
        }
        Write-Host "       Python installed successfully." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[ERROR] Python 3.11+ is required but not installed." -ForegroundColor Red
        Write-Host "        Install it from https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "        Make sure to check 'Add Python to PATH' during install." -ForegroundColor Yellow
        Write-Host ""
        Read-Host "Press Enter to close"
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

# Temporarily allow errors so pip's stderr warnings/notices don't crash the
# script. PowerShell 5.1 converts any stderr output from native commands into
# ErrorRecords; with $ErrorActionPreference = "Stop" those become terminating
# exceptions that kill the installer before *>$null can suppress them.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"

# ── Upgrade pip (with spinner) ──
$pipUpgradeJob = Start-Job -ScriptBlock {
    param($py)
    & $py -m pip install --upgrade pip *>$null
    $LASTEXITCODE
} -ArgumentList $pythonFull

$frames = @('|', '/', '-', '\')
$frameIdx = 0
Write-Host "`r       Updating pip... " -NoNewline -ForegroundColor DarkGray
while ($pipUpgradeJob.State -eq 'Running') {
    Write-Host "`r       Updating pip... $($frames[$frameIdx])" -NoNewline -ForegroundColor DarkGray
    $frameIdx = ($frameIdx + 1) % $frames.Count
    Start-Sleep -Milliseconds 120
}
Receive-Job -Job $pipUpgradeJob | Out-Null
Remove-Job -Job $pipUpgradeJob -Force
Write-Host "`r       Updating pip... done.  " -ForegroundColor DarkGray

# ── Install plutus-ai (with spinner) ──
$pipInstallJob = Start-Job -ScriptBlock {
    param($py)
    & $py -m pip install --upgrade "plutus-ai" *>$null
    $LASTEXITCODE
} -ArgumentList $pythonFull

$frameIdx = 0
Write-Host "`r       Downloading and installing packages... " -NoNewline -ForegroundColor DarkGray
while ($pipInstallJob.State -eq 'Running') {
    Write-Host "`r       Downloading and installing packages... $($frames[$frameIdx])" -NoNewline -ForegroundColor DarkGray
    $frameIdx = ($frameIdx + 1) % $frames.Count
    Start-Sleep -Milliseconds 120
}
$pipExit = Receive-Job -Job $pipInstallJob
Remove-Job -Job $pipInstallJob -Force
Write-Host "`r       Downloading and installing packages... done.  " -ForegroundColor DarkGray

# If the first attempt fails (e.g. stale metadata, pip cache corruption),
# retry with --force-reinstall.  IMPORTANT: do NOT use --no-deps here —
# on a fresh install the dependencies (fastapi, uvicorn, etc.) have never
# been installed, so skipping them leaves the server unable to start.
if ($pipExit -ne 0) {
    Write-Host "       Retrying with --force-reinstall..." -ForegroundColor DarkGray

    $retryJob = Start-Job -ScriptBlock {
        param($py)
        & $py -m pip install --force-reinstall --upgrade "plutus-ai" *>$null
        $LASTEXITCODE
    } -ArgumentList $pythonFull

    $frameIdx = 0
    Write-Host "`r       Reinstalling packages... " -NoNewline -ForegroundColor DarkGray
    while ($retryJob.State -eq 'Running') {
        Write-Host "`r       Reinstalling packages... $($frames[$frameIdx])" -NoNewline -ForegroundColor DarkGray
        $frameIdx = ($frameIdx + 1) % $frames.Count
        Start-Sleep -Milliseconds 120
    }
    $pipExit = Receive-Job -Job $retryJob
    Remove-Job -Job $retryJob -Force
    Write-Host "`r       Reinstalling packages... done.  " -ForegroundColor DarkGray
}

$ErrorActionPreference = $prevEAP

if ($pipExit -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Failed to install Plutus (pip exit code $pipExit)." -ForegroundColor Red
    Write-Host "        Try running manually: $pythonFull -m pip install plutus-ai" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

# Verify that critical runtime dependencies were installed (not just plutus
# itself).  This catches the case where --force-reinstall --no-deps was used
# by mistake, or where a dependency couldn't be resolved for this Python version.
$depCheck = & $pythonFull -c "import fastapi; import uvicorn; import pydantic; print('ok')" 2>$null
if ($depCheck -ne "ok") {
    Write-Host "       Installing missing dependencies..." -ForegroundColor DarkGray
    & $pythonFull -m pip install --upgrade "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "pydantic>=2.10.0" "websockets>=14.0" "click>=8.1.0" "rich>=13.9.0" "aiosqlite>=0.20.0" "httpx>=0.28.0" "psutil>=6.1.0" "litellm>=1.55.0" *>$null
}

Write-Host "       Plutus installed successfully." -ForegroundColor Green

# Refresh PATH so the plutus command is available in this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
             [System.Environment]::GetEnvironmentVariable("Path", "User")

# pip may install to the per-user site-packages (AppData\Roaming\Python\PythonXYZ\Scripts)
# which often isn't on PATH. Detect this and add it so `plutus` works immediately.
$prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$userScriptsDir = & $pythonFull -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))" 2>$null
$ErrorActionPreference = $prevEAP
if ($userScriptsDir -and (Test-Path $userScriptsDir)) {
    $pathLower = $env:Path.ToLower()
    if (-not $pathLower.Contains($userScriptsDir.ToLower())) {
        # Add to this session
        $env:Path = "$userScriptsDir;$env:Path"

        # Persist to the user's PATH so future terminals work too
        $currentUserPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (-not $currentUserPath) { $currentUserPath = "" }
        if (-not $currentUserPath.ToLower().Contains($userScriptsDir.ToLower())) {
            [System.Environment]::SetEnvironmentVariable(
                "Path",
                "$userScriptsDir;$currentUserPath",
                "User"
            )
            Write-Host "       Added Python Scripts to PATH: $userScriptsDir" -ForegroundColor DarkGray
        }
    }
}

# Also check the system-level Scripts dir (next to python.exe)
$sysScriptsDir = Split-Path $pythonFull
if ($sysScriptsDir -and -not $sysScriptsDir.EndsWith("Scripts")) {
    $sysScriptsDir = Join-Path $sysScriptsDir "Scripts"
}
if ($sysScriptsDir -and (Test-Path $sysScriptsDir)) {
    if (-not $env:Path.ToLower().Contains($sysScriptsDir.ToLower())) {
        $env:Path = "$sysScriptsDir;$env:Path"
    }
}

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

# Create launcher scripts.
# Two-file approach for reliability:
#   start_plutus.bat  — runs Python and redirects ALL output to the log file
#   start.vbs         — calls the .bat with a hidden window (no flash)
#
# Why a .bat wrapper instead of `cmd /c python ...` directly in VBS?
# VBS window-style 0 creates a hidden console.  On some Python versions
# (notably 3.14+), Python's console I/O init fails when the console is
# invisible, causing a silent crash.  The .bat gives Python a real
# console (hidden by VBS) and captures all output to a log file.
#
# NOTE: --no-browser is passed because the VBS launcher handles opening
# the browser itself, preventing a duplicate tab.

$vbsPath = "$plutusDir\start.vbs"
$batPath = "$plutusDir\start_plutus.bat"
$logPath = "$plutusDir\plutus.log"

# ── .bat launcher ──
$batContent = @"
@echo off
"$pythonFull" -m plutus start --no-browser > "$logPath" 2>&1
"@
Set-Content -Path $batPath -Value $batContent -Encoding ASCII

# ── .vbs launcher (calls the .bat) ──
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
    ' Start Plutus via the .bat launcher (hidden window)
    WshShell.Run """$batPath""", 0, False

    ' Wait a moment, then open the browser
    WScript.Sleep 2000
    WshShell.Run "http://localhost:7777"
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

# Launch in the background via the VBS launcher (which handles opening the browser)
Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`""

# Wait for the server to come up (up to 15 seconds)
$serverOk = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:7777/api/config" `
                                  -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            $serverOk = $true
            break
        }
    } catch {
        # Not ready yet — keep waiting
    }
}

if ($serverOk) {
    Write-Host "  Plutus is running at http://localhost:7777" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Plutus may not have started correctly." -ForegroundColor Yellow
    $logFile = "$env:USERPROFILE\.plutus\plutus.log"
    if (Test-Path $logFile) {
        Write-Host ""
        Write-Host "  Last 10 lines of the log ($logFile):" -ForegroundColor DarkGray
        Get-Content $logFile -Tail 10 | ForEach-Object {
            Write-Host "    $_" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    Write-Host "  Try running manually to see the full error:" -ForegroundColor Yellow
    Write-Host "    $pythonFull -m plutus start" -ForegroundColor White
}
