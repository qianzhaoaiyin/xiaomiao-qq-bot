# -*- coding: utf-8 -*-
"""给 OneBot 适配器补上「拟人化发送」—— 让分条之间有停顿。

现状
----
``im_onebot_adapters/adapter.py`` 的 ``send_message()`` 里其实**已经有**基础延时：

    duration = max(text_length * 0.1, 1) + random.uniform(0.5, 1.5)
    await asyncio.sleep(duration)

而且每个 ``<break>`` 分出来的段都是独立 flush，所以分条之间本来就在等。
缺的只有三样（思路来自 pinganbbOvO/ai-companion-kit 的 Humanizer）：

1. **偶尔来一次长停顿** —— 像在走神 / 被打断 / 在想要不要回
2. **深夜变慢** —— 2:00~7:00 整体 ×1.6，半睡半醒
3. **单次最多拆几条** —— 模型一激动能拆出十几条，把群刷爆

⚠️ **只做停顿，不做「正在输入」上报。**
频繁调 ``set_input_status`` 本身就是腾讯风控的触发点之一
（ai-companion-kit 教程第十三章：一天上报 175 次被限速，服务端直接不回包）。

全部参数走环境变量，改完重启 kirara 即生效，不用再动代码：

    HUMANIZE_ENABLED=1              总开关，设0 关掉
    HUMANIZE_LONG_GAP_CHANCE=0.22   长停顿概率
    HUMANIZE_LONG_GAP_MIN=3         长停顿最少几秒
    HUMANIZE_LONG_GAP_MAX=9         长停顿最多几秒
    HUMANIZE_NIGHT_FROM=2 / _TO=7   深夜时段
    HUMANIZE_NIGHT_FACTOR=1.6       深夜变慢倍数
    HUMANIZE_MAX_SEGMENTS=6         单次最多拆几条
    HUMANIZE_MAX_DELAY=12           单条最长等几秒（封顶）

补丁是**幂等**的：重复运行不会重复改；改之前自动备份。
"""
import os
import shutil
import sys
import time

import paths

MARKER = "def humanize_delay"
TARGET_REL = "im_onebot_adapters/adapter.py"

IMPORTS_OLD = """from typing import Dict, Optional, Set, Any, List
import asyncio
import functools
import random
import time
from urllib.parse import urlparse"""
IMPORTS_NEW = """from typing import Dict, Optional, Set, Any, List
import asyncio
import functools
import os
import random
import time
from datetime import datetime
from urllib.parse import urlparse"""

HELPER = '''

# ---- patched by xiaomiao-qq-bot：拟人化发送参数 ----------------------
# 上游本来就有基础延时（字数 * 0.1 + random(0.5, 1.5) 秒），
# 但少了「偶尔来一次长停顿」和「深夜变慢」这两个最像人的特征。
# 全部走环境变量，改完重启 kirara 即生效。
# 注意：只做停顿，不做「正在输入」上报 —— 频繁 set_input_status 本身是风控触发点。
HUMANIZE_ENABLED = os.environ.get("HUMANIZE_ENABLED", "1") != "0"
HUMANIZE_LONG_GAP_CHANCE = float(os.environ.get("HUMANIZE_LONG_GAP_CHANCE", "0.22"))
HUMANIZE_LONG_GAP_MIN = float(os.environ.get("HUMANIZE_LONG_GAP_MIN", "3"))
HUMANIZE_LONG_GAP_MAX = float(os.environ.get("HUMANIZE_LONG_GAP_MAX", "9"))
HUMANIZE_NIGHT_FROM = int(os.environ.get("HUMANIZE_NIGHT_FROM", "2"))
HUMANIZE_NIGHT_TO = int(os.environ.get("HUMANIZE_NIGHT_TO", "7"))
HUMANIZE_NIGHT_FACTOR = float(os.environ.get("HUMANIZE_NIGHT_FACTOR", "1.6"))
HUMANIZE_MAX_SEGMENTS = int(os.environ.get("HUMANIZE_MAX_SEGMENTS", "6"))
HUMANIZE_MAX_DELAY = float(os.environ.get("HUMANIZE_MAX_DELAY", "12"))


def humanize_delay(text_length: int) -> float:
    """算这一条消息发出去之前该等多久。"""
    base = max(text_length * 0.1, 1) + random.uniform(0.5, 1.5)
    if HUMANIZE_LONG_GAP_CHANCE > 0 and random.random() < HUMANIZE_LONG_GAP_CHANCE:
        base += random.uniform(HUMANIZE_LONG_GAP_MIN, HUMANIZE_LONG_GAP_MAX)
    hour = datetime.now().hour
    if HUMANIZE_NIGHT_FROM <= hour < HUMANIZE_NIGHT_TO:
        base *= HUMANIZE_NIGHT_FACTOR
    return min(base, HUMANIZE_MAX_DELAY)

'''

