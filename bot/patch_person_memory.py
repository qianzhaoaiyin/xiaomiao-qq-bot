# -*- coding: utf-8 -*-
"""给 kirara 加一个「按人存」的记���作用域，做到跨场合记忆。

问题
----
kirara 自带三个作用域（``kirara_ai/memory/scopes/builtin_scopes.py``）：
``member`` / ``group`` / ``global``。前两个的 ``is_in_scope()`` 第一行就是

    if target_sender.chat_type != query_sender.chat_type:
        return False

而私聊是 ``ChatType.C2C``、群聊是 ``ChatType.GROUP`` —— **同一个人的两套记忆
永远互相看不见**。他在群里说过的事，你私聊问它，它不知道。

``global`` 能跨场合，但它所有人共用一个 ``"global"`` 桶，会把甲的私聊内容
喂给乙，隐私上不能接受。

补丁做了什么
------------
1. 新增 ``PersonScope``：``get_scope_key`` 返回 ``person:{user_id}``，
   ``is_in_scope`` **只比 user_id**，不看 chat_type、不看群号。
   这样既跨场合，又不会把不同人的记忆串在一起。
2. 在 ``memory/scopes/__init__.py`` 导出它。
3. 在 ``entry.py`` 注册 ``person`` 作用域。
4. 把 ``config.yaml`` 的 ``memory.default_scope`` 改成 ``person``。

⚠️ **真正决定成败的是第 4 步之外的另一件事**：工作流里的记忆块
（``internal:chat_memory_query`` / ``internal:chat_memory_store``）
自带 ``scope_type`` 参数，它**优先于**全局默认值。
所以还要把 ``data/workflows/**/*.yaml`` 里那些块的 ``scope_type`` 也改掉，
否则改了配置也没用（这个坑我踩过一次）。

⚠️ 旧记忆文件**不会自动迁移**，``data/memory/c2c_*.json`` 留着但不再被读到。

补丁是**幂等**的：重复运行不会重复改；改之前自动备份。
kirara 升级后跑一次本脚本即可恢复。
"""
import glob
import os
import re
import shutil
import sys
import time

import paths

MARKER = "class PersonScope"
SCOPES_REL = ("kirara_ai/memory/scopes/builtin_scopes.py",)
EXPORT_REL = "kirara_ai/memory/scopes/__init__.py"
ENTRY_REL = "kirara_ai/entry.py"
MEM_BLOCKS = ("internal:chat_memory_query", "internal:chat_memory_store")

PERSON_SCOPE = '''

# ---- patched by xiaomiao-qq-bot：按人存，跨场合共享 ------------------
# 上游三个内置作用域都过不了这一关：member / group 的 is_in_scope() 第一行就是
# `if target.chat_type != query.chat_type: return False`，而私聊是 C2C、群聊是 GROUP，
# 所以同一个人在群里说的话，私聊时完全看不见。
# global 能跨场合，但所有人共用一个 "global" 桶，会把甲的私聊内容喂给乙。
class PersonScope(MemoryScope):
    """按人存：不管他出现在私聊还是哪个群，读写的都是同一本账。

    只按 user_id 判定，不看 chat_type、不看群号——
    跨场合记忆的同时，不同人之间仍然隔离。
    """

    def get_scope_key(self, sender: ChatSender) -> str:
        return f"person:{sender.user_id}"

    def is_in_scope(self, target_sender: ChatSender, query_sender: ChatSender) -> bool:
        return str(target_sender.user_id) == str(query_sender.user_id)
'''


def _site():
    sp = paths.site_packages()
    if sp is None:
        sys.exit("找不到 kirara 的 site-packages，请先跑 scripts\\安装.cmd")
    return sp


def _backup(f):
    bak = f.with_suffix(f.suffix + ".orig-" + time.strftime("%Y%m%d%H%M%S"))
    shutil.copy2(str(f), str(bak))
    return bak


def _wf_files():
    data = paths.kirara_data_dir()
    hits = glob.glob(str(data / "workflows" / "**" / "*.yaml"), recursive=True)
    return [h for h in hits if "memory" in open(h, encoding="utf-8").read()]


