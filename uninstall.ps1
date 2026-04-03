# Plutus Uninstaller for Windows
# Usage: powershell -ExecutionPolicy Bypass -File uninstall.ps1

$ErrorActionPreference = "Stop"

# ── Pipeline-safe re-launch ─────────────────────────────────
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
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ── Step 1: Terminate Processes ───────────────────────────

Write-Host "[1/5] Stopping Plutus..." -ForegroundColor Cyan
# Try to kill processes listening on Plutus port (7777)
try {
    $portProcess = Get-NetTCPConnection -LocalPort 7777 -ErrorAction SilentlyContinue
    if ($portProcess) {
        Stop-Process -Id $portProcess.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "       Stopped running Plutus instance." -ForegroundColor DarkGray
    }
} catch {}

# Also kill any VBS/WScript launchers
Get-Process wscript -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*start.vbs*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# ── Step 2: Remove Shortcuts ──────────────────────────────

Write-Host "[2/5] Removing shortcuts..." -ForegroundColor Cyan

$desktopPath = [System.Environment]::GetFolderPath("Desktop")
$startMenuPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"

$shortcuts = @(
    "$desktopPath\Plutus.lnk",
    "$startMenuPath\Plutus.lnk"
)

foreach ($link in $shortcuts) {
    if (Test-Path $link) {
        Remove-Item $link -Force
        Write-Host "       Removed: $link" -ForegroundColor DarkGray
    }
}

# ── Step 3: Uninstall Python Package ──────────────────────

Write-Host "[3/5] Uninstalling Plutus package..." -ForegroundColor Cyan

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

# ── Step 4: Clean up Application Files ────────────────────

Write-Host "[4/5] Cleaning up app files..." -ForegroundColor Cyan

$plutusDir = "$env:USERPROFILE\.plutus"
if (Test-Path $plutusDir) {
    Remove-Item -Path $plutusDir -Recurse -Force
    Write-Host "       Removed configuration directory: $plutusDir" -ForegroundColor DarkGray
}

# ── Step 5: Optional Workspace Cleanup ────────────────────

$workspaceDir = "$env:USERPROFILE\plutus-workspace"
if (Test-Path $workspaceDir) {
    Write-Host ""
    $confirmation = Read-Host "Do you want to delete the workspace folder (projects and data) at $workspaceDir? [y/N]"
    if ($confirmation -eq 'y' -or $confirmation -eq 'Y') {
        Write-Host "[5/5] Removing workspace..." -ForegroundColor Cyan
        Remove-Item -Path $workspaceDir -Recurse -Force
        Write-Host "       Workspace deleted." -ForegroundColor DarkGray
    } else {
        Write-Host "[5/5] Skipping workspace cleanup." -ForegroundColor Yellow
        Write-Host "       Your data is safe at $workspaceDir" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host "  Plutus has been successfully uninstalled." -ForegroundColor Green
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""
Read-Host "Press Enter to exit"
