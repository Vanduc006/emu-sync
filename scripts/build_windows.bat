@echo off
chcp 65001 >nul
cd /d "%~dp0.."

rem Build EmuSync.exe (khong can PowerShell). Chay TREN Windows.
rem Yeu cau: da chay scripts\install_windows.bat truoc do.

if not exist ".venv\Scripts\python.exe" (
  echo Chua co .venv. Hay chay truoc: scripts\install_windows.bat
  pause
  exit /b 1
)

echo [1/2] Cai pyinstaller ...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 ( pause & exit /b 1 )

echo [2/2] Build EmuSync.exe (mat vai phut) ...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name EmuSync ^
  --paths src ^
  --collect-all uvicorn ^
  --collect-all fastapi ^
  --collect-all webview ^
  --collect-all clr_loader ^
  --hidden-import pythonnet ^
  --hidden-import webview.platforms.edgechromium ^
  --add-data "src/emu_sync/static;emu_sync/static" ^
  --add-data "src/emu_sync/assets;emu_sync/assets" ^
  packaging/launcher.py
if errorlevel 1 ( pause & exit /b 1 )

echo.
echo XONG! File chay: dist\EmuSync\EmuSync.exe (double-click)
pause
