@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "GALLERY_PORT=3100"
set "NAPCAT_PORT=6100"
if exist "%ROOT%\.env" for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%\.env") do (
    if /i "%%a"=="GALLERY_PORT" set "GALLERY_PORT=%%b"
    if /i "%%a"=="NAPCAT_WEBUI_PORT" set "NAPCAT_PORT=%%b"
)
title 小喵 QQ 机器人 - 停止
echo ============================================================
echo    小喵 QQ 机器人  停止
echo ============================================================
echo.
call :kill %NAPCAT_PORT% NapCat协议端
call :kill 8080 kirara主程序
call :kill %GALLERY_PORT% 表情包图库
echo.
echo    已停止。只结束监听这几个端口的进程及其子进程。
echo ============================================================
echo.
pause
exit /b

:kill
set "_P="
for /f "tokens=5" %%a in ('netstat -nao ^| findstr "LISTENING" ^| findstr ":%~1 "') do set "_P=%%a"
if not defined _P goto kill_none
echo   正在结束 %~2 （端口 %~1, PID %_P%）...
taskkill /PID %_P% /T /F >nul 2>&1
echo   已结束
exit /b

:kill_none
echo   %~2 未在运行（端口 %~1）
exit /b
