# 开发用 Makefile（Windows 用户日常请用 scripts\*.cmd，不需要 make）
# CI 也调用这里的 target，保证本地和流水线跑的是同一套检查。

PYTHON ?= python

.PHONY: help test lint compile cmd cmd-check secrets install provision start stop status guard clean-cache

help:
	@echo "可用目标："
	@echo "  make test        运行单元测试（离线，不碰网络）"
	@echo "  make compile     语法编译检查"
	@echo "  make cmd         重新生成 scripts/*.cmd（GBK+CRLF）"
	@echo "  make cmd-check   校验 .cmd 与生成器一致、编码正确"
	@echo "  make secrets     扫描仓库里是否混入密钥"
	@echo "  make lint        compile + cmd-check + secrets 一把梭"
	@echo "  ---- 以下需要本机已安装（Windows）----"
	@echo "  make install     下载 kirara/NapCat 并灌配置"
	@echo "  make provision   只灌配置与工作流"
	@echo "  make start       一键启动"
	@echo "  make stop        停止"
	@echo "  make status      状态报告"
	@echo "  make guard       前台运行守护进程"

test:
	$(PYTHON) -m unittest discover -s tests -v

compile:
	$(PYTHON) -m compileall -q bot tools tests

cmd:
	$(PYTHON) tools/make_cmd.py

cmd-check:
	$(PYTHON) tools/make_cmd.py --check

secrets:
	@bash -c 'if git grep -nIE "sk-[A-Za-z0-9]{16,}" -- . ":!README.md" ":!CHANGELOG.md"; then \
		echo "疑似真实 API Key，请移除后再提交"; exit 1; else echo "未发现密钥"; fi'

lint: compile cmd-check secrets
	@echo "lint 通过"

install:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install.ps1

provision:
	$(PYTHON) bot/provision.py

start:
	cmd //c scripts\\一键启动.cmd

stop:
	cmd //c scripts\\停止.cmd

status:
	$(PYTHON) bot/watchdog.py --once

guard:
	$(PYTHON) bot/watchdog.py

# 只清理 Python 缓存，不动任何用户数据
clean-cache:
	$(PYTHON) -c "import pathlib,shutil;[shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	@echo "已清理 __pycache__"
