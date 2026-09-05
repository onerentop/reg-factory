# Ant Browser Provider 对接设计

- 日期：2026-09-05
- 需求：对接 Ant Browser（`F:\Ant-Browser`，本地 REST API 端口 19876）作为 reg-factory 的新浏览器 provider，替代 ixBrowser。ixBrowser 服务端对现用账号的数据已损坏、开窗接口稳定 500（本机无法修复），故切换到自研的 Ant Browser。
- 核心变化：新增 `common/ant_provider.py` 实现现有 `BrowserProvider` 抽象；`BROWSER_PROVIDER` 默认值由 `ixbrowser` 改为 `ant`；ixbrowser/donut 代码与配置保留可切。

## 0. 背景与可行性（已实测）

Ant Browser 是 Go + Wails 自研反检测浏览器,提供本地 REST API,已实测在 19876 端口运行:

| 接口 | 实测 |
|---|---|
| `GET /api/health` | ✅ `{"ok":true}` |
| `GET /api/profiles` | ✅ `{"count":1,"items":[{profileId(UUID), profileName, userDataDir, coreId, fingerprintArgs}],"ok":true}` |
| `GET /api/runtime/active` | ✅ `{active, debugPort, cdpUrl, directDebugUrl, debugReady, pid, running, profileId}` |
| `POST /api/profiles` | 创建实例;`coreId` 可空(空则 `GetDefaultCore()` 取默认内核) |
| `POST /api/launch` | 启动实例,body `{profileId, proxyConfig, ...}`,返回含 `debugPort` |
| `POST /api/runtime/stop` | 停止当前活跃实例 |
| `DELETE /api/profiles/{id}` | 删除实例 |

**并发模型**:Ant `LaunchServer` 用单个 `activePort/activeID`(server.go:284)跟踪**一个活跃实例**——单活跃语义。reg-factory `LocalProcessTaskManager(max_concurrency=1)` 默认一次只跑一个浏览器子进程。两边天然匹配。

**代理格式**:Ant 的 `proxyConfig` 是 URL scheme 格式,直连为 `direct://`。reg-factory 的 `proxy_str`(`http://user:pass@host:port` / `socks5://user:pass@host:port`)可直接作为 `proxyConfig`。

**CDP 连接**:Ant launch 后返回 `debugPort`,`http://127.0.0.1:{debugPort}` 是 Chrome DevTools HTTP 端点。现有 `common/browser.py::open_and_connect` 在 provider 只给 http 端点时,已有用 `connect_over_cdp(http_endpoint)` 让 Playwright 自动发现 ws 的兜底逻辑(为 ixBrowser 写的),Ant 直接复用。

## 1. 已确认的产品口径

| 议题 | 决定 |
|---|---|
| 实例生命周期 | **每次注册新建 profile,失败即删**——沿用 ixBrowser 模式,上层 worker/flows 零改造 |
| 默认 provider | **改为 ant**;ixbrowser/donut 代码保留,设 `BROWSER_PROVIDER` 可切回 |
| 单活跃约束 | 可接受(reg-factory 默认 `max_concurrency=1`) |
| CDP 接入 | 走 http `debugPort`,复用现有 `open_and_connect` |

## 2. BrowserProvider 抽象（要实现的契约）

`common/browser_provider.py` 定义的 7 个抽象方法:

```python
create_browser(name="reg", proxy_str=None, **kwargs) -> profile_id
open_browser(profile_id) -> {"ws": <cdp端点>, "http": <debug addr>}
close_browser(profile_id)      # 吞异常
delete_browser(profile_id)     # 吞异常
cleanup_browsers(keep=0) -> 删除数
list_browsers(page=0, page_size=100) -> {"data": {"list": [{"id","name","remark","seq"}]}}
select_browser() -> profile_id # 交互式
```

工厂 `get_browser_provider()` 现分支 `donut` / 默认 `ixbrowser`,新增 `ant` 分支。

## 3. AntBrowserProvider 实现

新文件 `common/ant_provider.py`,类 `AntBrowserProvider(BrowserProvider)`,风格对齐 `donut_provider.py`(urllib REST + 自定义异常 + 网络抖动重试)。

### 3.1 HTTP 底座

```python
class AntAPIError(Exception):
    """Ant REST API 调用错误(含 HTTP 状态)。"""
    def __init__(self, status, method, path, body=""): ...

class AntBrowserProvider(BrowserProvider):
    def __init__(self, base=None, api_key=None, timeout=30, retries=3):
        self.base = (base or ANT_API_BASE).rstrip("/")
        self.api_key = api_key or ANT_API_KEY  # 空则不发 X-Ant-Api-Key 头

    def _call(self, method, path, body=None):
        """urllib 调用。网络抖动(connection refused/reset/timeout)指数退避重试;
        HTTP >=400 抛 AntAPIError;返回解析后的 JSON dict。"""
```

`X-Ant-Api-Key` 头仅在 `api_key` 非空时附加。

### 3.2 create_browser

