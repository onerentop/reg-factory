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

### 3.2 create_browser（已实测校准）

请求体是**嵌套**结构 `{"profile": {...ProfileInput...}}`,响应 HTTP 201,`profileId` 在**顶层**。

```python
def create_browser(self, name="reg", proxy_str=None, **kwargs):
    proxy_config = proxy_str.strip() if proxy_str and proxy_str.strip() else "direct://"
    body = {"profile": {"profileName": name, "proxyConfig": proxy_config,
                        "coreId": kwargs.get("core_id", "")}}  # coreId 空→默认内核
    result = self._call("POST", "/api/profiles", body)
    return result["profileId"]   # 实测:顶层 profileId(UUID)
```

实测响应键:`{created, launchCode, launched, ok, profile, profileId, profileName, updated}`。

### 3.3 open_browser（launch 同步返回 debugPort,无需轮询）

实测:`POST /api/launch {profileId}` 同步返回 `{debugPort, debugReady:true, cdpUrl, pid, launchCode}`。无需轮询 runtime/active。保留一个 debugReady 断言 + 短重试兜底(极端情况 debugReady 可能瞬时未就绪)。

```python
def open_browser(self, profile_id):
    r = self._call("POST", "/api/launch", {"profileId": profile_id})
    debug_port = r.get("debugPort")
    if r.get("debugReady") and debug_port:
        http_ep = f"http://127.0.0.1:{debug_port}"
        return {"ws": http_ep, "http": http_ep}
    # 兜底:短轮询 runtime/active(实测通常首次即就绪)
    for _ in range(15):
        rt = self._call("GET", "/api/runtime/active")
        if rt.get("profileId") == profile_id and rt.get("debugReady") and rt.get("debugPort"):
            http_ep = f"http://127.0.0.1:{rt['debugPort']}"
            return {"ws": http_ep, "http": http_ep}
        time.sleep(1)
    raise AntAPIError(0, "GET", "/api/runtime/active", "debug not ready")
```

`http://127.0.0.1:{debugPort}` 是真实 Chrome DevTools 端点,交由 `open_and_connect` 的 `connect_over_cdp` 自动发现 ws。(Ant 另给 `cdpUrl=http://127.0.0.1:19876` 是它自己的 CDP 代理,不用它。)

### 3.4 close / delete / cleanup / list / select（stop 需 selector,delete 须先 stop）

实测坑:`stop` 空 body 返回 400,需带 `{"profileId":pid}` selector;`delete` 对**运行中**实例返回 409,必须先 stop。

```python
def close_browser(self, profile_id):
    try: self._call("POST", "/api/runtime/stop", {"profileId": profile_id})  # 需 selector
    except Exception: pass

def delete_browser(self, profile_id):
    # 先确保已停(delete 运行中实例返回 409)
    try: self._call("POST", "/api/runtime/stop", {"profileId": profile_id})
    except Exception: pass
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
    rows = self._fetch_all_profiles()          # items 顺序即创建顺序
    to_delete = rows[keep:]                     # 保留前 keep 个
    for p in to_delete: self.delete_browser(p["profileId"])   # delete 内含 stop
    return len(to_delete)

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

## 8. 实测校准结果（已对运行中的 Ant API 打过一轮,创建→launch→stop→delete 全走通并清理)

| 项 | 校准结论 |
|---|---|
| 创建请求体 | 嵌套 `{"profile": {profileName, proxyConfig, coreId}}`,**非扁平**;HTTP 201 |
| profileId 位置 | 响应**顶层** `profileId`(UUID) |
| launch 返回 | `POST /api/launch {profileId}` **同步**返回 `{debugPort, debugReady:true, cdpUrl, pid, launchCode}`,**无需轮询** |
| CDP 端点 | `http://127.0.0.1:{debugPort}`(真实 Chrome 端点);`cdpUrl` 是 Ant 自己的代理,不用 |
| stop 参数 | 需 `{"profileId":pid}` selector;**空 body 返回 400** |
| delete 时机 | 运行中实例 delete **返回 409**,必须先 stop |
| proxyConfig | URL scheme,直连 `direct://`;创建时接受(连通性校验发生在 launch,非 create) |
| coreId | 可空,空则用默认内核 |

以上已全部并入第 3 节代码骨架。实现时无剩余未知项。

## 9. 唯一仍需实测的边界项

- socks5/http 带认证代理经 Ant launch 后**出口 IP 是否正确**(create 阶段不校验连通性,只有真 launch 才验证)。此项在实现的 smoke 测试里用一条真实 Webshare 代理验证,不阻塞架构。
