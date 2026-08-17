@echo off
chcp 65001 > nul
title 구매설치 사업관리 - 웹 UI

echo ================================================
echo   구매설치 사업관리 - React Web UI 시작
echo ================================================
echo.

REM 백엔드 패키지 확인 및 설치
echo [1/3] FastAPI 백엔드 패키지 확인 중...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo     fastapi 설치 중...
    pip install -r backend\requirements.txt -q
)

REM 프론트엔드 패키지 확인 및 설치
echo [2/3] React 프론트엔드 패키지 확인 중...
if not exist "frontend\node_modules" (
    echo     npm install 실행 중...
    cd frontend
    npm install
    cd ..
)

echo [3/3] 서버 시작 중...
echo.

REM 백엔드 시작 (창 없음, 로그: backend.log)
powershell -Command "Start-Process python -ArgumentList '-m uvicorn backend.main:app --reload --port 8000' -WorkingDirectory '%~dp0' -WindowStyle Hidden -RedirectStandardOutput '%~dp0backend.log' -RedirectStandardError '%~dp0backend_err.log'"

REM 백엔드가 준비될 때까지 대기 (최대 30초)
echo   백엔드 준비 대기 중...
set /a COUNT=0
:WAIT_BACKEND
timeout /t 1 /nobreak > nul
curl -s http://localhost:8000/api/health > nul 2>&1
if errorlevel 1 (
    set /a COUNT+=1
    if %COUNT% lss 30 goto WAIT_BACKEND
    echo   경고: 백엔드 응답 없음. 강제 진행합니다.
)

echo.
echo   FastAPI  : http://localhost:8000
echo   React    : http://localhost:5173
echo.
echo   브라우저가 자동으로 열립니다.
echo   종료하려면 이 창을 닫으세요.
echo.

REM 프론트엔드 시작
cd frontend
npm run start
