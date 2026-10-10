@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
set "GALLERY_PORT=3100"
set "NAPCAT_PORT=6100"
if exist "%ROOT%\.env" for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%\.env") do (
    if /i "%%a"=="GALLERY_PORT" set "GALLERY_PORT=%%b"
    if /i "%%a"=="NAPCAT_WEBUI_PORT" set "NAPCAT_PORT=%%b"
)
title 表情包图库
netstat -na | findstr "LISTENING" | findstr ":%GALLERY_PORT% " >nul
if not errorlevel 1 (
    echo 图库已在运行（端口 %GALLERY_PORT%），不重复启动
    pause
    exit /b
)
echo 启动表情包图库 ...
start "图库" /min "%PY%" "%ROOT%\bot\gallery_server.py"
timeout /t 2 /nobreak >nul
echo 已启动：http://127.0.0.1:%GALLERY_PORT%
echo 图库目录：%ROOT%\表情包   （往里放图即生效，也会在聊天中自动收录）
echo.
pause
