# 贡献指南

感谢你有兴趣改进这个项目。它跑在真实用户的 QQ 上，所以**改动请尽量小而可验证**。

## 开发环境

```bash
git clone https://github.com/qianzhaoaiyin/xiaomiao-qq-bot.git
cd xiaomiao-qq-bot
python -m pip install -e ".[dev]"     # 只装 pyyaml + pre-commit
pre-commit install
```

运行期代码**只用 Python 标准库**，这是刻意的：目标用户是不写代码的人，
多一个依赖就多一个装不上的理由。请保持这一点，新增第三方依赖前先在 issue 里讨论。

## 跑测试

```bash
python -m unittest discover -s tests -v      # 39 例，全部离线，不碰网络
python tools/make_cmd.py --check             # 批处理编码与生成器一致性
python tools/sync_persona_to_workflows.py --check   # 工作流模板与 persona/ 是否同步
python -m compileall -q bot tools tests      # 语法检查
```

改了 `persona/` 下的文件后，**必须**跑一次
`python tools/sync_persona_to_workflows.py` 把新的人设同步进 `config/workflows/*.json`，
否则仓库里的模板和实际行为会不一致（CI 会红）。只想本地生效、不想动仓库里的模板，
直接双击 `scripts\应用人设.cmd` 即可。

CI 会在 Ubuntu + Windows × Python 3.11/3.13 上跑同样这几步，外加密钥扫描。

## 几条硬规矩

1. **不要提交任何密钥、QQ 号、聊天内容或他人图片。**
   `.env`、`kirara/`、`napcat/`、`表情包/*` 都已在 `.gitignore` 里；
   `tests/test_config.py` 会断言配置模板里不含真实 key，CI 也会 grep 一遍。
2. **不要直接编辑 `scripts/*.cmd`。**
   Windows 批处理必须是 GBK + CRLF，普通编辑器会存成 UTF-8 + LF，
   双击就报「命令语法不正确」。请改 `tools/make_cmd.py` 里的文本，然后运行
   `python tools/make_cmd.py` 重新生成；`--check` 会校验一致性。
3. **不要在仓库里写死绝对路径。** 一切路径都从 `bot/paths.py` 出发，
   基于仓库根目录推导，这样整个文件夹可以放在任何盘任何位置。
4. **改动 kirara 行为优先走配置，不要改上游源码。**
   唯一例外是 `bot/patch_sticker_source.py`（因为上游图源已失效），
   它必须保持幂等、必须留备份、必须做语法自检。
5. **提示词改动要附实测对话。** 这个项目很大一部分价值在人设与工具调用的提示词上，
   空谈"更好"没有意义，请贴上改动前后的真实回复。

## 提交规范

- 提交信息用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：
  `feat:` / `fix:` / `docs:` / `test:` / `refactor:` / `chore:`
- 一个提交只做一件事。修 bug 请同时补一个能复现该 bug 的测试。
- 中文注释和文档是这个项目的默认语言，请保持一致。

## 目录速览

| 路径 | 说明 |
|---|---|
| `bot/paths.py` | 所有路径与 `.env` 的唯一入口 |
| `bot/gallery_server.py` | 图库 HTTP 服务（含关键词打分算法） |
| `bot/sticker_collector.py` | 自动收录 + 视觉打标 |
| `bot/provision.py` | 把配置/规则/工作流灌进 kirara 与 NapCat |
| `bot/watchdog.py` | 守护与状态自检 |
| `bot/selftest.py` | 端到端自测 |
| `config/` | 配置模板与工作流定义 |
| `tools/make_cmd.py` | 批处理生成器 |
| `tests/` | 单元测试 |

架构细节见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 行为准则

友善、就事论事。这个项目的用户很多是第一次搭机器人，issue 里的"蠢问题"往往正是文档没写清楚的地方。
