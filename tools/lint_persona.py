# -*- coding: utf-8 -*-
"""人设体检：在把设定灌给模型之前，先检查有没有常见毛病。

为什么需要这个：「决定一个 AI 像不像人的主要是提示词，而不是模型」。
所以提示词写坏了要能在提交前就发现，而不是等机器人开始说客服腔才发现。
参考 pinganbbOvO/ai-companion-kit 的 role.js lint()，思路一样。

用法：
    python tools/lint_persona.py            # 体检并打印报告
    python tools/lint_persona.py --strict   # 有警告就返回非 0（CI 用）

退出码：0 = 没警告；1 = 有警告（仅 --strict）；2 = 文件有问题没法检
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "bot"))

import paths  # noqa: E402

# system prompt 里不能丢的占位符
REQUIRED_PLACEHOLDERS = paths.REQUIRED_PLACEHOLDERS

# 出现在这些词所在的「句子」里就不是问题——因为那是在讲"不要这么写"
NEGATION = ("不要", "别", "禁止", "不准", "不能", "不是", "不等于", "别做",
            "出现即失败", "黑名单", "严禁", "避免", "不许")

# 身份自我定义成客服/助手。只有"定义式"写法才算问题——
# 否则「你有 AI 的助手能力」「不是客服腔」这种正常句子会满屏误报。
CS_PATTERNS = [
    (r"我是[^。\n]{0,10}(助手|助理|客服|机器人)", "把自己定义成了「%s」"),
    (r"身份[^\n]{0,14}(助手|助理|客服|机器人)", "身份栏里出现了「%s」"),
    (r"名字[^\n]{0,14}(助手|助理|客服|机器人)", "名字里出现了「%s」"),
    (r"你是一个[^。\n]{0,10}(助手|助理|客服)", "把对方设定成了「%s」"),
    (r"扮演[^。\n]{0,8}(助手|助理|客服)", "要求扮演「%s」"),
]

# 这些是「必须写清楚」的东西，缺一条人设就容易跑偏
MUST_HAVE = [
    (r"说话|语气|口吻|怎么(说|讲)", "没写「怎么说话」——这是最影响像不像人的部分"),
    (r"不|别|禁止|不准|不要", "没写「不做什么」——没有边界的角色最容易跑偏"),
    (r"情绪|生气|开心|烦|傲娇|脾气", "没写情绪起伏——它会永远用同一个语气"),
    (r"示例|样例|例如|Q[：:]|A[：:]", "没有对话样例——只靠描述很难写出稳定的语气"),
]

# 出现即出戏的词
AI_TASTE = ["首先", "其次", "综上所述", "总而言之", "值得注意的是",
            "希望这个回答对你有帮助", "有什么可以帮您", "随时找我",
            "作为一个语言模型", "我理解你的感受", "大家觉得呢"]

MAX_CHARS = 12000        # system prompt 注入上限，超了会被截断
MAX_LINE = 400           # 单段超过这个长度模型不敏感


def _sentence(text, pos):
    """取 pos 所在的整句（以。！？换行 分隔）。"""
    left = max(text.rfind(c, 0, pos) for c in "。！？\n") + 1
    right = len(text)
    for c in "。！？\n":
        i = text.find(c, pos)
        if i != -1:
            right = min(right, i + 1)
    return text[left:right]


def _is_negated(text, pos):
    """这个词是不是出现在「不要这么写」的语境里。

    额外把**上一行**也算进语境：像「AI 味黑名单（出现即失败）：」这种
    标题 + 换行 + 一长串词的写法，关键词和「不要」的提示会落在两行，
    只看当前行必然误报。
    """
    s = _sentence(text, pos)
    line_start = text.rfind("\n", 0, pos) + 1
    prev_start = text.rfind("\n", 0, max(0, line_start - 1)) + 1
    prev = text[prev_start:line_start]
    return any(w in s or w in prev for w in NEGATION)


def lint():
    """返回 (文件是否都在, [(级别, 说明)])。级别是 error / warn。"""
    if not paths.PERSONA_FILE.exists():
        return False, [("error", "找不到 %s" % paths.PERSONA_FILE.name)]
    if not paths.TOOLS_FILE.exists():
        return False, [("error", "找不到 %s" % paths.TOOLS_FILE.name)]

    persona = paths.PERSONA_FILE.read_text(encoding="utf-8")
    tools = paths.TOOLS_FILE.read_text(encoding="utf-8")
    full = persona + "\n\n" + tools
    warns = []

    # 硬性：占位符
    for ph in REQUIRED_PLACEHOLDERS:
        if ph not in tools:
            warns.append(("error", "%s 里缺少占位符 %s，记忆或时间会失效"
                          % (paths.TOOLS_FILE.name, ph)))

    # 长度
    if len(full) > MAX_CHARS:
        warns.append(("warn", "system prompt %d 字，超过 %d 会被截断，"
                             "等于把后面的铁律悄悄丢掉" % (len(full), MAX_CHARS)))
    for i, line in enumerate(full.splitlines(), 1):
        if len(line) > MAX_LINE:
            warns.append(("warn", "第 %d 行有 %d 字，建议拆短（模型对超长段落不敏感）"
                              % (i, len(line))))

    # 必须写清楚的东西
    for pat, msg in MUST_HAVE:
        if not re.search(pat, persona):
            warns.append(("warn", msg))

    # 客服腔：只认定义式写法，且排除禁止语境
    for pat, msg in CS_PATTERNS:
        for m in re.finditer(pat, persona):
            if _is_negated(persona, m.start()):
                continue
            word = re.search(r"(助手|助理|客服|机器人)", m.group(0))
            line_no = persona[:m.start()].count("\n") + 1
            warns.append(("warn", "第 %d 行%s：%s"
                          % (line_no, msg % (word.group(1) if word else "?"),
                             _sentence(persona, m.start()).strip()[:50])))
            break

    # AI 味：所有出现位置里只要有一个不在禁止语境就不算过
    for w in AI_TASTE:
        hits = list(re.finditer(re.escape(w), full))
        if not hits:
            continue
        if any(not _is_negated(full, m.start()) for m in hits):
            bad = next(m for m in hits if not _is_negated(full, m.start()))
            warns.append(("warn", "「%s」出现在非禁止语境里（第 %d 行），建议删掉或改写"
                          % (w, full[:bad.start()].count("\n") + 1)))
            break

    # 工具段专项
    if "<break>" not in tools:
        warns.append(("warn", "工具段没提 <break>——模型会把三句话塞进一个气泡"))
    if "例外" not in persona and "唯一" not in persona:
        warns.append(("warn", "人设里没写「例外条款」——"
                              "只写了「不要顺从」的话，它会连正当要求一起拒绝"))

    return True, warns


def main():
    ap = argparse.ArgumentParser(description="人设体检")
    ap.add_argument("--strict", action="store_true", help="有警告就返回 1")
    args = ap.parse_args()

    print("=" * 62)
    print("  人设体检")
    print("=" * 62)
    ok, warns = lint()
    if not ok:
        for lv, m in warns:
            print("  [致命] %s" % m)
        return 2

    try:
        total = len(paths.build_system_prompt())
    except (FileNotFoundError, ValueError) as e:
        print("  [致命] %s" % e)
        return 2
    print("  拼出来的 system prompt %d 字（上限 %d）" % (total, MAX_CHARS))
    print()

    errors = [w for w in warns if w[0] == "error"]
    others = [w for w in warns if w[0] != "error"]

    if not warns:
        print("  [OK] 没发现问题。")
    else:
        for lv, m in warns:
            print("  [%s] %s" % ("✗ 致命" if lv == "error" else "!  提醒", m))
        print()
        print("  致命 %d 条，提醒 %d 条" % (len(errors), len(others)))

    if errors:
        print()
        print("  有致命问题，别灌进工作流（改了会跑不起来）。")
        return 2
    if others and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())