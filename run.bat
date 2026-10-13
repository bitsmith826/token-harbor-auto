@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Token Harbor Auto - 9Router

echo.

:: selalu jalan dari folder script ini
cd /d "%~dp0"

:: ---- 1. CARI PYTHON ----------------------------------------------
set "PYCMD="
where python >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD where py >nul 2>&1 && set "PYCMD=py"

if not defined PYCMD (
    echo [!] Python BELUM terinstall di komputer ini.
    echo     Download Python 3.12 dan install otomatis ...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '%TEMP%\th-python.exe' } catch { exit 1 }"
    if not exist "%TEMP%\th-python.exe" (
        echo [X] Gagal download Python. Cek koneksi internet, lalu coba lagi.
        pause
        exit /b 1
    )
    echo     Install ^(tunggu sampai selesai, sekitar 1 menit^) ...
    "%TEMP%\th-python.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    if !errorlevel! neq 0 (
        echo [X] Install gagal. Install manual dari https://python.org lalu jalankan lagi.
        pause
        exit /b 1
    )
    for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%ProgramFiles%\Python312\python.exe") do (
        if exist "%%~P" set "PYCMD=%%~P"
    )
)

if not defined PYCMD (
    echo [X] Python tidak ditemukan. Install manual dari https://python.org lalu jalankan lagi.
    pause
    exit /b 1
)

:: ---- 2. INSTALL LIBRARY (hanya kalau belum ada) -------------------
"!PYCMD!" -c "import camoufox, playwright, faker" >nul 2>&1
if !errorlevel! equ 0 goto cekbrowser

echo [..] Install library ^(sekali saja^) ...
"!PYCMD!" -m pip install --disable-pip-version-check --no-input -q -r requirements.txt >"%TEMP%\th-pip.log" 2>&1
if !errorlevel! neq 0 (
    echo [X] Gagal install library:
    type "%TEMP%\th-pip.log"
    pause
    exit /b 1
)

:cekbrowser

:: ---- 3. DOWNLOAD BROWSER CAMOUFOX --------------------------------
:: 'camoufox fetch' kadang exit 0 meski gagal ^(GitHub rate limit^),
:: jadi cek folder browsernya langsung. Coba maksimal 3 kali.
set "CAMOUFOX_DIR=%LOCALAPPDATA%\camoufox\camoufox\Cache\browsers\official"

if exist "!CAMOUFOX_DIR!\*" goto mulai

set "coba=0"
:camoufoxcoba
set /a coba+=1
if !coba! gtr 3 goto camoufoxgagal
echo [..] Download browser Camoufox ^(~500 MB, sekali saja^) ...
echo     percobaan !coba! dari 3
echo.
"!PYCMD!" -m camoufox fetch
if exist "!CAMOUFOX_DIR!\*" goto camoufoxok
echo.
echo [!] Download belum selesai ^(mungkin GitHub sedang sibuk^).
if !coba! lss 3 (
    echo     Tunggu 30 detik, lalu coba lagi ...
    timeout /t 30 /nobreak >nul
)
goto camoufoxcoba

:camoufoxgagal
echo [X] Gagal download Camoufox setelah 3x percobaan.
echo     Tutup ini, tunggu beberapa menit, lalu jalankan lagi.
pause
exit /b 1

:camoufoxok
echo [v] Browser siap.
echo.

:: ---- 4. MULAI -----------------------------------------------------
:mulai
"!PYCMD!" main.py
echo.
echo  ============================================================
echo    Selesai. Lihat hasil di result.txt
echo  ============================================================
pause
