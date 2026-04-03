# Plutus Uninstaller for Windows
# Usage: powershell -ExecutionPolicy Bypass -File uninstall.ps1
# Or:    iwr -useb https://useplutus.ai/uninstall.ps1 | iex

$ErrorActionPreference = "Continue"

# -- Pipeline-safe re-launch ------------------------------------------------
if (-not $PSCommandPath) {
    $tmpPs1 = Join-Path ([System.IO.Path]::GetTempPath()) "plutus-uninstall-$PID.ps1"
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
Write-Host "  Plutus Uninstaller" -ForegroundColor White
Write-Host "  ==============================" -ForegroundColor DarkGray
Write-Host ""

# -- Step 1: Terminate Processes --------------------------------------------

Write-Host "[1/6] Stopping Plutus..." -ForegroundColor Cyan
try {
    $portProcess = Get-NetTCPConnection -LocalPort 7777 -ErrorAction SilentlyContinue
    if ($portProcess) {
        Stop-Process -Id $portProcess.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "       Stopped running Plutus instance." -ForegroundColor DarkGray
    }
} catch {}

# Also kill any VBS/WScript launchers
Get-Process wscript -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*start.vbs*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue

# -- Step 2: Remove Shortcuts -----------------------------------------------

Write-Host "[2/6] Removing shortcuts..." -ForegroundColor Cyan

$desktopPath = [System.Environment]::GetFolderPath("Desktop")
$startMenuPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"

# Also check OneDrive Desktop if it exists
$oneDriveDesktop = "$env:USERPROFILE\OneDrive\Desktop"

$shortcuts = @(
    "$desktopPath\Plutus.lnk",
    "$startMenuPath\Plutus.lnk"
)
if ((Test-Path $oneDriveDesktop) -and ($oneDriveDesktop -ne $desktopPath)) {
    $shortcuts += "$oneDriveDesktop\Plutus.lnk"
}

$removed = 0
foreach ($link in $shortcuts) {
    if (Test-Path $link) {
        Remove-Item $link -Force -ErrorAction SilentlyContinue
        Write-Host "       Removed: $link" -ForegroundColor DarkGray
        $removed++
    }
}
if ($removed -eq 0) {
    Write-Host "       No shortcuts found." -ForegroundColor DarkGray
}

# -- Step 3: Uninstall Python Package ----------------------------------------

Write-Host "[3/6] Uninstalling Plutus package..." -ForegroundColor Cyan

function Get-PythonCommand {
    foreach ($cmd in @("python", "python3")) {
        try {
            $version = & $cmd --version 2>&1
            if ($version -match "Python (\d+)\.(\d+)") { return $cmd }
        } catch { continue }
    }
    return $null
}

$pythonCmd = Get-PythonCommand
if ($pythonCmd) {
    Write-Host "       Using $pythonCmd to uninstall..." -ForegroundColor DarkGray
    & $pythonCmd -m pip uninstall plutus-ai -y *>$null
    Write-Host "       Python package removed." -ForegroundColor Green
} else {
    Write-Host "       Python not found; skipping pip uninstall." -ForegroundColor Yellow
}

# -- Step 4: Clean up PATH --------------------------------------------------

Write-Host "[4/6] Cleaning up PATH..." -ForegroundColor Cyan

$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $entries = $userPath -split ";" | Where-Object { $_ -ne "" }
    $cleaned = $entries | Where-Object {
        -not ($_ -like "*\Python*\Scripts" -and $_ -like "*$env:USERNAME*")
    }
    if ($cleaned.Count -lt $entries.Count) {
        $newPath = ($cleaned -join ";")
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "       Removed Plutus Scripts directory from PATH." -ForegroundColor DarkGray
    } else {
        Write-Host "       PATH is clean." -ForegroundColor DarkGray
    }
}

# -- Step 5: Clean up Application Files -------------------------------------

Write-Host "[5/6] Cleaning up app files..." -ForegroundColor Cyan

$plutusDir = "$env:USERPROFILE\.plutus"
if (Test-Path $plutusDir) {
    Write-Host ""
    $confirmation = Read-Host "       Delete config, memory and settings at $plutusDir? [y/N]"
    if ($confirmation -eq 'y' -or $confirmation -eq 'Y') {
        Remove-Item -Path $plutusDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "       Removed: $plutusDir" -ForegroundColor DarkGray
    } else {
        Write-Host "       Kept: $plutusDir" -ForegroundColor Yellow
    }
} else {
    Write-Host "       No config directory found." -ForegroundColor DarkGray
}

# -- Step 6: Optional Workspace Cleanup --------------------------------------

$workspaceDir = "$env:USERPROFILE\plutus-workspace"
if (Test-Path $workspaceDir) {
    Write-Host "[6/6] Workspace cleanup..." -ForegroundColor Cyan
    Write-Host ""
    $confirmation = Read-Host "       Delete workspace (projects and data) at $workspaceDir? [y/N]"
    if ($confirmation -eq 'y' -or $confirmation -eq 'Y') {
        Remove-Item -Path $workspaceDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "       Workspace deleted." -ForegroundColor DarkGray
    } else {
        Write-Host "       Your data is safe at $workspaceDir" -ForegroundColor DarkGray
    }
} else {
    Write-Host "[6/6] No workspace folder found." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  ==============================" -ForegroundColor DarkGray
Write-Host "  Plutus has been successfully uninstalled." -ForegroundColor Green
Write-Host "  ==============================" -ForegroundColor DarkGray
Write-Host ""
Read-Host "Press Enter to exit"
