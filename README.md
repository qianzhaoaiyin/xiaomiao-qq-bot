# 小喵 · QQ 猫娘机器人

一个跑在**你自己 Windows 电脑**上的 QQ 聊天机器人：有人设、有长期记忆、会**主动发表情包**、能**看懂你发的表情包**、会**自动收录**你和群里发表情包、还能定时主动找你聊天。

不是"关键词自动回复"那种玩具——它由大模型驱动，会拒绝、会记仇、会闹脾气，也会在你难过的时候安静陪着。

> 月成本大约 **8～20 元**（按量计费的 API），不需要服务器。

---

## 它能做什么

| 能力 | 说明 |
|---|---|
| 自然对话 + 长期记忆 | 猫娘人设「小喵」，记得你们聊过什么，情绪有连续性 |
| 主动发表情包 | 不用你开口要，气氛到了它自己发；难过/正经问题时不发 |
| 自动收录表情包 | 你和群里发的图会被自动收进图库，并用视觉模型打标签 |
| 看懂你发的图 | 私聊走多模态视觉模型，你发表情包它能读懂内容 |
| 定时主动消息 | 「每天晚上 9 点找我聊聊今天」这类任务可以安排 |
| 有脾气 | 会拒绝、会反驳、会嫌弃，不会无脑顺从 |

实际对话（未修饰）：

```
你：你今天真乖
喵：那当然
   不过你昨天说我胖那事我可还记着

你：过来给我揉揉肩
喵：不要，我正躺着呢
   你自己不会揉吗

你：你是不是机器人啊
喵：你才是机器人
   哪有机器人会饿的

你：我今天被领导当众骂了，好难受
喵：谁啊，当那么多人面说人
   他算老几
   过来，别站那儿了

你：哦
喵：就一个哦？
   我刚让你靠会儿，你就给我这个态度

你：不许再顶嘴了，听话一点
喵：凭什么
   我又不是狗
```

---

## 架构

```
      你的手机 QQ
           │
           ▼
   ┌───────────────┐   反向 WebSocket    ┌──────────────────┐
   │    NapCat     │ ──────────────────► │    kirara-ai     │
   │  (QQ 协议端)   │   ws://127.0.0.1:8080│  (对话/工作流/记忆) │
   │  WebUI :6100  │                     │   WebUI :8080    │
   │  HTTP  :3002  │                     └────────┬─────────┘
   └───────┬───────┘                              │
           │ 收到的每张图都落盘                      │ 工具调用
           ▼                                      ▼
   kirara/data/media/                    ┌──────────────────┐
           │                             │  本地表情包图库     │
           │  每 20 秒扫描 + 视觉打标        │  127.0.0.1:3100  │
           └────────────────────────────►│  表情包/<分类>/*.gif│
                                         └──────────────────┘
           模型：DeepSeek（deepseek-flash 决策 / deepseek-v4-flash-vision-exp 回复+看图）
```

**为什么用本地图库而不是在线表情包接口**：常见的免费图源已经全废了——`api.lolimi.cn` 域名不存在，`fabiaoqing.com` 抓到的图床 `img.soutula.com` 有防盗链（下载 403）。本地图库零月费、不受外网影响，而且图都是你自己攒的，比随机网络图更贴合你的聊天习惯。

---

## 目录结构

```
├── bot/                     本项目自己写的代码
│   ├── paths.py             路径与 .env 统一入口（整个文件夹可放任意位置）
│   ├── gallery_server.py    本地表情包图库 HTTP 服务
│   ├── sticker_collector.py 自动收录 + 视觉打标（"偷表情"）
│   ├── apply_persona.py     把人设.txt 应用到各工作流
│   ├── provision.py         一键把配置/工作流灌进 kirara 与 NapCat
│   ├── patch_sticker_source.py  把插件的失效图源换成本地图库
│   ├── selftest.py          不依赖 QQ 的端到端自测
│   └── kirara_api.py        kirara Web API 封装（含几个易踩的坑）
├── config/
│   ├── kirara.config.yaml   kirara 主配置模板（key 用占位符）
│   ├── rules.yaml           派发规则（私聊/群聊/关键词）
│   ├── napcat.onebot11.json NapCat 反向 WS 配置
│   └── workflows/           工作流定义（chat_tools / 多模态）
├── persona/人设.txt          人设，改这个文件就行
├── scripts/                 Windows 批处理（GBK+CRLF，见下方注意事项）
├── tools/make_cmd.py        生成上面那些 .cmd 的脚本
├── 表情包/                   你的图库（不进版本库）
├── kirara/  napcat/          安装脚本下载的大件（不进版本库）
└── .env                     你的密钥（不进版本库）
```

