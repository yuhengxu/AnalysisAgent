@echo off
REM ============================================================================
REM 能源 AI 平台 · 前后端服务管理脚本（Windows）
REM
REM 用法：
REM   scripts\manage.bat <动作> [目标]
REM   动作：start ^| stop ^| restart ^| status
REM   目标：backend ^| frontend ^| all   (默认 all)
REM
REM 示例：
REM   scripts\manage.bat start
REM   scripts\manage.bat stop backend
REM   scripts\manage.bat restart frontend
REM   scripts\manage.bat status
REM
REM 说明：服务在独立窗口中启动；停止按端口查 PID 后 taskkill。
REM       可改下方 BACKEND_PORT / FRONTEND_PORT。
REM ============================================================================
setlocal
set "ROOT=%~dp0.."
set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"
set "HOST=0.0.0.0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"

set "ACTION=%~1"
set "TARGET=%~2"
if "%TARGET%"=="" set "TARGET=all"

if /i "%ACTION%"=="start"   goto :start
if /i "%ACTION%"=="stop"    goto :stop
if /i "%ACTION%"=="restart" goto :restart
if /i "%ACTION%"=="status"  goto :status
goto :usage

REM --------------------------------------------------------------------------
:start
if /i "%TARGET%"=="backend"  call :start_backend
if /i "%TARGET%"=="frontend" call :start_frontend
if /i "%TARGET%"=="all" ( call :start_backend & call :start_frontend )
goto :eof

:start_backend
echo [manage] 启动后端 (:%BACKEND_PORT%) ...
if not exist "%BACKEND_DIR%\.venv" (
  echo [manage] 创建虚拟环境并安装依赖 ...
  pushd "%BACKEND_DIR%" & python -m venv .venv & call .venv\Scripts\activate.bat & pip install -r requirements.txt -q & popd
)
start "energy-backend" cmd /c "cd /d %BACKEND_DIR% ^&^& call .venv\Scripts\activate.bat ^&^& uvicorn app.main:app --host %HOST% --port %BACKEND_PORT% --reload"
echo [manage] 后端窗口已启动 -> http://localhost:%BACKEND_PORT%  (docs: /docs)
goto :eof

:start_frontend
echo [manage] 启动前端 (:%FRONTEND_PORT%) ...
if not exist "%FRONTEND_DIR%\node_modules" (
  echo [manage] 安装前端依赖 ...
  pushd "%FRONTEND_DIR%" & npm install & popd
)
start "energy-frontend" cmd /c "cd /d %FRONTEND_DIR% ^&^& npm run dev -- --host %HOST% --port %FRONTEND_PORT%"
echo [manage] 前端窗口已启动 -> http://localhost:%FRONTEND_PORT%
goto :eof

REM --------------------------------------------------------------------------
:stop
if /i "%TARGET%"=="backend"  call :stop_port %BACKEND_PORT% 后端
if /i "%TARGET%"=="frontend" call :stop_port %FRONTEND_PORT% 前端
if /i "%TARGET%"=="all" ( call :stop_port %FRONTEND_PORT% 前端 & call :stop_port %BACKEND_PORT% 后端 )
goto :eof

:stop_port
set "PORT=%~1"
set "NAME=%~2"
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo [manage] 停止 %NAME% (PID=%%P) ...
  taskkill /PID %%P /T /F >nul 2>&1
)
if not defined FOUND echo [manage] %NAME% 未在运行
goto :eof

REM --------------------------------------------------------------------------
:restart
call :stop
timeout /t 1 /nobreak >nul
call :start
goto :eof

REM --------------------------------------------------------------------------
:status
call :status_port %BACKEND_PORT% 后端
call :status_port %FRONTEND_PORT% 前端
goto :eof

:status_port
set "PORT=%~1"
set "NAME=%~2"
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo [manage] %NAME%: 运行中 (PID=%%P, 端口 %PORT%)
)
if not defined FOUND echo [manage] %NAME%: 已停止
goto :eof

REM --------------------------------------------------------------------------
:usage
echo 用法: %~nx0 ^<start^|stop^|restart^|status^> [backend^|frontend^|all]
goto :eof
