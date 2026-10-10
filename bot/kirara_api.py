# -*- coding: utf-8 -*-
"""kirara Web API 的最小封装。

几个容易踩的点，都封在这里了：
  * 登录接口返回的字段是 **access_token**，不是 token
  * 工作流 API 挂在 **/backend-api** 前缀下，直接访问 /api/... 会被 SPA 兜底
    路由返回 index.html（HTTP 200 但内容是 HTML，很容易误判成成功）
  * 内置 http_legacy 适配器的测试入口是 POST http://127.0.0.1:8080/v1/chat
    （注意：不在 /backend-api 下面），body 是 {username, message, session_id}
    session_id 用 "friend-xxx" 是私聊、"group-群号:用户号" 是群聊，
    用假 id 测试就不会污染真实会话的记忆
"""
import json
import time
import urllib.error
import urllib.request

import paths


class KiraraError(Exception):
    pass


class Kirara:
    def __init__(self, password=None):
        self.api = paths.KIRARA_API
        self.base = paths.KIRARA_BASE
        self.password = password or paths.webui_password()
        self.token = None

    def _call(self, method, url, body=None, token=None, timeout=120):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                txt = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise KiraraError("%s %s -> HTTP %s %s" % (method, url, e.code, detail))
        if not txt.strip():
            return {}
        if txt.lstrip().startswith("<"):
            raise KiraraError("返回的是 HTML，说明路径少了 /backend-api 前缀：%s" % url)
        return json.loads(txt)

    # ---------- 认证 ----------
    def login(self):
        d = self._call("POST", self.api + "/api/auth/login", {"password": self.password})
        self.token = d.get("access_token")
        if not self.token:
            raise KiraraError("登录没拿到 access_token，返回：%s" % json.dumps(d)[:200])
        return self.token

    def ensure_token(self):
        if not self.token:
            self.login()
        return self.token

    def wait_boot(self, timeout=240, need_login=True):
        """等 kirara 起来；need_login=True 时还要能用 .env 里的密码登录。"""
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                self._call("POST", self.api + "/api/auth/login", {"password": self.password})
                self.login()
                return True
            except Exception as e:
                last = e
                time.sleep(3)
        raise KiraraError("等不到 kirara 就绪（%ss）。最后错误：%s\n"
                          "如果是 HTTP 401，说明 WebUI 密码和 .env 里的 KIRARA_WEBUI_PASSWORD 不一致："
                          "首次启动请在 http://127.0.0.1:8080 把密码设成一样。" % (timeout, last))

    # ---------- 工作流 ----------
    def get_workflow(self, wf_id):
        return self._call("GET", "%s/api/workflow/%s" % (self.api, wf_id), token=self.ensure_token())["workflow"]

    def put_workflow(self, wf_id, wf):
        return self._call("PUT", "%s/api/workflow/%s" % (self.api, wf_id), wf, self.ensure_token())

    def list_workflows(self):
        d = self._call("GET", self.api + "/api/workflow", token=self.ensure_token())
        return d.get("workflows", d if isinstance(d, list) else [])

    def system_prompt(self, wf_id):
        wf = self.get_workflow(wf_id)
        return next(b for b in wf["blocks"] if b["name"] == "system_prompt")["config"]["text"]

    # ---------- 插件 / 规则 ----------
    def list_plugins(self):
        d = self._call("GET", self.api + "/api/plugin/plugins", token=self.ensure_token())
        return d.get("plugins", [])

    def enable_plugin(self, entry_name):
        return self._call("POST", "%s/api/plugin/plugins/%s/enable" % (self.api, entry_name),
                          {}, self.ensure_token())

    def get_rules(self):
        return self._call("GET", self.api + "/api/dispatch/rules", token=self.ensure_token()).get("rules", [])

    # ---------- 测试通道（http_legacy） ----------
    def chat(self, message, session_id="friend-selftest", username="主人", timeout=180):
        """走内置 http_legacy 适配器发一条消息，用于不依赖 QQ 的端到端自测。"""
        body = {"username": username, "message": message, "session_id": session_id}
        return self._call("POST", self.base + "/v1/chat", body, timeout=timeout)
