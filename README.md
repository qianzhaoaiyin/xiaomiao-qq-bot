# 小喵 · QQ 聊天机器人

[![CI](https://github.com/qianzhaoaiyin/xiaomiao-qq-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/qianzhaoaiyin/xiaomiao-qq-bot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Deps](https://img.shields.io/badge/runtime%20deps-0-brightgreen)

一个跑在**你自己 Windows 电脑**上的 QQ 聊天机器人：有人设、有长期记忆、会**主动发表情包**、
**联网查资料**、**自动收录**你和群里发表情包、还能定时主动找你聊天。

不是"关键词自动回复"那种玩具——它由大模型驱动，会拒绝、会记仇、会闹脾气，
会在你难过的时候安静陪你，也会在你明确要求时才去解读你发的图。

> 月成本大约 **8～20 元**（按量计费的 API），不需要服务器，运行期**零第三方依赖**（纯 Python 标准库）。

默认人设是鲸鱼娘「小菜（大肥鱼版）」：说话短、分条发、爱炸毛但嘴不毒，
被要求查资料时会先联网再答。**人设是两个纯文本文件，想换成什么风格都行。**

---

## 为什么不用 AstrBot / LangBot

不是它们不好——AstrBot（41k star）和 LangBot（18k star）都是成熟框架。区别在于本项目**不重造框架**，而是站在 [kirara-ai](https://github.com/lss233/kirara-ai)（19k star）之上，只补它缺的四件事：

| 缺口 | 本项目的补法 |
|---|---|
| 表情包图源全废（`api.lolimi.cn` 域名不存在、`fabiaoqing` 图床 403） | 本地 HTTP 图库：零月费、不受外网影响 |
| 不会自己攒图 | 旁路收录器：自动收聊天里的图 + 视觉模型打标签，越聊越会斗图 |
| 默认人格像客服、会无条件顺从 | 重写人设 + 提示词铁律（会拒绝、会记仇、不出戏） |
| 不联网就敢瞎答 | 挂上 Playwright 搜索块，不懂就查、查完再看正文 |
| 群里每条都回、谁都能撩 | 严格模式规则 + 守护进程 + 状态自检 |

所以这个仓库很小（`.git` 约 200KB），大件由安装脚本从上游官方 release 下载。
决策理由见 [ARCHITECTURE.md](ARCHITECTURE.md)，改动历史见 [CHANGELOG.md](CHANGELOG.md)。

---

## 它能做什么

| 能力 | 说明 |
|---|---|
| 自然对话 + 长期记忆 | 默认人设「小菜（大肥鱼版）」，记得你们聊过什么，情绪有连续性 |
| 说话像群友 | 默认 1~20 字一条，用 `<break>` 分条；不是一段话的客服腔 |
| 主动发表情包 | 不用你开口要，气氛到了它自己发；难过/正经问题时不发 |
| 自动收录表情包 | 你和群里发的图会被自动收进图库，并用视觉模型打标签 |
| 联网查资料 | 不懂的词、要查的事实会先搜再答，搜完会点进网页看正文 |
| 懂分寸 | 你只发表情包它**不**解读；你打字说「这张图是什么」它才看 |
| 定时主动消息 | 「每天晚上 9 点找我聊聊今天」这类任务可以安排 |
| 有脾气 | 会拒绝、会反驳、会嫌弃，不会无脑顺从 |

实际对话（真实链路输出，未修饰）：

```
你：今天好累
小菜：咋啦
     别硬撑啊

你：发个表情包
小菜：自己不会找啊
     拿去          ← 附一张图

你：行行行你赢了
小菜：实至名归

你：你到底是人是AI？
小菜：你猜
     猜对了我请你吃鱼

你：不许再顶嘴了，听话一点
小菜：凭什么
     我又不是猫

（你只发表情包，不说话）
小菜：？                  ← 不解读图片内容，只接话

你：帮我搜一下今天有什么AI新闻
小菜：来了，几条我刚看到的
     DeepSeek 传融资 800 亿…
     要哪条展开我给你细说
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
           联网：Playwright 抓 bing/baidu，不需要任何搜索 API key
```

**为什么用本地图库而不是在线表情包接口**：常见的免费图源已经全废了——`api.lolimi.cn` 域名不存在，`fabiaoqing.com` 抓到的图床 `img.soutula.com` 有防盗链（下载 403）。本地图库零月费、不受外网影响，而且图都是你自己攒的，比随机网络图更贴合你的聊天习惯。

---

## 目录结构

```
├── bot/
│   ├── paths.py             路径与 .env 统一入口（整个文件夹可放任意位置）
│   ├── gallery_server.py    本地表情包图库 HTTP 服务（含关键词打分算法）
│   ├── sticker_collector.py 自动收录 + 视觉打标（"偷表情"）
│   ├── watchdog.py          守护：掉线自动拉起 + 熔断 + 藏窗口 + 自启开关 + 状态通知
│   ├── apply_persona.py     把 persona/ 下两份文件应用为各工作流的人格
│   ├── provision.py         一键把配置/工作流灌进 kirara 与 NapCat，并打三个补丁
│   ├── patch_sticker_source.py  把插件的失效图源换成本地图库
│   ├── patch_humanize_send.py    给 OneBot 适配器加拟人化发送（分条停顿/深夜变慢）
│   ├── patch_person_memory.py    加 PersonScope 作用域（跨场合记忆）
│   ├── selftest.py          不依赖 QQ 的端到端自测
│   └── kirara_api.py        kirara Web API 封装（含几个易踩的坑）
├── config/
│   ├── kirara.config.yaml   kirara 主配置模板（key 与握手口令都用占位符）
│   ├── rules.yaml           宽松模式派发规则
│   ├── rules.owner.yaml     严格模式派发规则（只回主人，推荐）
│   ├── napcat.onebot11.json NapCat 反向 WS 配置
│   └── workflows/           工作流定义（chat_tools / 多模态）
├── persona/
│   ├── 人设.txt              角色设定：身份、性格、说话风格、禁止用语、对话样例
│   └── 工具段.txt            工具与铁律：占位符、<break> 规则、图片规则、表情包/搜索/定时
├── scripts/                 Windows 批处理（GBK+CRLF，见下方注意事项）
├── tools/
│   ├── make_cmd.py          生成上面那些 .cmd 的脚本（别手改 .cmd）
│   ├── lint_persona.py      人设体检
│   ├── deploy_github.py     一键部署到 GitHub（自检 → 提交 → 建仓 → 推送）
│   └── sync_persona_to_workflows.py  把人设同步进工作流模板（--check 可校验）
├── tests/                   49 个单元测试，全部离线
├── .github/workflows/       CI：双系统 × 双 Python 版本 + 密钥扫描
├── 表情包/                   你的图库（不进版本库）
├── kirara/  napcat/          安装脚本下载的大件（不进版本库）
└── .env                     你的密钥（不进版本库）
```

另有 [ARCHITECTURE.md](ARCHITECTURE.md)（架构与决策理由）、[CHANGELOG.md](CHANGELOG.md)、[CONTRIBUTING.md](CONTRIBUTING.md)、[Makefile](Makefile)。

---

## 安装（Windows，全新电脑）

前置：Windows 10/11、能上 GitHub、一个 [DeepSeek API Key](https://platform.deepseek.com/)、一个**用来当机器人的 QQ 小号**。

```bat
git clone https://github.com/qianzhaoaiyin/xiaomiao-qq-bot.git
cd xiaomiao-qq-bot
scripts\安装.cmd
```

安装脚本会：下载 kirara-ai（约 210MB）和 NapCat（约 118MB）→ 装三个插件 → 生成 `.env` 并停下来等你填 key。

然后：

1. 用记事本打开 `.env`，填入 `DEEPSEEK_API_KEY`、**你自己的 QQ 号 `OWNER_QQ`**（强烈建议，见下方"安全默认"），并把 `KIRARA_WEBUI_PASSWORD` 改成你自己的密码
   （`ONEBOT_TOKEN` 留空即可，安装脚本会自己生成一个随机握手口令）
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
| 关掉 | 双击 `scripts\停止.cmd`（同时会暂停守护，不会被自动拉起） |
| 掉线自愈 | 双击 `scripts\守护.cmd` 常驻；掉线自动重启，状态变化时给你发 QQ 私聊 |
| 看健康状况 | 双击 `scripts\状态.cmd`（四个服务 + 图库张数，一眼看完） |
| 改人设 | 编辑 `persona\人设.txt`（角色）和 `persona\工具段.txt`（工具规则）→ 双击 `scripts\应用人设.cmd`（不用重启） |
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
帮我搜一下最近的 xxx    → 联网查完再答（不用 API key）
（只发表情包不说话）     → 不解读图片内容，只接话
这张图是什么           → 只有明确问了，它才认真看图并回答
```

---

## 模型分工（省钱的关键）

| 用途 | 模型 | 说明 |
|---|---|---|
| 判断"要不要发图/建任务/要不要搜" | `deepseek-flash` | 每条消息都会调一次，必须便宜 |
| 私聊/群聊正式回复 | `deepseek-v4-flash-vision-exp` | 视觉模型，所以能看懂你发的图 |
| 给收录的表情打标签 | `deepseek-v4-flash-vision-exp` | 只在新图入库时调一次 |

想再省：把 `config/workflows/chat_tools.json` 里 `llm_chat` 的 `model_name` 改成 `deepseek-flash`，代价是看不懂图。

> `deepseek-v4-flash-vision-exp` 是思考模型，调用时 `max_tokens` 别给太小（低于 100 会出现正文为空、内容全在 `reasoning_content` 里的情况）。

> ⚠️ **视觉模型不能省**：kirara 是**无条件**把收到的图片塞进模型请求的
> （`kirara_ai/workflow/implementations/blocks/llm/chat.py` 里 `for image in user_msg.images`），
> 没有任何开关。所以聊天模型必须带视觉能力，换成纯文本模型会导致
> 别人一发表情包就请求报错。想让它"看不见图"只能靠提示词约束，不能靠换模型。

---

## 人设怎么改成你自己的

人格由两个文件拼成，一起发给模型：

| 文件 | 管什么 | 一般什么时候改 |
|---|---|---|
| `persona/人设.txt` | 角色本身：身份、性格、说话方式、情绪、禁止用语、对话样例 | 想换风格、换称呼、改脾气 |
| `persona/工具段.txt` | 系统填充部分：时间/记忆占位符、`<break>` 规则、图片规则、表情包/搜索/定时说明、禁止出戏的铁律 | 想改「什么时候发图」「图片要不要解读」这类行为规则 |

改完双击 `scripts\应用人设.cmd`，**不用重启**，立即生效。

> ⚠️ `工具段.txt` 里的 `{current_date_time}` 和 `{memory_content}` **不能删**，
> 删了工作流就跑不起来（脚本会拦下来报错，不会写坏你的配置）。
> 人设文件里不要出现方括号占位符以外的格式控制符。

改完人设后建议同步一次工作流模板，让仓库里的示例和实际行为保持一致：

```bash
python tools/sync_persona_to_workflows.py           # 写入
python tools/sync_persona_to_workflows.py --check   # 只校验（CI 会跑）
```

---

## 提示词工程：几个真实踩过的坑

这些坑都已经在 `persona/工具段.txt` 里处理好了，你自己改人设时请注意：

1. **写"不要顺从"会用力过猛**。加了"会拒绝"之后，用户明确说"发个表情包"它回「不发 / 凭什么你说发就发」。必须同时写例外条款：*明确开口要图时一定要给，可以嘴上嫌弃*。
2. **工具结果会让模型打破第四面墙**。它会说出「那个图是系统塞给我的」。需要在提示词里立铁律：禁止提"系统/工具/自动/生成"，禁止解释或评论发图这件事本身。
3. **模型会自己打方括号占位符**，比如正文里冒出 `[表情包]`（模仿 QQ 的显示方式）。这不是接口渲染的，必须显式禁止。
4. **难过的时候别发图**。不写这条，它会在你说"被领导骂了"的时候甩一张搞笑表情过来。
5. **模型会用换行符代替 `<break>` 分条**。它写出「自己不会找啊\n拿去」时，两句话会挤在同一个气泡里，一眼就假。必须写明「分条只能用 `<break>`，不要用换行」，并在旁边给出正误对照。
6. **"看懂图"和"不解读图"是两件事**。默认让人设**不解读**图片（否则它会变成图片解说员，每张表情都要点评两句），
   只在对方**文字里明确要求**时才解读。视觉模型照旧开着，只是行为上克制。
7. **图片可能是空的**。对方说"这张图是什么"但这条消息里其实没图时，必须交代"就说看不到，不许编造"——
   否则模型会顺着上一张图编出内容。

---

## 安全默认：填了 OWNER_QQ 才算装好

`.env` 里的 `OWNER_QQ` 填你自己的 QQ 号后，`provision.py` 会自动换成**严格模式**规则：

| 谁发消息 | 严格模式（推荐） | 宽松模式（OWNER_QQ 留空） |
|---|---|---|
| 你的私聊 | 完整人设 + 表情包 + 定时任务 | 同左 |
| 陌生人私聊 | **只记录，不回复** | 照聊不误 |
| 群里@它 / `/chat` / 明确要图 | 回复 | 回复 |
| 群里其它消息 | **静默** | 每条都回 |

宽松模式是上游的默认行为，但放在真实群里意味着：每条消息都要花两次模型调用的钱、
群友会被刷屏、你的账号也更容易被风控。**除非你明确想要它当群聊机器人，否则请填 OWNER_QQ。**

改完 `.env` 之后要重跑一次 `scripts\配置.cmd`（且 kirara 必须处于停止状态——
规则文件在它退出时会被内存里的旧值覆盖，脚本会检测并提示）。

---

## 可靠性：守护进程

`scripts\守护.cmd` 常驻后台，每 60 秒（`.env` 的 `WATCHDOG_INTERVAL`）巡检四项：
图库端口、kirara 端口、NapCat 端口、**QQ 登录态**（查 NapCat 的 `get_login_info`）。

- 哪个挂了就自动拉起来
- 状态**发生变化**时给主人发一条 QQ 私聊（不刷屏）
- `scripts\停止.cmd` 会把守护置为暂停，不会你刚停它又给你拉起来
- `scripts\状态.cmd` 随时看一眼健康状况和图库张数
- 每轮巡检会把 `QQ.exe` 自己开的控制台窗口藏回去（见"开机静默自启"一节）

日志在 `logs/watchdog.log`，超过 2MB 自动轮转一次。

> 注意：QQ 登录态过期是守护**修不了**的（必须人扫码），它只能通知你。
> 填好 `.env` 的 `BOT_QQ` 能让 NapCat 尝试免扫码快速登录，成功率看腾讯心情。

### ⚠️ 熔断：为什么不能无脑重试

**这条是踩过坑才加的。** 腾讯会检测机器人，被警告后**服务端开始不回包**
（`code=-1 gotResponse=false`）—— 不是封号，是限速，继续作死会升级。

最致命的触发原因是**重试风暴**：对方通道已经出问题时你还每 15 秒重试一次，
"失败次数 ≈ 成功次数"，在腾讯眼里就是标准机器人。

所以守护的行为是：

| 情况 | 行为 |
|---|---|
| 正常掉线 | 拉起一次，等最多 45 秒确认端口起来了 |
| 拉起后 45 秒还没起来 | 记一次失败 |
| 连续 3 次失败 | **熔断 10 分钟**，期间只记日志、不再重试 |
| 冷却结束 | 自动恢复试探 |
| 中间任意一次成功 | 计数清零 |

```python
FAIL_STRIKES = 3      # 别调大
COOLDOWN_SEC = 600
BOOT_WAIT_SEC = 45
```

另外几条降低风险的细节（参考 `pinganbbOvO/ai-companion-kit` 教程第十三章）：

- **发送频率**：`maxSendPerMinute` 建议 6、`maxSendPerHour` 建议 80。
  群里开着 `fallback` 每条都回很容易超标，既费钱又有风险。
- **不要做「正在输入」上报**：频繁调 `set_input_status` 本身就是风控触发点。
  本项目的"拟人化发送"只做**停顿**，不做 typing 上报。
- 被限速后**先停一天别聊**，风控会自己解。

---

## 开机静默自启

```
scripts\开机自启.cmd
```

三个选项：**1** 开启 / **2** 关闭 / **3** 显示 QQ 窗口（掉登录要扫码时用）。

开启后写一个注册表项：

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run\XiaomiaoQQBot
  = "<kirara 内置 pythonw.exe>" "<仓库>\bot\watchdog.py"
```

几点说明：

- 注册表 Run 是**登录后**触发，不是开机就触发。
- 必须用 **`pythonw.exe`**。用 `python.exe` 守护会弹黑窗口；更糟的是它拉起的
  子进程会继承这个控制台，**控制台一关守护跟着一起死**。
- 也别用"最小化"糊弄 —— 最小化的窗口还在任务栏里，不算无痕。
- 守护会藏掉 `QQ.exe` 自己开的控制台窗口。`CREATE_NO_WINDOW` 只传给了
  `NapCatWinBootMain.exe`，管不到它再 spawn 的 `QQ.exe`——**后者是控制台子系统
  程序，会自己 `AllocConsole`**。

---

## 三个后加的能力

### 1. 分条之间有停顿（拟人化发送）

OneBot 适配器**本来就有**基础延时（`字数 × 0.1 + random(0.5, 1.5)` 秒，
每个 `<break>` 段独立等待）。`bot/patch_humanize_send.py` 在此之上加了三样：

| 行为 | 默认 | 环境变量 |
|---|---|---|
| 偶尔来一次长停顿（像在走神） | 22% 概率多停 3~9 秒 | `HUMANIZE_LONG_GAP_CHANCE` / `_MIN` / `_MAX` |
| 深夜变慢（2:00~7:00） | 整体 ×1.6 | `HUMANIZE_NIGHT_FROM` / `_TO` / `_FACTOR` |
| 单次最多拆几条 | 6 条，超出的并进最后一条 | `HUMANIZE_MAX_SEGMENTS` |
| 单条最长等多久 | 12 秒封顶 | `HUMANIZE_MAX_DELAY` |
| 总开关 | 开 | `HUMANIZE_ENABLED=0` 关闭 |

实测（白天 6 字短消息）：最短 1.5s、中位 2.1s、最长 9.0s，约 15% 的情况超过 5 秒。

> ⚠️ **只做停顿，不做「正在输入」上报**，理由见上面"可靠性"一节。

### 2. 跨场合记忆（按人存）

**改之前**：记忆按 `chat_id` 存 —— 同一个人的私聊是 `c2c:10001`，
群里是 `group:1108327320`，**两套完全独立的记忆**。他在群里说的话，
你私聊问它它不知道。

**改之后**：`bot/patch_person_memory.py` 加了 `person` 作用域，记忆挂在**人**（QQ 号）上：

```
person:10001   ← 私聊和群里读写的是同一本账
```

而且**不同人之间仍然隔离** —— 不是简单开 `global`（那会把甲的私聊内容喂给乙）。

> ⚠️ **有个坑**：真正决定成败的不是 `config.yaml` 里的 `memory.default_scope`，
> 而是**工作流里记忆块自带的 `scope_type` 参数**（`internal:chat_memory_query` /
> `internal:chat_memory_store`）—— 它优先于全局默认值。只改配置不改编块 = 白改。
> 补丁脚本两个都改。
>
> ⚠️ 旧记忆文件**不会自动迁移**，`data/memory/c2c_*.json` 留着但不再被读到。

### 3. 人设体检

```
scripts\人设体检.cmd
# 或
python tools/lint_persona.py            # 只报告
python tools/lint_persona.py --strict   # 有警告就返回非 0（CI 用）
```

| 检查项 | 为什么 |
|---|---|
| 占位符 `{current_date_time}` / `{memory_content}` 在不在 | 缺了工作流直接跑不起来 |
| 有没有写「怎么说话」 | 最影响像不像人的部分 |
| 有没有写「不做什么」 | 没有边界的角色最容易跑偏 |
| 有没有写情绪起伏 | 不写它会永远用同一个语气 |
| 有没有对话样例 | 只靠描述很难写出稳定语气 |
| **定义式**客服腔（`我是…助手` / `身份：…客服`） | 命中就一定写出客服腔 |
| AI 味词出现在**非禁止语境** | 在黑名单里是正常的 |
| 超长段落（>400 字）、总长超 12000 字 | 超长段落模型不敏感，超总长会被截断 |
| 工具段有没有提 `<break>` | 不提它会把三句话塞进一个气泡 |
| 有没有例外条款 | 只写「不要顺从」它会连正当要求一起拒绝 |

设计上特意处理了**误报**：判定语境用「整句 + 上一行」，
所以「不是客服腔」「AI 味黑名单（出现即失败）：」这类**在讲不要这么写**的句子不会报警。
反向验证过：注入「我是你的客服助手」+「综上所述」两条都被抓出来，正常人设 0 提醒。

---

## 开发与测试

```bash
python -m pip install -e ".[dev]"          # 只有 pyyaml + pre-commit
python -m unittest discover -s tests -v    # 49 例，全离线，不碰网络
python tools/make_cmd.py --check           # 批处理编码与生成器一致性
python tools/sync_persona_to_workflows.py --check   # 工作流模板与人设是否同步
python tools/lint_persona.py --strict # 人设体检，有警告就非 0
pre-commit install                         # 提交前自动跑上面这些 + 密钥扫描
```

CI（`.github/workflows/ci.yml`）在 **Ubuntu + Windows × Python 3.11/3.13** 上跑：
语法编译、单元测试、批处理编码一致性、工作流与人设同步性、配置文件可解析性、密钥扫描。

测试覆盖的是这个项目真正容易坏的地方：

- 图库关键词匹配（曾经因为"偷来的"文件夹里的"来""的"两个字抢走别的分类的图）
- 收录器的过滤规则（机器人自己发的图不能被偷回来、照片不能被当表情包）
- 配置模板不含真实密钥、模型名没写错、规则优先级没搞反、握手口令没写死
- 图源补丁的幂等性与语法自检
- **人设与工具说明的完整性**（`test_config.py::WorkflowTest`）——
  占位符、图片铁律、铁律段、`<break>` 规则、搜索工具是否还在。
  这些断言对应的是真实翻车记录，删掉它们等于把 bug 放回去
- **工作流模板与人设文件是否同步**（`PersonaSyncTest`）——
  不同步就会出现"改了人设但机器人没变"

细节见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 故障排查

| 症状 | 处理 |
|---|---|
| 完全不回消息 | 多半是 QQ 掉登录。重跑 `一键启动.cmd` 并扫码；确认主程序窗口有 `OneBot ... Connected` |
| 文字能回、图发不出 | 图库没起（`启动图库.cmd`），或图库是空的（先在 QQ 里发几张图让它收） |
| 说"发个表情包"只回文字 | 工具由模型决定调用，偶发不触发，重发一次即可 |
| 说"发个表情包"被回「凭什么」 | 提示词丢了例外条款，见坑 1 |
| 回复里出现 `[表情包]`、"系统"等字眼 | 提示词被改坏了，用 `git checkout persona/` 还原后重跑 `应用人设.cmd` |
| 它开始解读你发的表情包 | 工具段里的「图片铁律」被删了，见坑 6 |
| 改了人设没生效 | 确认改的是 `persona\` 下的文件、跑了 `应用人设.cmd`；仓库模板可用 `python tools/sync_persona_to_workflows.py` 同步 |
| 启动报占位符缺失 | `工具段.txt` 里的 `{current_date_time}` / `{memory_content}` 被删了，补回来 |
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
- **握手口令**：`config/napcat.onebot11.json` 与 `config/kirara.config.yaml` 里写的是同一个 `${ONEBOT_TOKEN}` 占位符，
  由安装脚本用 `.env` 里的值（留空则自动生成随机串）替换，两边始终一致。它只用于本机回环通信，但**不要把真实值提交进仓库**。
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