---

## 安装（Windows，全新电脑）

前置：Windows 10/11、能上 GitHub、一个 [DeepSeek API Key](https://platform.deepseek.com/)、一个**用来当机器人的 QQ 小号**。

```bat
git clone https://github.com/你的用户名/xiaomiao-qq-bot.git
cd xiaomiao-qq-bot
scripts\安装.cmd
```

安装脚本会：下载 kirara-ai（约 210MB）和 NapCat（约 118MB）→ 装三个插件 → 生成 `.env` 并停下来等你填 key。

然后：

1. 用记事本打开 `.env`，填入 `DEEPSEEK_API_KEY`，并把 `KIRARA_WEBUI_PASSWORD` 改成你自己的密码
2. 双击 `scripts\一键启动.cmd`
3. 首次启动打开 <http://127.0.0.1:8080>，把管理密码设成和 `.env` 里一致
4. 双击 `scripts\配置.cmd`（写入工作流、检查插件、跑一次自测）
5. 在 NapCat 窗口（或 <http://127.0.0.1:6100>）扫码登录你的 QQ 小号
6. 把 `.env` 里的 `BOT_QQ` 填成机器人 QQ 号，再跑一次 `scripts\配置.cmd`（这样以后能免扫码快速登录）
7. 双击 `scripts\自测.cmd`，全绿就能用了

> **GitHub 下载慢/失败**：手动去 [kirara-ai releases](https://github.com/lss233/kirara-ai/releases) 下 `Windows-quickstart-*.zip`、[NapCatQQ releases](https://github.com/NapNeko/NapCatQQ/releases) 下 `NapCat.Shell.Windows.Node.zip`，分别改名为 `kirara-quickstart.zip`、`NapCat.Shell.Windows.Node.zip` 放进 `downloads/`，再重跑 `安装.cmd`（它会优先用本地包）。

---

## 日常使用

| 想干什么 | 怎么做 |
|---|---|
| 开机启动 | 双击 `scripts\一键启动.cmd`（想开机自启就把它的快捷方式放进 `shell:startup`） |
| 关掉 | 双击 `scripts\停止.cmd` |
| 改人设 | 编辑 `persona\人设.txt` → 双击 `scripts\应用人设.cmd`（不用重启） |
| 加表情包 | 往 `表情包\开心`、`表情包\晚安` 这类文件夹丢图，立刻生效 |
| 看它偷了哪些图 | 浏览器开 <http://127.0.0.1:3100/stolen> |
| 看图库各分类张数 | <http://127.0.0.1:3100/list> |
| 体检 | 双击 `scripts\自测.cmd` |
| kirara 管理后台 | <http://127.0.0.1:8080> |
| NapCat 管理后台 | <http://127.0.0.1:6100> |

在 QQ 里可以这样用：

```
发个表情包            → 从图库挑一张发给你
三分钟后提醒我喝水      → 建一个一次性定时任务
每天晚上9点找我聊天     → 建一个循环任务
（直接发一张表情包）    → 它能看懂并评论
```

---

## 模型分工（省钱的关键）

| 用途 | 模型 | 说明 |
|---|---|---|
| 判断"要不要发图/建任务" | `deepseek-flash` | 每条消息都会调一次，必须便宜 |
| 私聊/群聊正式回复 | `deepseek-v4-flash-vision-exp` | 视觉模型，所以能看懂你发的图 |
| 给收录的表情打标签 | `deepseek-v4-flash-vision-exp` | 只在新图入库时调一次 |

想再省：把 `config/workflows/chat_tools.json` 里 `llm_chat` 的 `model_name` 改成 `deepseek-flash`，代价是看不懂图。

> `deepseek-v4-flash-vision-exp` 是思考模型，调用时 `max_tokens` 别给太小（低于 100 会出现正文为空、内容全在 `reasoning_content` 里的情况）。

---

## 提示词工程：几个真实踩过的坑

这些坑都已经在 `config/workflows/chat_tools.json` 里处理好了，你自己改人设时请注意：

1. **写"不要顺从"会用力过猛**。加了"会拒绝"之后，用户明确说"发个表情包"它回「不发 / 凭什么你说发就发」。必须同时写例外条款：*明确开口要图时一定要给，可以嘴上嫌弃*。
2. **工具结果会让模型打破第四面墙**。它会说出「那个图是系统塞给我的」。需要在提示词里立铁律：禁止提"系统/工具/自动/生成"，禁止解释或评论发图这件事本身。
3. **模型会自己打方括号占位符**，比如正文里冒出 `[表情包]`（模仿 QQ 的显示方式）。这不是接口渲染的，必须显式禁止。
4. **难过的时候别发图**。不写这条，它会在你说"被领导骂了"的时候甩一张搞笑表情过来。

---

## 故障排查

| 症状 | 处理 |
|---|---|
| 完全不回消息 | 多半是 QQ 掉登录。重跑 `一键启动.cmd` 并扫码；确认主程序窗口有 `OneBot ... Connected` |
| 文字能回、图发不出 | 图库没起（`启动图库.cmd`），或图库是空的（先在 QQ 里发几张图让它收） |
| 说"发个表情包"只回文字 | 工具由模型决定调用，偶发不触发，重发一次即可 |
| 回复里出现 `[表情包]`、"系统"等字眼 | 提示词被改坏了，用 `git checkout config/workflows/` 还原后重跑 `配置.cmd` |
| 改了人设没生效 | 确认改的是 `persona\人设.txt`，并且跑了 `应用人设.cmd` |
| 脚本双击报"命令语法不正确" | `.cmd` 被存成 UTF-8 了。改 `tools\make_cmd.py` 后重跑它生成（必须 GBK+CRLF） |
| NapCat 端口不是 6100 | 多开时它会自动递增。跑一次 `配置.cmd` 会把端口钉死 |
| 图片下载慢/超时 | 本机 DNS 若是 `8.8.8.8`/`4.2.2.1`，国内站点会解析到海外节点。建议改 `223.5.5.5` / `119.29.29.29` |

排查利器：`bot\selftest.py` 会逐项检查图库、插件、规则、模型、对话链路，并给出失败原因。

---

## 已知限制与风险（务必先看）

- **非官方协议端**：NapCat 不是腾讯官方接入方式，存在**账号被风控或封禁**的可能。请只用小号，不要用有重要联系人和资料的主号。
- **登录态会过期**：掉线后需要重新扫码。填好 `.env` 的 `BOT_QQ` 可以让它尝试免扫码快速登录，但不保证成功。
- **不是服务器**：机器人跑在你电脑上，关机/睡眠/断网就离线。
- **群聊默认会回复每一条消息**（规则里带 `fallback`）。这在活跃群里既费钱又扰民，建议把 `config/rules.yaml` 里 `chat_normal` 的 `fallback` 去掉，只保留 `/chat` 前缀或被@触发。
- **隐私**：自动收录会把别人在群里发的图存到你本地。自用没问题，**不要二次分发**，也不要提交到 git（`.gitignore` 已经排除整个 `表情包/`）。
- **默认口令**：`config/napcat.onebot11.json` 与 `config/kirara.config.yaml` 里的 OneBot access_token 是同一个默认值，只用于本机回环通信。想更安全就把两处同时改成随机串。
- 本项目与腾讯、DeepSeek 均无关联。

---

## 致谢

站在这些上游项目的肩膀上：

- [kirara-ai](https://github.com/lss233/kirara-ai)（AGPL-3.0）—— 对话框架、工作流、记忆
- [NapCatQQ](https://github.com/NapNeko/NapCatQQ)（GPL-3.0）—— QQ 协议端
- `chatgpt-mirai-qq-bot-onebot-adapter` / `-scheduler` / `-api-collection` —— kirara 插件
- [DeepSeek](https://platform.deepseek.com/) —— 对话与视觉模型

本仓库只包含自己编写的胶水代码与配置模板，**不再分发任何上游二进制或源码**，安装时从官方发布页下载。

## License

[MIT](LICENSE)
