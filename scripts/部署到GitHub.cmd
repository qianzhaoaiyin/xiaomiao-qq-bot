@echo off
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY="
for /d %%D in ("%ROOT%\kirara\WPy64-*") do if exist "%%D\python\python.exe" set "PY=%%D\python\python.exe"
if not defined PY set "PY=python"
title 部署到 GitHub
echo ============================================================
echo    把本仓库部署到 GitHub
echo ------------------------------------------------------------
echo    会做这些事：
echo      1. 自检（单元测试 / 人设同步 / 批处理编码 / 密钥扫描）
echo      2. 把README 里的 your-name 占位符换成你的用户名
echo      3. 提交，然后建仓并推送
echo ------------------------------------------------------------
echo    没装 gh（GitHub CLI）的话会提示你怎么装。
echo    没配 git 身份的话会提示你怎么配，不会替你乱签名。
echo ============================================================
echo.
set "OWNER="
set /p "OWNER=你的 GitHub 用户名或组织名（直接回车取消）: "
if not defined OWNER (
    echo 已取消。
    pause
    exit /b
)
echo.
set "VIS="
set /p "VIS=仓库 visibility？输入 public 或 private（默认 public，直接回车用默认）: "
set "PRIV="
if /i "%VIS%"=="private" set "PRIV=--private"
echo.
"%PY%" "%ROOT%\tools\deploy_github.py" --owner "%OWNER%" %PRIV%
echo.
pause
