@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 开机静默自启
echo ============================================================
echo    登录 Windows 后自动静默启动机器人（不弹任何窗口）
echo ------------------------------------------------------------
echo    1. 开启开机自启
echo    2. 关闭开机自启
echo    3. 显示 QQ 窗口（掉登录要扫码时用）
echo    0. 退出
echo ============================================================
echo.
set "C="
set /p "C=请选择: "
if "%C%"=="1" goto on
if "%C%"=="2" goto off
if "%C%"=="3" goto showqq
exit /b

:on
"%PY%" "%ROOT%\bot\watchdog.py" --install-autostart
echo.
pause
exit /b

:off
"%PY%" "%ROOT%\bot\watchdog.py" --uninstall-autostart
echo.
pause
exit /b

:showqq
"%PY%" "%ROOT%\bot\watchdog.py" --show-qq
echo.
pause
exit /b
