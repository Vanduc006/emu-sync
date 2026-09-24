@echo off
rem Double-click de mo emu-sync (Windows). Can cai truoc: scripts\install_windows.ps1
cd /d "%~dp0.."
where uv >nul 2>nul
if errorlevel 1 (
  echo Chua co 'uv'. Cai bang PowerShell:
  echo   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  pause
  exit /b 1
)
uv run emu-sync app %*
if errorlevel 1 pause