FLUSH_OLD = """                # 计算延时
                duration = max(text_length * 0.1, 1) + random.uniform(0.5, 1.5)
                await asyncio.sleep(duration)"""
FLUSH_NEW = """                # 计算延时（patched：基础延时 + 偶尔长停顿 + 深夜变慢）
                if HUMANIZE_ENABLED:
                    duration = humanize_delay(text_length)
                else:
                    duration = max(text_length * 0.1, 1) + random.uniform(0.5, 1.5)
                await asyncio.sleep(duration)"""

LOOP_OLD = """            for segment in segments:
                # 判断是否需要flush
                if segment.type in ("text", "record", "video", "rps", "dice", "shake", "poke", "share", "contact", "location"):
                    await flush()
                    buffer = [segment]"""
LOOP_NEW = """            sent_groups = 0
            for segment in segments:
                # 判断是否需要flush
                if segment.type in ("text", "record", "video", "rps", "dice", "shake", "poke", "share", "contact", "location"):
                    # patched：超过条数上限就把后面的并进上一条，不再单独发
                    if sent_groups >= HUMANIZE_MAX_SEGMENTS:
                        if buffer and segment.type == "text":
                            tail = segment.data.get("text", "")
                            try:
                                buffer[-1].data["text"] = buffer[-1].data.get("text", "") + "\\n" + tail
                                text_length += len(tail)
                            except Exception:
                                buffer.append(segment)
                            continue
                    await flush()
                    buffer = [segment]
                    sent_groups += 1"""


def find_target():
    sp = paths.site_packages()
    if sp is None:
        sys.exit("找不到 kirara 的 site-packages，请先跑 scripts\\安装.cmd")
    f = sp / TARGET_REL
    if not f.exists():
        sys.exit("没找到 %s，插件版本可能变了。" % f)
    return f


def patch(verbose=True):
    f = find_target()
    src = f.read_text(encoding="utf-8")
    if MARKER in src:
        if verbose:
            print("  [跳过] 拟人化发送补丁已经在了")
        return False

    missing = [name for name, old in
               (("imports", IMPORTS_OLD), ("flush", FLUSH_OLD), ("loop", LOOP_OLD))
               if old not in src]
    if missing:
        sys.exit("适配器结构和预期不一致，找不到：%s。\n"
                 "插件可能升级了，请提 issue 并附上版本。" % "、".join(missing))

    out = src.replace(IMPORTS_OLD, IMPORTS_NEW, 1)
    out = out.replace(FLUSH_OLD, FLUSH_NEW, 1)
    out = out.replace(LOOP_OLD, LOOP_NEW, 1)
    # 辅助函数插在 import 之后、class 之前
    anchor = "\n\nclass OneBotAdapter"
    if anchor in out:
        out = out.replace(anchor, HELPER + "\nclass OneBotAdapter", 1)
    else:
        out += HELPER

    bak = f.with_suffix(".py.orig-" + time.strftime("%Y%m%d%H%M%S"))
    shutil.copy2(str(f), str(bak))
    f.write_text(out, encoding="utf-8")
    if verbose:
        print("  [补丁] 拟人化发送已启用   备份：%s" % bak.name)
        print("         长停顿 %d%%概率 多停 %g~%g 秒；深夜 %d:00-%d:00 慢 %g 倍；单次最多 %d 条"
              % (22, 3, 9, 2, 7, 1.6, 6))
        print("         参数走环境变量，改完重启 kirara 生效")
    return True


if __name__ == "__main__":
    print("=" * 58)
    print("  拟人化发送补丁")
    print("=" * 58)
    patch()
    import py_compile
    try:
        py_compile.compile(str(find_target()), doraise=True)
        print("  [自检] 补丁后的文件语法正常")
    except Exception as e:
        print("  [自检] 失败：%s" % e)
        sys.exit(1)