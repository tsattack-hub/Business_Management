@echo off
setlocal
title Business Management - Web UI

echo ================================================
echo   Business Management - Web UI
echo ================================================
echo.

REM ---- 1) backend packages ----
echo [1/3] Checking backend packages (fastapi)...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo     Installing backend requirements...
    pip install -r "%~dp0backend\requirements.txt" -q
)

REM ---- 2) frontend packages ----
echo [2/3] Checking frontend packages (node_modules)...
if not exist "%~dp0frontend\node_modules" (
    echo     Running npm install...
    pushd "%~dp0frontend"
    call npm install
    popd
)

REM ---- 3) start servers ----
echo [3/3] Starting servers...
echo.

REM Free port 8000 if a previous backend process is still holding it,
REM so a restart always loads the current code.
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

REM Backend runs hidden and inherits G2B_KEY from this window if it was set.
powershell -Command "Start-Process python -ArgumentList '-m','uvicorn','backend.main:app','--port','8000' -WorkingDirectory '%~dp0' -WindowStyle Hidden -RedirectStandardOutput '%~dp0backend.log' -RedirectStandardError '%~dp0backend_err.log'"

echo   Waiting for backend to be ready...
set /a COUNT=0
:WAIT_BACKEND
timeout /t 1 /nobreak >nul
curl -s http://localhost:8000/api/health >nul 2>&1
if errorlevel 1 (
    set /a COUNT+=1
    if %COUNT% lss 30 goto WAIT_BACKEND
    echo   Warning: backend did not respond in time. Check backend_err.log
)

echo.
echo   FastAPI  : http://localhost:8000
echo   React    : http://localhost:5173
echo.
echo   A browser tab opens automatically. Keep this window open.
echo   Press Ctrl+C or close this window to stop.
echo.

REM Frontend in the correct folder (absolute path), foreground.
cd /d "%~dp0frontend"
call npm run start
