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
title 小喵 QQ 机器人 - 一键启动
echo ============================================================
echo    小喵 QQ 机器人  一键启动
echo ------------------------------------------------------------
echo    管理后台   http://127.0.0.1:8080
echo    NapCat     http://127.0.0.1:%NAPCAT_PORT%
echo    表情包图库 http://127.0.0.1:%GALLERY_PORT%/list
echo ============================================================
echo.

netstat -na | findstr "LISTENING" | findstr ":%GALLERY_PORT% " >nul
if errorlevel 1 (
    echo [1/3] 启动 表情包图库 ...
    start "图库" /min "%PY%" "%ROOT%\bot\gallery_server.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [1/3] 图库已在运行，跳过（端口 %GALLERY_PORT%）
)

netstat -na | findstr "LISTENING" | findstr ":8080 " >nul
if errorlevel 1 (
    echo [2/3] 启动 kirara 主程序 ...
    start "kirara" cmd /c "%ROOT%\scripts\_run_kirara.cmd"
    echo       等 15 秒让它把服务拉起来 ...
    timeout /t 15 /nobreak >nul
) else (
    echo [2/3] kirara 已在运行，跳过（端口 8080）
)

netstat -na | findstr "LISTENING" | findstr ":%NAPCAT_PORT% " >nul
if errorlevel 1 (
    echo [3/3] 启动 NapCat 协议端 ...
    set "NAP="
    for /r "%ROOT%\napcat" %%F in (NapCatWinBootMain.exe NapCatBoot.exe) do if exist "%%F" set "NAP=%%F"
    if defined NAP (
        for %%I in ("!NAP!") do start "NapCat" /D "%%~dpI" "%%~dpI%%~nxI"
        echo       等 12 秒 ...
        timeout /t 12 /nobreak >nul
    ) else (
        echo       [!] napcat 目录里找不到启动器，请先跑 scripts\安装.cmd
    )
) else (
    echo [3/3] NapCat 已在运行，跳过（端口 %NAPCAT_PORT%）
)

echo.
echo ============================================================
echo    启动完成。NapCat 还要 10~30 秒把 QQ 登上去。
echo ------------------------------------------------------------
echo    如果 QQ 掉登录了，去 NapCat 窗口或
echo    http://127.0.0.1:%NAPCAT_PORT% 扫码。
echo    主程序窗口里出现 OneBot ... Connected 就说明接通了。
echo.
echo    之后在 QQ 里给机器人发消息即可。
echo ============================================================
echo.
pause
