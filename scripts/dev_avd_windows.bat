@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

rem ==================================================================
rem  Chay may ao Android (AVD/QEMU) tren Windows — KHONG can Android
rem  Studio, KHONG can PowerShell.
rem
rem  Yeu cau: Java 17+ (Temurin: https://adoptium.net)
rem  License: cmdline-tools moi (23.0) co CLI `android sdk install` TU chap
rem  nhan license (`sdkmanager --licenses` da bi bo) — script dung CLI nay.
rem  Usage:
rem     scripts\dev_avd_windows.bat create   :: tai SDK, tao emu1/emu2
rem     scripts\dev_avd_windows.bat start    :: mo 2 may ao
rem     scripts\dev_avd_windows.bat stop
rem ==================================================================

set "SDK=%LOCALAPPDATA%\Android\Sdk"
set "CLT=%SDK%\cmdline-tools\latest"
set "IMAGE=system-images;android-35;google_apis;x86_64"
set "CLT_URL=https://dl.google.com/android/repository/commandlinetools-win-16111833_latest.zip"
set ANDROID_HOME=%SDK%
set ANDROID_SDK_ROOT=%SDK%

if "%~1"=="" goto :usage
if /i "%~1"=="create" goto :create
if /i "%~1"=="start" goto :start
if /i "%~1"=="stop" goto :stop
goto :usage

rem ------------------------------------------------------------------
:ensure_tools
rem Cmdline-tools 23.0 co `android.exe` (CLI moi, TU chap nhan license) + sdkmanager/avdmanager.
rem Ban cu (19.0, chi co .bat) se lam package bi skip: "license is not accepted" → nang cap.
if not exist "%CLT%\bin\android.exe" goto :download_tools
if not exist "%CLT%\bin\android.bat" goto :download_tools
if not exist "%CLT%\bin\sdkmanager.bat" goto :download_tools
exit /b 0

:download_tools
echo [0/4] Tai Android command-line tools 23.0 ...
if not exist "%SDK%" mkdir "%SDK%"
curl -L --retry 2 -o "%TEMP%\cmdline-tools.zip" "%CLT_URL%"
if errorlevel 1 (
  echo [LOI] Tai cmdline-tools that bai. Kiem tra mang roi chay lai.
  exit /b 1
)
if not exist "%SDK%\cmdline-tools" mkdir "%SDK%\cmdline-tools"
if exist "%SDK%\cmdline-tools\_new" rmdir /s /q "%SDK%\cmdline-tools\_new"
mkdir "%SDK%\cmdline-tools\_new"
tar -xf "%TEMP%\cmdline-tools.zip" -C "%SDK%\cmdline-tools\_new"
if not exist "%SDK%\cmdline-tools\_new\cmdline-tools\bin" (
  echo [LOI] Giai nen cmdline-tools that bai (kiem tra dung luong dia).
  exit /b 1
)
if exist "%CLT%" rmdir /s /q "%CLT%"
if exist "%CLT%" (
  echo [LOI] Khong xoa duoc ban cmdline-tools cu (co the dang mo trong Explorer/CMD).
  echo       Dong cua so dang mo trong "%CLT%" roi chay lai.
  exit /b 1
)
move "%SDK%\cmdline-tools\_new\cmdline-tools" "%CLT%" >nul
rmdir /s /q "%SDK%\cmdline-tools\_new"
del "%TEMP%\cmdline-tools.zip"
if not exist "%CLT%\bin\android.exe" (
  echo [LOI] Khong thay android.exe sau khi giai nen.
  exit /b 1
)
echo    cmdline-tools 23.0 OK
exit /b 0

rem ------------------------------------------------------------------
:sdk_install
rem Cai 1 package SDK (%~1).
rem Cmdline-tools 23.0 co `android.exe` — tu dong chap nhan license khi cai.
rem Luu y: `sdkmanager --licenses` DA BI BO (bao "--licenses option is no longer
rem needed" va khong tao file license) => dung sdkmanager se bi skip package voi
rem thong bao "license is not accepted".
set "ACLI="
if exist "%CLT%\bin\android.exe" set "ACLI=%CLT%\bin\android.exe"
if not defined ACLI if exist "%CLT%\bin\android.bat" set "ACLI=%CLT%\bin\android.bat"
if defined ACLI (
  call "%ACLI%" sdk --sdk="%SDK%" install %~1
  if errorlevel 1 exit /b 1
  exit /b 0
)
rem Fallback cho cmdline-tools cu: ghi file license (tuong duong tra loi "y") roi cai
call :write_licenses
call "%CLT%\bin\sdkmanager.bat" --sdk_root="%SDK%" %~1
if errorlevel 1 exit /b 1
exit /b 0

rem ------------------------------------------------------------------
:write_licenses
rem File license chuan cua Google (~/.android licenses): moi file = dong trong + hash.
if not exist "%SDK%\licenses" mkdir "%SDK%\licenses"
call :write_license android-sdk-license 24333f8a63b6825ea9c5514f83c2829b004d1fee
call :write_license android-sdk-preview-license 84831b9409646a918e30573bab4c9c91346d8abd
call :write_license android-sdk-arm-dbt-license 859f317696f67ef3d7f30a50a5560e7834b43903
call :write_license android-googletv-license 601085b94cd77f0b54ff86406957099ebe79c4d6
call :write_license android-googlexr-license ceff83576aac4f7f37cb98fe189e9fb3c49d3b81
call :write_license google-gdk-license 33b6a2b64607f11b759f320ef9dff4ae5c47d97a
call :write_license intel-android-extra-license d975f751698a77b662f1254ddbeed3901e976f5a
call :write_license mips-android-sysimage-license e9acab5b5fbb560a72cfaecce8946896ff6aab9d
exit /b 0

:write_license
(echo.& echo %~2)> "%SDK%\licenses\%~1"
exit /b 0

rem ------------------------------------------------------------------
:create
call :ensure_tools || exit /b 1

where java >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua co Java. Cai JDK 17+ truoc: https://adoptium.net
  exit /b 1
)

echo [1/4] Cai platform-tools + emulator + system image (lan dau ~5GB, vai phut) ...
call :sdk_install "platform-tools" || exit /b 1
call :sdk_install "emulator" || exit /b 1
call :sdk_install "%IMAGE%" || exit /b 1

rem Kiem tra cai that su thanh cong (tranh loi day chuyen kho hieu o buoc sau)
if not exist "%SDK%\emulator\emulator.exe" (
  echo [LOI] Khong thay %SDK%\emulator\emulator.exe sau khi cai. Xem thong bao phia tren.
  exit /b 1
)

echo [2/4] Tao AVD emu1 / emu2 ...
set "AVDHOME=%USERPROFILE%\.android\avd"
if defined ANDROID_AVD_HOME set "AVDHOME=%ANDROID_AVD_HOME%"
for %%A in (emu1 emu2) do (
  if exist "%AVDHOME%\%%A.avd\config.ini" (
    echo    AVD %%A da ton tai, bo qua
  ) else (
    echo    Tao AVD %%A ...
    echo no | "%CLT%\bin\avdmanager.bat" create avd -n %%A -k "%IMAGE%" -d pixel_6 --force
    if not exist "%AVDHOME%\%%A.avd\config.ini" (
      echo    [LOI] Tao AVD %%A that bai — xem thong bao ngay tren.
      exit /b 1
    )
    call :set_keyboard %%A
  )
)

echo.
echo [4/4] XONG! Mo may ao bang: scripts\dev_avd_windows.bat start
echo      (Neu emulator bao thieu tang toc: bat "Windows Hypervisor Platform"
echo       trong Turn Windows features on or off, roi khoi dong lai may.
echo       Kiem tra: "%SDK%\emulator\emulator.exe" -accel-check)
exit /b 0

rem ------------------------------------------------------------------
:set_keyboard
rem Bat hw.keyboard=yes de go duoc phim + sync ban phim
if not exist "%AVDHOME%\%~1.avd\config.ini" exit /b 0
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo    [CANH BAO] Khong co python de bat hw.keyboard — sua tay:
  echo      %AVDHOME%\%~1.avd\config.ini  -^>  hw.keyboard=yes
  exit /b 0
)
%PY% -c "import pathlib,sys;p=pathlib.Path(sys.argv[1]);t=p.read_text(encoding='utf-8');t=t.replace('hw.keyboard=no','hw.keyboard=yes') if 'hw.keyboard=' in t else t+'\nhw.keyboard=yes\n';p.write_text(t,encoding='utf-8')" "%AVDHOME%\%~1.avd\config.ini"
if errorlevel 1 echo    [CANH BAO] Chua bat duoc hw.keyboard — sua tay: %AVDHOME%\%~1.avd\config.ini
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
