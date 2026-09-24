@echo off
chcp 65001 >nul
cd /d "%~dp0.."

rem Double-click de mo emu-sync (Windows).
rem Uu tien .venv (cai bang scripts\install_windows.bat); neu khong co thi dung uv.

if exist ".venv\Scripts\emu-sync.exe" (
  ".venv\Scripts\emu-sync.exe" app %*
  if errorlevel 1 pause
  exit /b 0
)

where uv >nul 2>nul
if errorlevel 1 (
  echo Chua co moi truong .venv va cung khong co 'uv' tren may.
  echo Hay chay truoc: scripts\install_windows.bat
  pause
  exit /b 1
)

uv run emu-sync app %*
if errorlevel 1 pause
