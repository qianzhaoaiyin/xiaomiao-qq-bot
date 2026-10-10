# -*- coding: utf-8 -*-
"""项目路径与环境变量的统一入口。

仓库根目录就是运行根目录：所有相对路径都基于本文件所在目录的上一级，
所以整个文件夹可以放在任何盘、任何路径下，克隆下来即可用。
"""
import os
import sys
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parent
ROOT = BOT_DIR.parent

KIRARA_DIR = ROOT / "kirara"          # 由安装脚本下载解压，不进版本库
NAPCAT_DIR = ROOT / "napcat"          # 同上
GALLERY_DIR = ROOT / "表情包"          # 本地图库（不进版本库）
CONFIG_DIR = ROOT / "config"
WORKFLOW_DIR = CONFIG_DIR / "workflows"
PERSONA_DIR = ROOT / "persona"
# 人设拆成两个文件：人设.txt 是角色本身，工具段.txt 是系统填充部分
# （时间/记忆占位符、<break> 规则、图片规则、工具说明）。
# 分开的理由：改工具说明不需要动角色设定，也不会把占位符改坏。
PERSONA_FILE = PERSONA_DIR / "人设.txt"
TOOLS_FILE = PERSONA_DIR / "工具段.txt"
ENV_FILE = ROOT / ".env"
DOWNLOAD_DIR = ROOT / "downloads"

KIRARA_HOST = "127.0.0.1"
KIRARA_PORT = 8080
KIRARA_BASE = "http://%s:%d" % (KIRARA_HOST, KIRARA_PORT)
KIRARA_API = KIRARA_BASE + "/backend-api"

DEFAULT_GALLERY_PORT = 3100
DEFAULT_WEBUI_PASSWORD = "ChangeMe@1234"   # 仅兜底，实际以 .env 里的 KIRARA_WEBUI_PASSWORD 为准


def load_env() -> dict:
    """读 .env（不覆盖已存在的真实环境变量）。"""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    merged = dict(env)
    merged.update({k: v for k, v in os.environ.items() if k in env})
    return merged


def env(key: str, default: str = "") -> str:
    return load_env().get(key) or os.environ.get(key) or default


def gallery_port() -> int:
    return int(env("GALLERY_PORT", str(DEFAULT_GALLERY_PORT)))


def gallery_url() -> str:
    return "http://127.0.0.1:%d" % gallery_port()


def webui_password() -> str:
    return env("KIRARA_WEBUI_PASSWORD", DEFAULT_WEBUI_PASSWORD)


def find_python() -> str:
    """找 kirara 自带的嵌入式 Python（版本号会变，所以用通配）。"""
    for pat in ("WPy64-*/python/python.exe", "WPy64-*/python/python",
                "python/python.exe", "python.exe"):
        hits = sorted(KIRARA_DIR.glob(pat)) if KIRARA_DIR.exists() else []
        if hits:
            return str(hits[0])
    return sys.executable or "python"


def find_pythonw() -> str:
    """找无窗口版（pythonw.exe）。用它拉起的东西**不会弹控制台**。

    为什么必须有这个：用 python.exe 拉起的子进程会继承启动它的那个控制台，
    控制台一关，守护跟着一起死。而"最小化"不算无痕——最小化的窗口还在任务栏里。
    """
    base = find_python()
    cand = Path(base)
    w = cand.with_name("pythonw.exe")
    if w.exists():
        return str(w)
    return base


def autostart_command() -> str:
    """写进注册表 Run 项的启动命令（静默）。"""
    return '"%s" "%s"' % (find_pythonw(), BOT_DIR / "watchdog.py")


def site_packages() -> Path:
    """kirara 嵌入式 Python 的 site-packages 目录。"""
    for pat in ("WPy64-*/python/Lib/site-packages", "python/Lib/site-packages"):
        hits = sorted(KIRARA_DIR.glob(pat)) if KIRARA_DIR.exists() else []
        if hits:
            return hits[0]
    raise FileNotFoundError("找不到 kirara 的 site-packages，请先运行 scripts\\安装.cmd")


def napcat_launcher() -> Path:
    """NapCat 的启动器（不同版本名字可能是 NapCatWinBootMain.exe 或 NapCatBoot.exe）。"""
    if not NAPCAT_DIR.exists():
        raise FileNotFoundError("找不到 napcat 目录，请先运行 scripts\\安装.cmd")
    for name in ("NapCatWinBootMain.exe", "NapCatBoot.exe", "NapCat.Shell.exe"):
        hits = sorted(NAPCAT_DIR.rglob(name))
        if hits:
            return hits[0]
    raise FileNotFoundError("napcat 目录里找不到启动器 exe")


def napcat_config_dir() -> Path:
    """NapCat 的 config 目录（webui.json / onebot11*.json 在这里）。"""
    for pat in ("versions/*/resources/app/napcat/config", "napcat/config", "config"):
        hits = sorted(NAPCAT_DIR.glob(pat)) if NAPCAT_DIR.exists() else []
        if hits:
            return hits[0]
    raise FileNotFoundError("找不到 NapCat 的 config 目录")


def kirara_data_dir() -> Path:
    return KIRARA_DIR / "data"


def ensure_dirs():
    for d in (GALLERY_DIR, DOWNLOAD_DIR):
        d.mkdir(parents=True, exist_ok=True)
    for sub in ("开心", "无语", "疑惑", "安慰", "晚安", "打招呼", "随机", "偷来的"):
        (GALLERY_DIR / sub).mkdir(parents=True, exist_ok=True)


# system_prompt 里不能丢的占位符：丢了机器人就会失忆 / 不知道当前时间
REQUIRED_PLACEHOLDERS = ("{current_date_time}", "{memory_content}")


def build_system_prompt() -> str:
    """人设.txt + 工具段.txt拼成完整的 system_prompt。

    故意做成「整段替换」而不是「切掉 # Information 之前的部分」：
    后者会把工具说明锁死在数据库里，改人设时容易和新设定打架。
    这里两段都是仓库里的纯文本文件，改哪个改哪个。

    缺占位符时直接抛错——宁可让人改文件，也不写坏工作流。
    """
    for f in (PERSONA_FILE, TOOLS_FILE):
        if not f.exists():
            raise FileNotFoundError("缺少 %s" % f)
    persona = PERSONA_FILE.read_text(encoding="utf-8").strip()
    tools = TOOLS_FILE.read_text(encoding="utf-8").strip()
    if not persona:
        raise ValueError("%s 是空的" % PERSONA_FILE.name)
    if not tools:
        raise ValueError("%s 是空的" % TOOLS_FILE.name)
    for ph in REQUIRED_PLACEHOLDERS:
        if ph not in tools:
            raise ValueError("%s 里缺少占位符 %s，会写出跑不起来的工作流"
                             % (TOOLS_FILE.name, ph))
    return persona + "\n\n" + tools
