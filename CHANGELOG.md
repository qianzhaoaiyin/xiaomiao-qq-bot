# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-10-10

首个可发布版本。从一台真实使用中的 Windows 机器上整理而来，所有功能都在真实 QQ 链路上验证过。

### 新增

- **本地表情包图库**（`bot/gallery_server.py`）：HTTP 服务按关键词挑图，零月费、不依赖外网。
  取代已失效的外部图源（`api.lolimi.cn` 域名不存在，`fabiaoqing.com` 的图床 `img.soutula.com` 返回 403）。
- **表情包自动收录**（`bot/sticker_collector.py`）：从 kirara 的媒体库里旁路收集收到的图片，
  用视觉模型自动打标签写进文件名，形成语义检索。不改 kirara 一行内核代码。
- **看图能力**：私聊与群聊回复统一走 `deepseek-v4-flash-vision-exp`，能读懂用户发来的表情包。
- **主动发表情包**：不用用户开口要，模型按气氛自行决定；难过/正经问题不发图。
- **人设去机器人味**：会拒绝、会记仇、有情绪连续性；同时用"铁律"段禁止打破第四面墙。
- **守护进程**（`bot/watchdog.py`）：巡检图库/kirara/NapCat/QQ 登录态，掉线自动拉起，
  状态变化时给主人发 QQ 私聊；`--once` 输出状态报告；`--pause/--resume` 避免与手动启停打架。
- **严格模式派发规则**（`config/rules.owner.yaml`）：只回主人私聊、陌生人静默、群里被@或命令才回。
- **一键安装**（`scripts/install.ps1`）：从官方 release 下载 kirara-ai 与 NapCat，装插件、灌配置。
- **一键配置**（`bot/provision.py`）：幂等地写入 kirara 主配置、派发规则、NapCat 反向 WS，
  并通过 API 写入工作流；按 `.env` 的 `OWNER_QQ` 自动在严格/宽松规则之间选择。
- **端到端自测**（`bot/selftest.py`）：不依赖 QQ 扫码，走内置 http_legacy 通道验证全链路。
- **单元测试**（`tests/`，30 例）：图库关键词匹配、收录过滤规则、配置模板正确性、图源补丁幂等性。
- **CI**（`.github/workflows/ci.yml`）：Ubuntu + Windows × Python 3.11/3.13，
  跑编译检查、单元测试、批处理编码一致性检查和密钥扫描。

### 修复（整理过程中发现并修掉的真实缺陷）

- 图库关键词匹配原来按**单个汉字**命中就算，导致文件夹「偷来的」里的"来""的"
  抢走本该发给别的分类的图。改为**最长公共子串打分**，至少两个连续汉字对上才算命中。
- 匹配时误用完整路径，路径里的用户名/临时目录字符会造成误命中。改为只用「文件夹名 + 文件名」。
- `api_collection` 插件的 `_update_doc` 类脚本取登录响应的 `token` 字段，
  而 kirara 实际返回 `access_token`，导致脚本一直静默失败。
- 上游 `config.yaml` 模板的 `defaults.llm_model` 指向未配置的 `gemini-1.5-flash`，
  会让未显式指定模型的块取不到模型。改为 `deepseek-flash`。
- NapCat 的 WebUI 端口在被占用时会自动递增，导致按端口判断的启停脚本认错实例。
  安装时把端口钉死。
- 收录器原先只看 `source == im_message`，会把机器人**自己发出去**的图又收回来；
  改为叠加"内容为 sha1 已在图库"和"references 为空"两道过滤。
- 收录器与图库服务存在未关闭的文件句柄（`ResourceWarning`），全部改为 `with` 管理。

### 已知限制

- 仅支持 Windows（协议端与批处理脚本都是 Windows 形态）。
- 群聊默认每条消息都回（宽松模式）；建议启用严格模式。
- 不提供 Docker：QQ 协议端需要桌面运行环境，容器化收益有限。
- 主动定时消息依赖 QQ 侧允许主动推送，需自行实测。
