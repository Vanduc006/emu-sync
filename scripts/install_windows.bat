@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

echo ==================================================
echo  emu-sync - cai dat moi truong tren Windows
echo  (khong can PowerShell, khong can uv)
echo ==================================================
echo.

rem ---------- 0) adb (neu may chua co) ----------
where adb >nul 2>nul
if errorlevel 1 (
  if exist "tools\platform-tools\adb.exe" (
    echo [0/4] Da co adb trong tools\platform-tools
  ) else (
    echo [0/4] Chua co adb - dang tai Android platform-tools ...
    if not exist tools mkdir tools
    curl -L --retry 2 -o "tools\platform-tools.zip" "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    if errorlevel 1 (
      echo [CANH BAO] Tai platform-tools that bai. Ban co the tai thu cong:
      echo             https://developer.android.com/tools/releases/platform-tools
      echo             va giai nen vao tools\platform-tools
    ) else (
      tar -xf "tools\platform-tools.zip" -C tools
      del "tools\platform-tools.zip"
      echo [0/4] Da cai adb vao tools\platform-tools
    )
  )
) else (
  echo [0/4] Da co adb trong PATH
)

rem ---------- 1) Tim Python ----------
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo [LOI] Khong tim thay Python tren may.
  echo       Tai va cai Python 3.11+ tai: https://www.python.org/downloads/windows/
  echo       Khi cai nho TICH CHON "Add python.exe to PATH", roi chay lai file nay.
  pause
  exit /b 1
)
echo [1/3] Python:
%PY% --version
if errorlevel 1 ( pause & exit /b 1 )

rem ---------- 2) Tao virtualenv ----------
if exist ".venv\Scripts\python.exe" (
  echo [2/3] Da co .venv - bo qua buoc tao moi
) else (
  echo [2/3] Dang tao moi truong ao .venv ...
  %PY% -m venv .venv
  if errorlevel 1 ( echo [LOI] Tao .venv that bai. & pause & exit /b 1 )
)

rem ---------- 3) Cai dependencies ----------
echo [3/3] Dang cai dependencies (lan dau co the mat vai phut) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install -e ".[desktop]"
if errorlevel 1 (
  echo.
  echo [LOI] Cai dependencies that bai. Kiem tra ket noi mang roi chay lai file nay.
  pause
  exit /b 1
)

echo.
echo ==================================================
echo  XONG! Buoc tiep theo:
echo    1. Bat ADB trong trinh gia lap (BlueStacks/LDPlayer/...)
echo    2. Double-click scripts\EmuSync.bat de mo app
echo ==================================================
pause