def patch(verbose=True):
    sp = _site()
    changed = False

    # 1) 加 PersonScope
    f = sp / SCOPES_REL[0]
    if not f.exists():
        sys.exit("没找到 %s，kirara 版本可能变了" % f)
    src = f.read_text(encoding="utf-8")
    if MARKER in src:
        if verbose:
            print("  [跳过] PersonScope 已存在")
    else:
        bak = _backup(f)
        f.write_text(src.rstrip("\n") + "\n" + PERSON_SCOPE, encoding="utf-8")
        changed = True
        if verbose:
            print("  [补丁] 新增 PersonScope   备份：%s" % bak.name)

    # 2) 导出
    f = sp / EXPORT_REL
    src = f.read_text(encoding="utf-8")
    if "PersonScope" in src:
        if verbose:
            print("  [跳过] __init__ 已导出 PersonScope")
    else:
        bak = _backup(f)
        out = src.replace(
            "from .builtin_scopes import GlobalScope, GroupScope, MemberScope",
            "from .builtin_scopes import GlobalScope, GroupScope, MemberScope, PersonScope")
        out = re.sub(r'__all__ = \[(.*?)\]',
                     lambda m: '__all__ = [%s, "PersonScope"]' % m.group(1).rstrip().rstrip(","),
                     out, count=1, flags=re.S)
        f.write_text(out, encoding="utf-8")
        changed = True
        if verbose:
            print("  [补丁] 导出 PersonScope   备份：%s" % bak.name)

    # 3) 注册
    f = sp / ENTRY_REL
    src = f.read_text(encoding="utf-8")
    if 'register_scope("person"' in src:
        if verbose:
            print("  [跳过] entry.py 已注册 person")
    else:
        bak = _backup(f)
        out = src.replace(
            "from kirara_ai.memory.scopes import GlobalScope, GroupScope, MemberScope",
            "from kirara_ai.memory.scopes import GlobalScope, GroupScope, MemberScope, PersonScope")
        out = out.replace(
            '    memory_manager.register_scope("global", GlobalScope)',
            '    memory_manager.register_scope("global", GlobalScope)\n'
            '    # patched by xiaomiao-qq-bot：按人存，跨场合共享\n'
            '    memory_manager.register_scope("person", PersonScope)')
        f.write_text(out, encoding="utf-8")
        changed = True
        if verbose:
            print("  [补丁] 注册 person 作用域   备份：%s" % bak.name)

    # 4) 工作流里记忆块的 scope_type（真正的开关）
    n = 0
    for wf in _wf_files():
        lines = open(wf, encoding="utf-8").read().split("\n")
        out, cur, hit = [], None, 0
        for ln in lines:
            m = re.match(r"\s*-\s*type:\s*(\S+)", ln)
            if m:
                cur = m.group(1).strip()
            if cur in MEM_BLOCKS:
                m2 = re.match(r"^(\s*)scope_type:\s*(\S+)\s*$", ln)
                if m2 and m2.group(2) != "person":
                    out.append("%sscope_type: person" % m2.group(1))
                    hit += 1
                    continue
            out.append(ln)
        if hit:
            shutil.copy2(wf, wf + ".orig-" + time.strftime("%Y%m%d%H%M%S"))
            open(wf, "w", encoding="utf-8", newline="").write("\n".join(out))
            n += hit
            changed = True
            if verbose:
                print("  [补丁] %s 的记忆块 scope_type -> person（%d 处）"
                      % (os.path.basename(wf), hit))
    if n == 0 and verbose:
        print("  [跳过] 工作流里的 scope_type 已经是 person（或还没装 kirara）")

    if verbose:
        if not changed:
            print("  [OK] 已经是跨场合记忆，无需改动")
        else:
            print()
            print("  改动已写入。**需要重启 kirara 才生效**（pythonw 或 scripts\\停止+一键启动）。")
            print("  旧记忆文件不会自动迁移，老数据留在 data\\memory\\ 里不再被读到。")
    return changed


if __name__ == "__main__":
    print("=" * 58)
    print("  跨场合记忆补丁（PersonScope）")
    print("=" * 58)
    patch()
    import py_compile
    sp = _site()
    for rel in SCOPES_REL + (EXPORT_REL, ENTRY_REL):
        try:
            py_compile.compile(str(sp / rel), doraise=True)
        except Exception as e:
            print("  [自检] %s 语法错误：%s" % (rel, e))
            sys.exit(1)
    print("  [自检] 三个文件语法正常")