@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

rem ==================================================================
rem  Chay may ao Android (AVD/QEMU) tren Windows — KHONG can Android
rem  Studio, KHONG can PowerShell.
rem
rem  Yeu cau: Java 17+ (Temurin: https://adoptium.net)
rem  Usage:
rem     scripts\dev_avd_windows.bat create   :: tai SDK, tao emu1/emu2
rem     scripts\dev_avd_windows.bat start    :: mo 2 may ao
rem     scripts\dev_avd_windows.bat stop
rem ==================================================================

set "SDK=%LOCALAPPDATA%\Android\Sdk"
set "CLT=%SDK%\cmdline-tools\latest"
set "IMAGE=system-images;android-35;google_apis;x86_64"
set "CLT_URL=https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip"
set ANDROID_HOME=%SDK%
set ANDROID_SDK_ROOT=%SDK%

if "%~1"=="" goto :usage
if /i "%~1"=="create" goto :create
if /i "%~1"=="start" goto :start
if /i "%~1"=="stop" goto :stop
goto :usage

rem ------------------------------------------------------------------
:ensure_tools
if exist "%CLT%\bin\sdkmanager.bat" exit /b 0

echo [0/4] Tai Android command-line tools ...
if not exist "%SDK%" mkdir "%SDK%"
curl -L --retry 2 -o "%TEMP%\cmdline-tools.zip" "%CLT_URL%"
if errorlevel 1 (
  echo [LOI] Tai cmdline-tools that bai. Kiem tra mang roi chay lai.
  exit /b 1
)
if not exist "%SDK%\cmdline-tools" mkdir "%SDK%\cmdline-tools"
tar -xf "%TEMP%\cmdline-tools.zip" -C "%SDK%\cmdline-tools"
if not exist "%CLT%" (
  move "%SDK%\cmdline-tools\cmdline-tools" "%CLT%" >nul
)
del "%TEMP%\cmdline-tools.zip"
exit /b 0

rem ------------------------------------------------------------------
:create
call :ensure_tools || exit /b 1

where java >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua co Java. Cai JDK 17+ truoc: https://adoptium.net
  exit /b 1
)

echo [1/4] Cai platform-tools + emulator (co the mat vai phut) ...
call "%CLT%\bin\sdkmanager.bat" --sdk_root="%SDK%" "platform-tools" "emulator" "%IMAGE%"
if errorlevel 1 ( echo [LOI] sdkmanager that bai & exit /b 1 )

echo [2/4] Chap nhan license ...
(for /l %%i in (1,1,20) do @echo y) | "%CLT%\bin\sdkmanager.bat" --sdk_root="%SDK%" --licenses >nul 2>nul

echo [3/4] Tao AVD emu1 / emu2 ...
for %%A in (emu1 emu2) do (
  if exist "%USERPROFILE%\.android\avd\%%A.avd" (
    echo    AVD %%A da ton tai
  ) else (
    echo no | call "%CLT%\bin\avdmanager.bat" create avd -n %%A -k "%IMAGE%" -d pixel_6 --force
    call :set_keyboard %%A
  )
)

echo.
echo [4/4] XONG! Mo may ao bang: scripts\dev_avd_windows.bat start
echo      (Neu emulator bao thieu tang toc: bat "Windows Hypervisor Platform"
echo       trong Turn Windows features on or off, roi khoi dong lai may.)
exit /b 0

rem ------------------------------------------------------------------
:set_keyboard
rem Bat hw.keyboard=yes de go duoc phim + sync ban phim
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo    [CANH BAO] Khong co python de bat hw.keyboard — sua tay:
  echo      %USERPROFILE%\.android\avd\%~1.avd\config.ini  ->  hw.keyboard=yes
  exit /b 0
)
%PY% -c "import pathlib,os,sys;p=pathlib.Path(os.environ['USERPROFILE'])/'.android/avd/'/sys.argv[1]/'config.ini';t=p.read_text();t=t.replace('hw.keyboard=no','hw.keyboard=yes') if 'hw.keyboard=' in t else t+'\nhw.keyboard=yes\n';p.write_text(t)" %~1
exit /b 0

rem ------------------------------------------------------------------
:start
if not exist "%SDK%\emulator\emulator.exe" (
  echo Chua cai dat — chay truoc: scripts\dev_avd_windows.bat create
  exit /b 1
)

echo Mo 2 may ao (2 cua so rieng) ...
start "" "%SDK%\emulator\emulator.exe" -avd emu1 -port 5554 -no-audio -no-boot-anim
start "" "%SDK%\emulator\emulator.exe" -avd emu2 -port 5556 -no-audio -no-boot-anim

echo Dang cho boot (co the 1-2 phut lan dau) ...
call :wait_boot 5554
call :wait_boot 5556
echo XONG. Mo app quan ly: scripts\EmuSync.bat
exit /b 0

rem ------------------------------------------------------------------
:wait_boot
set /a waited=0
:wait_boot_loop
set "BOOT="
for /f "delims=" %%R in ('"%SDK%\platform-tools\adb.exe" -s emulator-%~1 shell getprop sys.boot_completed 2^>nul') do set "BOOT=%%R"
if "!BOOT!"=="1" (
  echo    emulator-%~1 ready
  exit /b 0
)
set /a waited+=2
if !waited! geq 300 (
  echo    TIMEOUT emulator-%~1 — mo cua so emulator xem loi.
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto :wait_boot_loop

rem ------------------------------------------------------------------
:stop
for %%S in (5554 5556) do "%SDK%\platform-tools\adb.exe" -s emulator-%%S emu kill 2>nul
echo Da yeu cau tat 2 may ao.
exit /b 0

rem ------------------------------------------------------------------
:usage
echo Usage: %~nx0 {create^|start^|stop}
echo   create : tai SDK + tao 2 AVD (emu1, emu2)
echo   start  : mo 2 AVD
echo   stop   : tat 2 AVD
exit /b 2
