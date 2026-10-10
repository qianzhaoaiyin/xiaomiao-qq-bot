@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 应用人设
echo ============================================================
echo    把 persona\ 下的两份文件应用到机器人
echo ------------------------------------------------------------
echo    用法：
echo      1. 改 persona\人设.txt   —— 角色：身份、性格、说话风格
echo      2. 改 persona\工具段.txt —— 工具规则：发图/ 看图 / 搜索 / 定时
echo      3. 双击本脚本
echo    不用重启 kirara，改完立刻生效。
echo ------------------------------------------------------------
echo    注意：工具段.txt 里的 {current_date_time} 和 {memory_content}
echo    是记忆与时间的占位符，不能删，删了脚本会直接报错。
echo ============================================================
echo.
"%PY%" "%ROOT%\bot\apply_persona.py"
echo.
pause
