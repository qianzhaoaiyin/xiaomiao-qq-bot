# 架构说明

这份文档解释**为什么是这样**，而不只是**是什么**。改代码前请先读完。

## 1. 总体数据流

```
手机 QQ
   │  (腾讯私有协议)
   ▼
NapCat  ──── 反向 WebSocket ────►  kirara-ai
 :6100 WebUI                       :8080 WebUI / Web API
 :3002 OneBot HTTP                 │
   ▲                               │ 派发规则 (rules.yaml)
   │ 收到/发出的每张图都落盘          ▼
kirara/data/media/            工作流 chat:tools
   files/<sha1>.<ext>              ├─ get_message
   metadata/<sha1>.json            ├─ query_memory      (长期记忆)
   ▲                               ├─ system_prompt     (人设 + 工具铁律)
   │ 每 20s 扫描                    ├─ tools             (auto_execute_tools)
   │                               │     └─ deepseek-flash 决策要不要发图/建任务
sticker_collector ──► 表情包/偷来的/  ├─ url_msg           (URL -> 图片消息)
   │  视觉模型打标签                 ├─ send_tools        (先把图发出去)
   ▼                               ├─ concat            (工具结果拼回上下文)
本地 HTTP 图库 :3100 ◄──────────────┤─ llm_chat          (deepseek-v4-flash-vision-exp)
   /random?kw=xxx                  ├─ resp_conv / send_msg
                                   └─ memory_store
```

一条消息的完整旅程：NapCat 收到 → 反向 WS 推给 kirara → 派发规则选工作流 →
`tools` 块让便宜模型决定要不要调工具（发图/建定时任务）→ 调用的话向本地图库要一张图、
下载进媒体库、先发出去 → 工具结果拼进上下文 → 视觉模型生成正式回复 → 发回 QQ → 写记忆。

## 2. 关键决策与理由

### 为什么表情包用本地 HTTP 图库，而不是在线接口

外部免费图源已经全废，而且这类接口本来就不可靠：

| 图源 | 状态 |
|---|---|
| `api.lolimi.cn` | 域名不存在（三个公共 DNS 都是 NXDOMAIN） |
| `fabiaoqing.com` | 能抓到直链，但图床 `img.soutula.com` 防盗链，下载 403 |

本地图库换来三件事：**零月费**、**不受外网波动影响**、**图库内容完全可控**
（用户自己的收藏比随机网络图更贴合他的聊天习惯）。代价是要自己攒图——
所以配了自动收录器，聊着聊着图库就满了。

### 为什么收录器是旁路的，而不是 kirara 插件

kirara 已经把**收到的每一张图**存进 `data/media/files/<sha1>.<ext>`，
元数据里有 `source` 和 `references`（来源会话）。这意味着"偷表情"所需的信息全都在磁盘上，
不需要 hook 消息流。旁路实现的好处：

- 不改上游一行代码，kirara 升级不会冲掉它
- 收集器崩了不影响聊天
- 想彻底移除就删掉一个文件

代价是有两个必须绕过的坑（都已在代码里处理并有测试覆盖）：

1. **机器人自己发出去的图，`source` 同样是 `im_message`**。
   只看这个字段会把自己发的表情又偷回来，形成回环。
   过滤方式：`references` 为空的一律跳过；内容 sha1 已存在于图库的一律跳过
   （kirara 的 media_id 就是文件内容 sha1，正好能用来比对）。
2. **别人发的照片、截图不是表情包**。用 1.5MB 体积上限挡掉。

### 为什么给上游插件打补丁，而不是自己写插件

`api_collection` 提供了 `random_emoji` / `sougou_image_search` 两个块，
工作流和提示词都已经在用它们。自己写一个同功能的 kirara 插件需要处理块注册、
entry point、与工作流的兼容，收益却不明显——真正的差异只在"图从哪来"。

