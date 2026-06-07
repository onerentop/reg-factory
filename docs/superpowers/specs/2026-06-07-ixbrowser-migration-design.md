# 指纹浏览器迁移设计：BitBrowser → ixBrowser

- 日期：2026-06-07
- 范围：reg-factory 全项目的指纹浏览器后端
- 参考实现：`D:\workspace\projects\auto_bitbrowser2`（`services/ix_api.py`、`services/ix_window.py`、`ixbrowser_local_api`）
- 状态：设计待评审

## 1. 背景与目标

当前 reg-factory 用 **BitBrowser（比特浏览器）** 做指纹隔离，通过其本地 HTTP API
(`http://127.0.0.1:54345`) 创建/打开/关闭/删除浏览器窗口，再用 Playwright 经 CDP
连接窗口执行自动注册。

目标：**彻底替换为 ixBrowser**，底层改用官方 pip 包 `ixbrowser-local-api`
(`IXBrowserClient`)，用法参考 `auto_bitbrowser2`。替换后 BitBrowser 不再保留。

非目标：
- 不改注册业务逻辑（claude/chatgpt/grok/outlook 各注册流程）。
- 不引入 profile 复用池，沿用"临时建窗口→用完删除"的生命周期。
- 不替换页面级反检测脚本 `STEALTH_JS`（与指纹平台无关，继续保留）。

## 2. 现状梳理

### 2.1 BitBrowser 封装与调用点

- `bitbrowser.py`：`BitBrowser` 类，方法
  `list_browsers / open_browser / close_browser / delete_browser / cleanup_browsers / create_browser / select_browser`。
  - `profile_id` 为字符串 UUID。
  - `open_browser(pid)` 返回 `{"ws": ..., "http": ...}`。
  - `create_browser(name, **kwargs)` 默认 `proxyMethod=2, proxyType="noproxy", browserFingerPrint={"coreVersion":"130"}`。
- `common/browser.py`：把 BitBrowser 封装成 `open_and_connect(name, p)` →
  `(bb, pid, browser, ctx, page)` 与 `teardown(bb, pid, delete)`。
  内部 `p.chromium.connect_over_cdp(ws)` + 注入 `STEALTH_JS` + 固定 `Accept-Language: en-US`。
  被 `oauth_codex.py`、`register_chatgpt.py` 复用。
- **裸用 `from bitbrowser import BitBrowser` 的文件**：
  `register.py`、`register_grok.py`、`outlook_reg_loop.py`、`mailbox_broker.py`、`validate_keys.py`。
- `register_outlook_standalone.py`：**自带一份独立的 BitBrowser 子类/封装**，含
  `_parse_proxy`，创建窗口时把住宅代理（`proxy_str`）注入窗口本身（per-window 代理）。

### 2.2 两种代理模式（必须都保留）

1. **noproxy 模式**（claude / chatgpt / grok）：窗口直连，靠 Clash Verge 系统代理走节点。
2. **per-window 模式**（outlook 自注册）：窗口配住宅代理（`OUTLOOK_PROXIES` 池，
   `proxy_str` 经 `_parse_proxy` 解析后注入）。

### 2.3 ixBrowser SDK 能力（来自 `ixbrowser_local_api`）

- `IXBrowserClient()`：默认连本机 `127.0.0.1:53200`。
- `open_profile(profile_id, cookies_backup=False, load_profile_info_page=False)`
  返回 dict，含 `ws`（**可直接喂给 Playwright `connect_over_cdp`**）、`debugging_address`、
  `webdriver`、`pid`。失败返回 `None`，错误信息在 `client.message` / `client.code`。
- `create_profile(Profile)` → 返回含 `profile_id`（整数）。
- `close_profile(id)` / `delete_profile(id)` / `get_profile_list(page, limit, group_id, keyword)`。
- `update_profile_to_custom_proxy_mode(profile_id, proxy_type, proxy_ip, proxy_port, proxy_user, proxy_password)`。
- `Profile.fingerprint_config = Fingerprint(...)`，`Fingerprint` 支持
  `kernel_version`（≈ BitBrowser coreVersion）、`platform`、`hardware_concurrency`、
  `device_memory`、`language` / `timezone`、`webrtc`、`cloudflare_challenge_bypassing` 等。
- `Profile.proxy_config = Proxy(...)`，`Proxy.change_to_custom_mode(...)` 设自定义代理。

## 3. 设计

### 3.1 架构：抽象接口 + ixBrowser 唯一实现

新增：
```
common/browser_provider.py    # BrowserProvider(ABC) — 契约
common/ixbrowser_provider.py  # IXBrowserProvider(BrowserProvider) — 唯一实现
```
删除：`bitbrowser.py`，以及 `register_outlook_standalone.py` 内的独立封装类。

`BrowserProvider` 抽象方法（**方法名/返回形状刻意对齐旧 BitBrowser，最小化调用方改动**）：

