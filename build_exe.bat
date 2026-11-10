@echo off
setlocal
cd /d "%~dp0"

rem ---- locate a Python 3.12 that has tkinter ----
rem 1) %PYTHON% if you set it   2) python on PATH   3) py -3.12   4) default user install
set "PY=%PYTHON%"
if not defined PY set "PY=python"
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 set "PY=py -3.12"
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.12 with tkinter not found.
  echo         Install Python 3.12 and keep "tcl/tk and IDLE" checked,
  echo         or set PYTHON=C:\path\to\python.exe before running this file.
  exit /b 1
)

echo Using: %PY%

echo [1/4] Generating icon...
%PY% make_icon.py || goto :err

echo [2/4] Cleaning old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/4] Building exe (1-3 min)...
%PY% -m PyInstaller --noconfirm --clean --windowed --onedir --name TextToVideo --icon app.ico --add-binary "bin\ffmpeg.exe;bin" --add-binary "bin\ffprobe.exe;bin" --collect-all edge_tts main.py || goto :err

echo [4/4] Renaming output...
%PY% rename_dist.py || goto :err

echo.
echo Done. Ship the whole release folder, not just the exe.
goto :eof

:err
echo.
echo BUILD FAILED - see errors above.
exit /b 1