所以 `bot/patch_sticker_source.py` 只替换取图函数，并强制三条纪律：
**幂等**（重复运行是 no-op）、**留备份**（`.orig-<时间戳>`）、**语法自检**（改完立刻 `py_compile`）。
CI 里的 `tests/test_config.py::PatchTest` 会在一个合成包上验证这三条。

### 为什么工具决策和正式回复用不同模型

`tools` 块每条消息都会调一次（判断"要不要发图/建任务"），
`llm_chat` 只在最后生成回复时调一次。把决策交给 `deepseek-flash`、
回复交给视觉模型，是延迟和成本的平衡点。实测私聊一句话 3～6 秒。

### 为什么规则分严格/宽松两套

kirara 的 `fallback` 规则意味着"没匹配上就回"。放在群聊里就是**每条消息都回**：
既烧钱又扰民，还容易触发账号风控。所以：

- `config/rules.owner.yaml`（填了 `OWNER_QQ` 时用）：只回主人私聊；陌生人私聊走
  `chat:memory_store`（记录但不发消息）；群里只有被@、`/chat` 前缀或明确关键词才回。
- `config/rules.yaml`（默认宽松）：保持上游行为，谁都能聊。

由 `provision.py` 按 `.env` 选择，不要求用户手改 YAML。

### 为什么提示词里有那么多"铁律"

这些不是文风偏好，每一条都对应一次真实的翻车：

| 规则 | 不加会发生什么 |
|---|---|
| 禁止提"系统/工具/自动/生成" | 它会说「那个图是系统塞给我的」，直接出戏 |
| 禁止方括号占位符 | 正文里冒出 `[表情包]`（模型模仿 QQ 的显示方式） |
| 明确要图时必须给 | 写了"不要顺从"之后，它会连「发个表情包」都拒绝 |
| 难过时不发图 | 你说"被领导骂了"，它甩一张搞笑表情过来 |
| 群里更克制 | 刷屏 |

改提示词请务必同步更新 `tests/test_config.py::WorkflowTest`，
那组断言就是这些教训的回归测试。

## 3. 可测试性

`bot/selftest.py` 利用了 kirara 内置的 http_legacy 适配器
（`POST http://127.0.0.1:8080/v1/chat`，body 为 `{username, message, session_id}`），
在**不扫码、不依赖 QQ** 的情况下跑通整条链路。
`session_id` 用 `friend-selftest-*` / `group-selftest:*` 这类假值，不会污染真实会话记忆。

`tests/` 是纯离线单元测试：图库匹配算法、收录过滤规则、配置模板正确性、补丁幂等性。
所有外部依赖（媒体目录、视觉模型、kirara API）都被替换成临时目录或假实现。

## 4. 进程与端口

| 组件 | 端口 | 谁启动 | 说明 |
|---|---|---|---|
| 表情包图库 | 3100 | `一键启动.cmd` / 守护 | 纯标准库 HTTP 服务 |
| kirara | 8080 | `一键启动.cmd` / 守护 | WebUI + Web API + http_legacy |
| NapCat WebUI | 6100 | `一键启动.cmd` / 守护 | **安装时钉死**，否则多开会自动递增导致启停脚本认错 |
| NapCat OneBot HTTP | 3002 | NapCat | 守护用它查登录态、发通知 |

`bot/watchdog.py` 巡检这四项，掉线自动拉起。它和手动启停的协调靠 `logs/.guard`
文件内容（`paused` / `running`）：`停止.cmd` 写 `paused`，`一键启动.cmd` 写 `running`。
用**覆写文件内容**而不是删文件，是为了让脚本里不出现任何删除操作。

## 5. 不做什么

- **不做 Docker**：QQ 协议端需要桌面运行环境与图形登录，容器化对目标用户（Windows 个人）没有收益。
- **不做多平台**：kirara 本身支持微信/Telegram，但本项目的价值在 QQ 表情包生态，
  多平台会摊薄精力。
- **不做 Web 管理面板**：kirara 自带，重复造轮子没有意义。
- **不引入运行期第三方依赖**：见 CONTRIBUTING。
