# -*- coding: utf-8 -*-
"""把 persona/人设.txt 应用到 kirara 的工作流。

用法：编辑 persona\\人设.txt，然后双击 scripts\\应用人设.cmd（或直接跑本文件）。
不用重启 kirara，改完立刻生效。

原理：拉取工作流 -> 只替换 system_prompt 里「# Information」之前的角色设定部分，
后面的系统信息 / 记忆占位符 / 工具说明原样保留 -> PUT 回去。

注意：私聊和群聊走的是不同工作流，所以这里要一次改多条，
否则会出现「改了人设但私聊没变化」的怪现象。
"""
import sys

import paths
from kirara_api import Kirara, KiraraError

# 需要刷人设的工作流；(id, 新名字 or None 表示不改, 新描述 or None)
TARGETS = [
    ("chat/tools", None, None),                       # 私聊 + 群聊主力（带表情包/定时工具）
    ("chat/normal", "聊天 - 自定义人设", "由 persona/人设.txt 生成"),
    ("chat/normal_multimodal", None, None),           # 备用：纯多模态
]


def apply(k: Kirara, wf_id, persona, rename=None, redesc=None):
    try:
        wf = k.get_workflow(wf_id)
    except KiraraError as e:
        print("  [跳过] %s（%s）" % (wf_id, str(e)[:70]))
        return False
    block = next((b for b in wf["blocks"] if b["name"] == "system_prompt"), None)
    if block is None:
        print("  [跳过] %s 里没有 system_prompt 块" % wf_id)
        return False

    old = block["config"]["text"]
    idx = old.find("# Information")
    tail = old[idx:] if idx != -1 else ""
    new = persona + "\n\n" + tail
    block["config"]["text"] = new
    if rename:
        wf["name"] = rename
    if redesc:
        wf["description"] = redesc
    k.put_workflow(wf_id, wf)

    ok = idx != -1
    print("  [%s] %d -> %d 字 %s" % (wf_id, len(old), len(new),
                                    "（占位符与工具说明已保留）" if ok else "⚠️ 没找到 # Information，请检查"))
    return ok


def main():
    if not paths.PERSONA_FILE.exists():
        sys.exit("找不到 %s" % paths.PERSONA_FILE)
    persona = paths.PERSONA_FILE.read_text(encoding="utf-8").strip()
    if not persona:
        sys.exit("人设.txt 是空的")

    k = Kirara()
    try:
        k.login()
    except Exception as e:
        sys.exit("连不上 kirara（%s 起了吗？）：%s" % (paths.KIRARA_BASE, str(e)[:120]))

    print("=" * 58)
    print("  应用人设：%s（%d 字）" % (paths.PERSONA_FILE.name, len(persona)))
    print("=" * 58)
    for wf_id, name, desc in TARGETS:
        apply(k, wf_id, persona, name, desc)
    print()
    print("  完成。直接在 QQ 里发消息就是新设定，不用重启。")


if __name__ == "__main__":
    main()