| 方法 | 返回 | 备注 |
|---|---|---|
| `create_browser(name, proxy_str=None, **kw)` | `profile_id`(int) | `proxy_str` 解析→ `Proxy` 自定义代理；无则直连。指纹见 3.3 |
| `open_browser(profile_id)` | `{"ws":..., "http":...}` | `ws` 取自 `open_profile().ws`；`http` 取 `debugging_address` |
| `close_browser(profile_id)` | None | |
| `delete_browser(profile_id)` | None | |
| `cleanup_browsers(keep=0)` | int(删除数) | `get_profile_list` 分页拉全量后按 seq 降序删 |
| `list_browsers(page, page_size)` | `{"data":{"list":[...]}}` | 形状对齐旧 API，内部字段转换 |
| `select_browser()` | `profile_id` | 交互式选择/新建，保留 |

工厂：`common/browser_provider.py` 提供 `get_browser_provider()`，当前直接返回
`IXBrowserProvider()` 单例。调用方一律改用它。

内置自动重试（TLS/socket/网络抖动指数退避 + 重置 client），逻辑参考
`auto_bitbrowser2/services/ix_api.py` 的 `RETRYABLE_ERRORS` / `_reset_client`。

### 3.2 调用方改动清单

| 文件 | 改动 |
|---|---|
| `common/browser.py` | `BitBrowser()` → `get_browser_provider()`；`open_and_connect`/`teardown` 逻辑不变（ws 对接、stealth、Accept-Language 全保留） |
| `register.py` | 替换 import 与实例化（3 处入口） |
| `register_grok.py` | 替换 import 与实例化 |
| `register_outlook_standalone.py` | 删除独立封装类，改用 `get_browser_provider()`；`proxy_str` 透传 `create_browser` |
| `outlook_reg_loop.py` | 替换实例化；`open/close/delete/cleanup` 调用不变 |
| `mailbox_broker.py` | 替换 import 与实例化 |
| `validate_keys.py` | 替换 import 与实例化 |
| `config.py` | 去掉 `BITBROWSER_API`；新增 `IXBROWSER_TARGET`(默认 `127.0.0.1`)、`IXBROWSER_PORT`(默认 `53200`) |
| `requirements.txt` | 加 `ixbrowser-local-api` |
| `.env.example` / `README.md` | 前置条件/配置表把 BitBrowser 段替换为 ixBrowser |

> `profile_id` 由 str(UUID) 变 int：所有调用方只是透传（建→开→关→删），不解析其内容，
> 落盘/日志按字符串化输出即可，无语义影响。

### 3.3 指纹：尽量对齐原 BitBrowser 配置

`create_browser` 内构造 `Fingerprint`：
- `kernel_version = "130"`（对齐旧 `coreVersion=130`）
- `platform = "Windows"`、`ua_type = 1`(PC)
- `hardware_concurrency = 8`、`device_memory = 8`（与 `STEALTH_JS` 内伪造值一致，避免自相矛盾）
- `language` / `timezone`：随代理地区，保持 ixBrowser 默认随机或跟随代理
- 可选：对 grok 开 `cloudflare_challenge_bypassing`（过 Cloudflare）——作为后续可调项，默认不强开

> 字段取值若与具体 ixBrowser 版本/账户套餐不兼容，回退为 ixBrowser 默认指纹并记日志。

### 3.4 代理映射

- `proxy_str` 为空 → `Proxy.change_to_custom_mode(proxy_type="direct")`（直连，走 Clash 系统代理）。
- `proxy_str` 非空 → 复用下沉到 provider 的 `_parse_proxy`，得到
  `{type, host, port, user, pass}`，调用 `Proxy.change_to_custom_mode(...)` 或建窗口后
  `update_profile_to_custom_proxy_mode(...)`。`type` 支持 `http` / `socks5`。

### 3.5 生命周期

沿用现状：每个账号临时 `create_browser → open_browser →（业务）→ close_browser → delete_browser`；
配额满时 `cleanup_browsers(keep=N)` 释放。

## 4. 依赖与前置

- `pip install ixbrowser-local-api`（加入 requirements.txt）。
- 本机 **ixBrowser 客户端运行中**，本地 API 默认 `127.0.0.1:53200`。
- Clash Verge 系统代理链路不变。

## 5. 风险

1. **ws 兼容性（头号）**：需实测 `open_profile().ws` 能被 Playwright `connect_over_cdp` 接受。
   若 ixBrowser 只给 `debugging_address`，则在 provider 内拼成 `http://<addr>` 用
   `connect_over_cdp("http://127.0.0.1:port")`（Playwright 支持 http 端点自动发现 ws）。
2. **联调依赖**：必须本机 ixBrowser 在线，当前会话无法代为实测；交付后需人工跑通一次。
3. **指纹差异**：换平台后风控表现可能与 BitBrowser 不同，`kernel_version` 等取值需按
   实际可用值校准。
4. **配额**：ixBrowser 免费/套餐的 profile 数限制可能与 BitBrowser 不同，`cleanup` 阈值
   可能需调整。

## 6. 验收标准

- [ ] `bitbrowser.py` 删除，全仓无 `from bitbrowser import` / `BITBROWSER_API` 残留。
- [ ] 7 个调用文件 + config/.env.example/requirements/README 全部改完。
- [ ] `register_outlook_standalone.py` 不再有独立浏览器封装类。
- [ ] 本机 ixBrowser 在线时，至少一条链路（建议 chatgpt 或 claude）端到端跑通：
      建窗口 → Playwright 连接 → 注入 stealth → 打开目标站 → 关闭并删除窗口。
- [ ] outlook 自注册的 per-window 住宅代理生效（窗口出口 IP = 代理 IP）。
