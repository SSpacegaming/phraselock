@echo off
setlocal
cd /d "%~dp0"
title PhraseLock - Single EXE Build

echo ============================================================
echo  PhraseLock single-executable build
echo ============================================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found on PATH.
  pause
  exit /b 1
)
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail
if exist tests (
  echo Running tests...
  python -m unittest discover -s tests -v
  if errorlevel 1 goto :fail
)
if not exist icon.ico (
  echo ERROR: icon.ico is missing.
  goto :fail
)
pyinstaller --noconfirm --clean --onefile --noconsole --noupx --name PhraseLock --icon icon.ico --add-data "icon.ico;." --add-data "icon.png;." --hidden-import settings --hidden-import PhraseLockWatchdog --hidden-import win32timezone --hidden-import tray --hidden-import pystray._win32 phrase_lock.py
if errorlevel 1 goto :fail
echo.
echo Build succeeded: %CD%\dist\PhraseLock.exe
echo Copy PhraseLock.exe to a folder with phrases.csv/json/txt if you want to edit phrase files externally.
pause
exit /b 0
:fail
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
