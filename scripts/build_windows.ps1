# Build EmuSync.exe (chay TREN Windows — PyInstaller khong cross-compile):
#   powershell -ExecutionPolicy ByPass -File scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Chua co 'uv' — dang cai..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

uv venv
uv pip install -e ".[desktop,build]"

Write-Host "Dang build EmuSync.exe (mat vai phut)..." -ForegroundColor Cyan
uv run pyinstaller --noconfirm --clean --windowed --name EmuSync `
    --paths src `
    --collect-all uvicorn `
    --collect-all fastapi `
    --collect-all webview `
    --collect-all clr_loader `
    --hidden-import pythonnet `
    --hidden-import webview.platforms.edgechromium `
    --add-data "src/emu_sync/static;emu_sync/static" `
    --add-data "src/emu_sync/assets;emu_sync/assets" `
    packaging/launcher.py

Write-Host ""
Write-Host "Xong! File chay: dist\EmuSync\EmuSync.exe (double-click)" -ForegroundColor Green
Write-Host "Log (khi build --windowed): %LOCALAPPDATA%\emu-sync\emu-sync-app.log"
