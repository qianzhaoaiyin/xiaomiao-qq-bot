# -*- coding: utf-8 -*-
"""把 persona/ 下的两份文件应用为 kirara 的机器人人格。

用法：编辑 persona\\人设.txt（角色设定）和 persona\\工具段.txt（工具与铁律说明），
     然后双击 scripts\\应用人设.cmd。不用重启 kirara，改完立刻生效。

原理：
  拉取工作流 -> 整段替换 system_prompt 为「人设.txt + 空行 + 工具段.txt」-> PUT 回去。

为什么不按「# Information 切一刀」：
  旧做法只替换角色设定段、原样保留数据库里的工具说明尾巴，
  于是想改「什么时候发图」「图片要不要解读」这类规则就只能手改数据库，
  很容易和人设打架。现在两段都是仓库里的纯文本文件，改哪个改哪个。

注意：私聊和群聊走的是不同工作流，必须一次改多条，
否则会出现「改了人设但私聊没变化」的怪现象。
"""
import sys

import paths
from kirara_api import Kirara, KiraraError

# 需要刷人设的工作流；(id, 新名字 or None 表示不改, 新描述 or None)
TARGETS = [
    ("chat/tools", None, None),                       # 私聊 + 群聊主力（带表情包/搜索/定时工具）
    ("chat/normal", "聊天 - 自定义人设", "由 persona/ 人设.txt + 工具段.txt 生成"),
    ("chat/normal_multimodal", None, None),           # 备用：纯多模态
]


def apply(k: Kirara, wf_id, system_prompt, rename=None, redesc=None):
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
    block["config"]["text"] = system_prompt
    if rename:
        wf["name"] = rename
    if redesc:
        wf["description"] = redesc
    k.put_workflow(wf_id, wf)
    print("  [%s] system_prompt %d -> %d 字" % (wf_id, len(old), len(system_prompt)))
    return True


def main():
    try:
        system_prompt = paths.build_system_prompt()
    except (FileNotFoundError, ValueError) as e:
        sys.exit("人设有问题：%s" % e)

    k = Kirara()
    try:
        k.login()
    except Exception as e:
        sys.exit("连不上 kirara（%s 起了吗？）：%s" % (paths.KIRARA_BASE, str(e)[:120]))

    print("=" * 58)
    print("  应用人设")
    print("  人设 %d 字 + 工具段 %d 字 = %d 字"
          % (len(paths.PERSONA_FILE.read_text(encoding="utf-8").strip()),
             len(paths.TOOLS_FILE.read_text(encoding="utf-8").strip()),
             len(system_prompt)))
    print("=" * 58)
    ok = sum(1 for wf_id, name, desc in TARGETS
             if apply(k, wf_id, system_prompt, name, desc))
    print()
    if ok == len(TARGETS):
        print("  %d/%d 条工作流已更新，直接在 QQ 里发消息就是新设定，不用重启。" % (ok, len(TARGETS)))
    else:
        print("  [警告] 只成功了 %d/%d 条，看上面的输出。" % (ok, len(TARGETS)))


if __name__ == "__main__":
    main()