```python
def create_browser(self, name="reg", proxy_str=None, **kwargs):
    proxy_config = proxy_str.strip() if proxy_str and proxy_str.strip() else "direct://"
    body = {"profileName": name, "proxyConfig": proxy_config, "coreId": kwargs.get("core_id", "")}
    result = self._call("POST", "/api/profiles", body)
    return result["item"]["profileId"]  # 具体字段名以实测响应为准
```

`coreId` 空 → Ant 用默认内核。响应取 `profileId`(UUID)。

### 3.3 open_browser（含轮询）

```python
def open_browser(self, profile_id):
    self._call("POST", "/api/launch", {"profileId": profile_id})
    # 轮询 runtime/active 到 debugReady(浏览器启动需几秒),超时抛错
    deadline = time.time() + 60
    while time.time() < deadline:
        rt = self._call("GET", "/api/runtime/active")
        if rt.get("profileId") == profile_id and rt.get("debugReady") and rt.get("debugPort"):
            http_ep = f"http://127.0.0.1:{rt['debugPort']}"
            return {"ws": http_ep, "http": http_ep}
        time.sleep(1)
    raise AntAPIError(0, "GET", "/api/runtime/active", "debug not ready in 60s")
```

返回的 `ws` 用 http 端点,交由 `open_and_connect` 的 `connect_over_cdp` 自动发现真实 ws。

### 3.4 close / delete / cleanup / list / select

```python
def close_browser(self, profile_id):
    try: self._call("POST", "/api/runtime/stop", {})   # 停当前活跃
    except Exception: pass

def delete_browser(self, profile_id):
    try: self._call("DELETE", f"/api/profiles/{profile_id}", None)
    except Exception: pass

def _fetch_all_profiles(self) -> list:
    return self._call("GET", "/api/profiles").get("items", [])

def list_browsers(self, page=0, page_size=100):
    rows = [{"id": p["profileId"], "name": p.get("profileName",""),
             "remark": p.get("userDataDir",""), "seq": p.get("profileId","")}
            for p in self._fetch_all_profiles()]
    return {"data": {"list": rows}}

def cleanup_browsers(self, keep=0):
    rows = self._fetch_all_profiles()
    to_delete = rows[keep:]  # 保留前 keep 个;排序规则以实测创建时间字段为准
    ...删除并计数

def select_browser(self):
    # 交互式列出 + 选择/新建,仿 ixBrowser
```

## 4. 配置变更（config.py）

```python
# 浏览器 provider:默认 ant。可 BROWSER_PROVIDER=ixbrowser/donut 切换。
BROWSER_PROVIDER = _env("BROWSER_PROVIDER", "ant")
ANT_API_BASE = _env("ANT_API_BASE", "http://127.0.0.1:19876")
ANT_API_KEY  = _env("ANT_API_KEY", "")
```

`common/browser_provider.py` 工厂加分支:

```python
if BROWSER_PROVIDER == "ant":
    from common.ant_provider import AntBrowserProvider
    _PROVIDER = AntBrowserProvider()
elif BROWSER_PROVIDER == "donut":
    ...
else:  # ixbrowser
    ...
```

## 5. 文档更新

- `.env.example`:provider 段落默认改 `ant`,新增 `ANT_API_BASE` / `ANT_API_KEY`,注明 ixbrowser/donut 为可选。
- `README.md` / `AGENTS.md`:前置条件与 provider 说明改为「默认 Ant Browser(19876),需先启动 Ant 客户端并开启 API 服务」,ixBrowser/donut 列为可选回退。

## 6. 已知约束

1. 需要 Ant Browser 客户端在 19876 运行且 API 服务已启用(设置页可查/改端口)。
2. Ant 单活跃语义:一次只有一个活跃实例。要求 reg-factory `max_concurrency=1`(已是默认)。若上调并发,第二个 launch 会顶掉第一个——provider 层不做多实例仲裁,由上层保证串行。
3. `close_browser(profile_id)` 停的是「当前活跃」实例;在 max_concurrency=1 下,当前活跃即该 profile,语义正确。

## 7. 测试

| 文件 | 覆盖 |
|---|---|
| `tests/test_ant_provider.py` | mock HTTP:create 传 direct:// / 传代理串、open 轮询到 debugReady 返回 http 端点、open 超时抛错、list 字段映射、close/delete 吞异常、是 BrowserProvider 子类 |
| 真实 smoke(手动/需授权) | 对运行中的 Ant:create→launch→拿 debugPort→connect_over_cdp→stop→delete 一个实例,验证端到端 |

单测全部 mock,不触发真实浏览器启动。smoke 会真实启动浏览器,需显式授权。

## 8. 实测待定项（实现时以真实响应校准）

- `POST /api/profiles` 成功响应里 profileId 的确切路径(`item.profileId` / `data.profileId` / 顶层)。
- `POST /api/launch` 是否也直接返回 debugPort(可省一次轮询),还是必须轮询 runtime/active。
- `cleanup_browsers` 排序依据的创建时间字段名。
- `proxyConfig` 对 socks5 带认证的确切接受格式(实测一条)。

这些不改变架构,实现首步先对真实 API 打一轮,校准字段名。
