# Cài đặt emu-sync trên Windows (chạy trong PowerShell, tại thư mục repo):
#   powershell -ExecutionPolicy ByPass -File scripts\install_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Chua co 'uv' — dang cai..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "Tao virtualenv + cai dependencies..." -ForegroundColor Cyan
uv venv
uv pip install -e ".[desktop]"

Write-Host ""
Write-Host "Xong! Cach chay:" -ForegroundColor Green
Write-Host "  - Double-click: scripts\EmuSync.bat"
Write-Host "  - Hoac trong terminal: uv run emu-sync app"
Write-Host ""
Write-Host "Luu y: bat ADB trong trinh gia lap (BlueStacks: Settings > Advanced > Android Debug Bridge;"
Write-Host "LDPlayer/MEmu/Nox thuong da bat san), roi bam 'Tim may ao' trong app."
