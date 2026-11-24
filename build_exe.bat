@echo off
rem ============================================================
rem  Bambu Smart Tuner - one-click build to single-file EXE
rem  Usage: double-click this file, or run  build_exe.bat
rem  Output: dist\BambuSmartTuner.exe
rem  NOTE: keep this file UTF-8 without BOM; chcp 65001 keeps
rem        Chinese text readable in the console.
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo [1/5] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
    echo     python not found. Install Python 3.9+ and tick "Add to PATH".
    pause & exit /b 1
)
for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%v
echo     Python %PYVER%

echo [2/5] Installing dependencies (PySide6 / PyInstaller)...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo     Install failed. Try a mirror:
    echo     python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause & exit /b 1
)

echo [3/5] Generating icon...
python tools\make_icon.py >nul 2>nul

echo [4/5] Cleaning old build...
taskkill /IM BambuSmartTuner.exe /F >nul 2>nul
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [5/5] Building, about 1-3 minutes...
python -m PyInstaller BambuSmartTuner.spec --noconfirm > build_pyinstaller.log 2>&1
if errorlevel 1 (
    echo     Build failed. Last lines of build_pyinstaller.log:
    powershell -NoProfile -Command "Get-Content build_pyinstaller.log -Tail 25"
    pause & exit /b 1
)

rem Ship the rules file next to the EXE: edit it there, no rebuild needed
if not exist "dist\rules" mkdir "dist\rules"
copy /y "rules\BambuRules.json" "dist\rules\BambuRules.json" >nul
copy /y "README.md" "dist\README.md" >nul 2>nul

echo.
echo ============================================================
echo  BUILD DONE
echo  EXE   : dist\BambuSmartTuner.exe
echo  RULES : dist\rules\BambuRules.json   (edit this copy)
echo ============================================================
pause
