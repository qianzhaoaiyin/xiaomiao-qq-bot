# -*- coding: utf-8 -*-
"""一键把这个仓库部署到 GitHub：填占位符 → 自检 → 提交 → 建仓 → 推送。

用法（推荐走 scripts\\部署到GitHub.cmd，它会引导你填）：

    python tools/deploy_github.py --owner 你的GitHub用户名
    python tools/deploy_github.py --owner 你的GitHub用户名 --private
    python tools/deploy_github.py --owner xxx --dry-run    # 只做自检和占位符替换预览

设计原则：
  - **推送前必过自检**。密钥、口令、坏编码、人设与工作流不同步，
    这些一旦推上去就要 rewrite history 才能清干净，不如在这里挡住。
  - **不碰你的 git 身份**。user.name / user.email 没配就报错让你配，
    绝不偷偷用某个默认值替你签名。
  - **幂等**。占位符已经是 owner 就跳过替换；remote 已指向同一地址就不重复添加。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "xiaomiao-qq-bot"

# 会把仓库地址写死到文档里的占位符
PLACEHOLDER_FILES = ("README.md", "CONTRIBUTING.md")
PLACEHOLDERS = ("your-name", "你的用户名")


def sh(args, check=True, capture=True):
    p = subprocess.run(args, cwd=str(ROOT), capture_output=capture, text=True,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        out = (p.stdout or "") + (p.stderr or "")
        sys.exit("命令失败：%s\n%s" % (" ".join(args), out.strip()[-800:]))
    return p


def have(cmd):
    return shutil.which(cmd) is not None


def hr(title):
    print()
    print("-" * 62)
    print("  " + title)
    print("-" * 62)


# ------------------------------------------------------------------ 自检
def preflight(skip_tests=False):
    hr("1/5 推送前自检")

    if not skip_tests:
        print("  [跑] 单元测试 ...")
        sh([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
        print("  [过] 单元测试")

    print("  [跑] 工作流模板与人设同步性 ...")
    sh([sys.executable, "tools/sync_persona_to_workflows.py", "--check"])
    print("  [过] 人设同步")

    print("  [跑] 批处理编码 ...")
    sh([sys.executable, "tools/make_cmd.py", "--check"])

    print("  [跑] 密钥扫描 ...")
    p = sh(["git", "grep", "-nIE", r"sk-[A-Za-z0-9]{16,}", "--", ".",
            ":.README.md", ":.CHANGELOG.md"], check=False)
    if p.returncode == 0 and (p.stdout or "").strip():
        sys.exit("仓库里出现了疑似真实 API Key，先清掉再推。\n" + p.stdout)

    p = sh(["git", "grep", "-nIE",
            r'(access_token|"token"|apikey|api_key|secret_key)\s*[:=]\s*"?[A-Za-z0-9_@.-]{8,}',
            "--", "config/"], check=False)
    if p.returncode == 0 and (p.stdout or "").strip():
        sys.exit("config/ 里出现了写死的密钥/口令，先改成 ${...} 占位符。\n" + p.stdout)
    print("  [过] 未发现密钥")


def check_identity():
    hr("2/5 检查 git 身份")
    name = sh(["git", "config", "user.name"], check=False).stdout.strip()
    email = sh(["git", "config", "user.email"], check=False).stdout.strip()
    if not name or not email:
        print("  [!] 你还没配 git 身份，提交会被拒绝。请先执行：")
        print("        git config --global user.name  \"你的名字\"")
        print("        git config --global user.email \"你的邮箱@example.com\"")
        sys.exit(1)
    print("  [ok] %s <%s>" % (name, email))


# ------------------------------------------------------- 占位符 / 身份
def fill_placeholders(owner, repo, dry=False):
    hr("3/5 替换仓库地址占位符")
    base = "https://github.com/%s/%s" % (owner, repo)
    total = 0
    for fname in PLACEHOLDER_FILES:
        p = ROOT / fname
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        new = text
        for ph in PLACEHOLDERS:
            new = new.replace(ph, owner)
        # 顺带把 .git 里没被占位符覆盖的旧地址也统一掉
        new = re.sub(r"https://github\.com/[^/\s]+/%s(?=[./)\s])" % re.escape(repo), base, new)
        if new != text:
            n = sum(text.count(ph) for ph in PLACEHOLDERS)
            total += n
            print("  [改] %-16s 替换 %d 处占位符 -> %s" % (fname, n, owner))
            if not dry:
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new)
        else:
            print("  [ok] %-16s 无占位符" % fname)
    if total == 0:
        print("  地址已经是最终形态，无需改动")
    return base


def check_nothing_unexpected():
    """确认不会把本机垃圾一起推上去。"""
    hr("附加检查：待提交内容")
    p = sh(["git", "status", "--porcelain"], check=False)
    lines = [x for x in p.stdout.splitlines() if x.strip()]
    if not lines:
        print("  工作区干净")
        return
    bad = [x for x in lines
           if re.search(r"(^|/)(\.env|token\.txt|__pycache__|downloads|kirara|napcat)(/|$)", x)
           or x.endswith((".log", ".pyc", ".zip"))]
    for x in lines[:40]:
        print("   ", x)
    if len(lines) > 40:
        print("    ... 共 %d 项" % len(lines))
    if bad:
        sys.exit("待提交内容里有本机垃圾（.env / token / 缓存 / 大件），先处理掉：\n  "
                 + "\n  ".join(bad))


def commit(message):
    hr("4/5 提交")
    p = sh(["git", "status", "--porcelain"], check=False)
    if not p.stdout.strip():
        print("  没有待提交改动，跳过")
        return
    sh(["git", "add", "-A"])
    # 只在有暂存内容时提交，否则 git commit 会返回非 0
    p = sh(["git", "diff", "--cached", "--quiet"], check=False)
    if p.returncode == 0:
        print("  没有待提交改动，跳过")
        return
    sh(["git", "commit", "-m", message])
    print("  [ok] " + sh(["git", "log", "-1", "--pretty=%h %s"], check=False).stdout.strip())


def push(owner, repo, private, base, use_ssh=False):
    hr("5/5 创建仓库并推送")
    if use_ssh:
        remote = "git@github.com:%s/%s.git" % (owner, repo)
    else:
        remote = "https://github.com/%s/%s.git" % (owner, repo)

    cur = sh(["git", "remote", "get-url", "origin"], check=False).stdout.strip()
    if cur == remote:
        print("  origin 已指向 %s" % cur)
    elif cur:
        sh(["git", "remote", "set-url", "origin", remote])
        print("  [改] origin -> %s" % remote)
    else:
        sh(["git", "remote", "add", "origin", remote])
        print("  [加] origin -> %s" % remote)

    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False).stdout.strip() or "main"

    if not have("gh"):
        print()
        print("  [!] 没装 gh（GitHub CLI），无法自动建仓。剩下一步请二选一：")
        print()
        print("      A. 装 gh（之后这个脚本能全自动）：")
        print("         winget install --id GitHub.cli")
        print("         gh auth login")
        print()
        print("      B. 自己在网页建一个空仓库")
        print("         https://github.com/new   （仓库名填 %s，%s勾任何初始化选项）"
              % (repo, "公开" if not private else "私有",))
        print()
        print("  建好后回到这个目录执行：")
        print("         git push -u origin %s" % branch)
        print()
        if not use_ssh and not have_ssh_keys():
            print("  [注意] 本机没有 SSH 密钥，走 HTTPS 推送时 GitHub 要的是 PAT，不是密码：")
            print("         1. 打开 https://github.com/settings/tokens/new")
            print("         2. Note 随便写，Expiration 选个期限，勾选 repo 权限")
            print("         3. 生成后复制那串token，推送时用户名填 %s，密码填 token" % owner)
            print()
        return False

    p = sh(["gh", "auth", "status"], check=False)
    if p.returncode != 0:
        print("  [!] gh 未登录。先执行： gh auth login")
        return False

    exists = sh(["gh", "repo", "view", "%s/%s" % (owner, repo)], check=False)
    if exists.returncode != 0:
        args = ["gh", "repo", "create", "%s/%s" % (owner, repo), "--source=.", "--remote=origin"]
        args.append("--private" if private else "--public")
        args += ["--push", "--description",
                 "跑在自己 Windows 电脑上的 QQ 聊天机器人：人设 + 长期记忆 + "
                 "主动发表情包 + 联网查资料 + 自动收录表情包"]
        sh(args)
        print("  [ok] 仓库已创建并推送")
    else:
        print("  仓库已存在，直接推送")
        sh(["git", "push", "-u", "origin", branch])

    print()
    print("  " + base)
    return True


def have_ssh_keys():
    d = Path(os.path.expanduser("~")) / ".ssh"
    return d.is_dir() and any(d.glob("id_*"))


def main():
    ap = argparse.ArgumentParser(description="一键部署到 GitHub")
    ap.add_argument("--owner", help="你的 GitHub 用户名或组织名")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="仓库名（默认 %s）" % DEFAULT_REPO)
    ap.add_argument("--private", action="store_true", help="建私有仓库（默认公开）")
    ap.add_argument("--dry-run", action="store_true", help="只自检 + 预览占位符替换，不提交不推送")
    ap.add_argument("--skip-tests", action="store_true", help="跳过单元测试")
    ap.add_argument("--ssh", action="store_true",
                    help="用 SSH 地址做 origin（默认 HTTPS，因为多数人没配 SSH 密钥）")
    ap.add_argument("--message", default="feat: 人设拆分为角色与工具两段，接入联网搜索，清除硬编码口令",
                    help="提交信息")
    args = ap.parse_args()

    if not args.owner:
        ap.error("必须给 --owner（你的 GitHub 用户名）")

    print("=" * 62)
    print("  部署到 GitHub：%s/%s（%s）" % (args.owner, args.repo,
                                          "私有" if args.private else "公开"))
    print("=" * 62)

    preflight(skip_tests=args.skip_tests)
    check_identity()
    base = fill_placeholders(args.owner, args.repo, dry=args.dry_run)
    check_nothing_unexpected()

    if args.dry_run:
        hr("dry-run：到此为止")
        print("  自检全过，占位符已%s。去掉 --dry-run 就会真的提交推送。" % ("预览" if args.dry_run else "替换"))
        return 0

    commit(args.message)
    ok = push(args.owner, args.repo, args.private, base, use_ssh=args.ssh)

    print()
    print("=" * 62)
    if ok:
        print("  部署完成：%s" % base)
        print("  记得去仓库 Settings 里确认 CI 首次运行是绿的。")
    else:
        print("  本地已就绪，剩下的建仓/推送需要你补一步（见上面）。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
