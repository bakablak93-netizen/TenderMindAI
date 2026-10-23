@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
set "UV_BIN="
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_BIN=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_BIN if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV_BIN=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
if not defined UV_BIN for /f "delims=" %%I in ('where uv 2^>nul') do if not defined UV_BIN set "UV_BIN=%%I"
if not defined UV_BIN (
 echo [ERROR] uv.exe not found. Install once with: winget install --id astral-sh.uv -e
 echo Then close this window and open START_WINDOWS.bat again.
 pause
 exit /b 1
)
"%UV_BIN%" python install 3.12
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" (
 "%UV_BIN%" venv --python 3.12 .venv
 if errorlevel 1 goto fail
)
"%UV_BIN%" pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 goto fail
echo.
echo Open: http://127.0.0.1:8501
echo Stop server: Ctrl+C
echo.
.venv\Scripts\python.exe run.py
pause
exit /b 0
:fail
echo [ERROR] Installation failed. See messages above.
pause
exit /b 1
