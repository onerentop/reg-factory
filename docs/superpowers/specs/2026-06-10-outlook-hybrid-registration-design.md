# Outlook 混合注册设计：浏览器铸会话 → 协议提交

日期：2026-06-10
状态：已批准设计，待实现
分支：feat/ixbrowser-migration

## 背景与动机

Outlook 注册有两套验证码，分布在不同入口：

- **浏览器模式** → PerimeterX 长按（Press&Hold）。CapSolver 能自动解，浏览器模式已端到端跑通。
- **协议模式** → CreateAccount 调用需要 Arkose FunCaptcha token（填入 `HSol` 字段）。

纯协议注册的瓶颈在 Arkose token：经多方验证，没有任何商业打码平台能稳定解 Outlook 的 Arkose FunCaptcha（实测 CapSolver 已停 FunCaptcha、EZ-Captcha 资源不足、SolveCaptcha/CaptchaKings/NextCaptcha 全部失败）。根因是这些平台在**孤立环境**铸 token，与 MS 会话/IP 不匹配。

**关键洞察**：在真实浏览器里，PerimeterX 清除后（CapSolver 设 `_px*` cookie），点提交时 Arkose 的 JS 会在本会话内**透明签发**一个 HSol token（会话干净、BDA 真实时通常无可见拼图）。协议流没有浏览器跑 Arkose JS，拿不到这个透明 token。

**目标**：协议跑轻量部分（取页、查可用、填资料、提交、校验、抽 token），只在铸 Arkose token 这一步短暂起浏览器，让真浏览器的 Arkose JS 在干净会话里签发 HSol，截获后交给协议消费。

## 核心原则

浏览器和协议**共享同一代理 + 同一份 cookie + 同一个 UA**，三者一致 → MS 服务端把它们当作"同一个真实会话"。这是与付费 API 唯一的本质区别。

## 架构总览

```
HybridOutlookOrchestrator  (Facade — 编排全流程，对 step_engine 暴露单一入口)
        │
        ├─ AccountDraft / AccountFactory   (账号资料对象，浏览器和协议全程共用同一份)
        │
        ├─ SessionMinter   (浏览器侧 — 过 PerimeterX、让 Arkose JS 铸 HSol、截获凭证、ABORT 不建号)
        │     └─ 产出 → MintedCredential
        │
        ├─ MintedCredential   (数据对象：cookies + canary + 截获的 CreateAccount 请求体 + headers + UA + proxy)
        │
        ├─ ProtocolSubmitter   (协议侧 — 装载凭证、立即 replay CreateAccount、校验、抽 token)
        │
        └─ FallbackPolicy   (Strategy — 混合失败时回退到完整浏览器模式)
```

### 数据流

```
1. Orchestrator 生成 AccountDraft（一份账号资料，全程唯一）
2. SessionMinter.mint(proxy, draft):
      浏览器开真实签到页(同 proxy)
      → CapSolver 自动过 PerimeterX（复用现有 solve_perimeterx_capsolver）
      → 用 draft 填表、触发提交
      → 拦截 CreateAccount 请求，截获其 HSol(Arkose token)+canary+cookies，ABORT 该请求(账号不在浏览器里建)
      → 关闭浏览器
      → 返回 MintedCredential
3. ProtocolSubmitter.submit(draft, credential):
      把 credential.cookies 装进 requests.Session(同 proxy、同 UA)
      → 立即 replay POST CreateAccount(用截获的 canary + HSol + 完整请求体)
      → verify_registered_outlook
      → 抽 refresh_token
4. 成功 → 存库；失败 → FallbackPolicy 决定是否回退完整浏览器模式
```

## 组件详细设计

### AccountDraft / AccountFactory

不可变数据对象，承载一次注册的全部账号资料（email、password、prefix、first_name、last_name、year、month、day）。`AccountFactory.create()` 复用现有 `generate_email_password()` / `generate_name()` / `generate_birthday()` 生成。**全程唯一**：浏览器填表和协议 replay 用的是同一份，保证一致。

### SessionMinter（浏览器侧）

职责单一：过 PerimeterX → 让 Arkose JS 铸 HSol → 截获完整请求 → ABORT（不建号）。

```python
class SessionMinter:
    def __init__(self, browser_provider, perimeterx_solver, capture_timeout=90): ...
    async def mint(self, proxy: str, draft: AccountDraft) -> MintedCredential: ...
```

`mint()` 流程：
1. 起浏览器（**同 proxy**）
2. 在 `**/API/CreateAccount*` 上挂 Playwright 路由拦截器
3. 导航签到页 → 需要时 CapSolver 过 PerimeterX
4. 用 **draft** 填表（姓名→生日→邮箱→密码，复用现有 fill 助手）→ 点提交
5. Arkose JS 签发 HSol → CreateAccount 请求触发 → 拦截器读出**请求体(含 HSol+uaid+hpgid 等全字段) + 请求头(canary 等) + cookies** → `route.abort()`
6. 读 `navigator.userAgent`、`context.cookies()`（canary/uaid/hpgid 以步骤 5 截获的请求为权威来源，不另读 ServerData）
7. 关浏览器 → 返回 `MintedCredential`

**关键决策——逐字 replay，不重建 payload**：截获的 CreateAccount 请求体是浏览器构造好的完整正确 payload（含 HSol、RiskAssessmentDetails 等全部字段）。`MintedCredential` 直接携带这个原始 dict，协议侧原样 replay，只换不重建——比手工拼 payload 稳得多。

设计模式：Strategy（PerimeterX solver 可注入替换）、Builder（MintedCredential 逐步装配）、Observer（拦截回调喂 `asyncio.Future`，`mint()` await 它）。

### MintedCredential

```python
@dataclass
class MintedCredential:
    cookies: list[dict]        # .live.com 全部 cookie，含 _px*
    canary: str                # 请求头里的 apiCanary
    create_payload: dict       # 截获的 CreateAccount JSON 体(含 HSol)
    request_headers: dict      # canary/hpgid/scid/Origin/Referer/Content-Type
    user_agent: str            # 必须与协议 Session 一致
    proxy: str
    captured: bool
```

### ProtocolSubmitter（协议侧）

```python
class ProtocolSubmitter:
    def __init__(self, token_extractor, verifier): ...
    def submit(self, draft: AccountDraft, cred: MintedCredential) -> RegistrationResult: ...
```

`submit()` 流程：
1. 建 `requests.Session`，**同 proxy、同 UA**
2. **Cookie 转植**：Playwright cookie `{name,value,domain,path}` → `session.cookies.set(...)`（处理前导点域名 `.live.com`）
3. **立即** replay：用 `cred.request_headers` + `cred.create_payload` 原样 POST `API/CreateAccount?lic=1`（token 有效期窗口内必须发出）
4. 解析响应：
   - 成功 → `verify_registered_outlook` → `token_extractor` 抽 refresh_token
   - `error.code` 含 Arkose/challenge 拒绝 → 抛 `SubmitRejected`（绑定理论失败信号，**重点日志**）
   - 网络错误 → 窗口内重发一次，仍失败则抛
5. 返回 `RegistrationResult`

**token 时效**：Orchestrator 在 `mint()` 返回后零延迟调 `submit()`，中间不插入任何耗时操作。

### FallbackPolicy（Strategy）

```python
class FallbackPolicy:
    async def handle(self, proxy, idx, draft, error) -> RegistrationResult: ...
```

- `MintFailed`（过不了 PerimeterX / Arkose 弹可见拼图解不了）→ 换会话重试 1 次
- `SubmitRejected`（token 被拒）→ 直接回退完整浏览器模式（现有 `_register_one_browser`，让浏览器自己建号）
- 仍失败 → 返回 `success=False`

**复用而非重写**：完整浏览器模式本质是"SessionMinter 不 abort CreateAccount、让它跑完"。但 `_register_one_browser` 已存在且能跑通，回退直接调它。

### HybridOutlookOrchestrator（Facade）

```python
class HybridOutlookOrchestrator:
    async def register(self, proxy, idx) -> RegistrationResult:
        draft = self._account_factory.create()          # 唯一账号资料，全程共用
        try:
            cred = await self._minter.mint(proxy, draft)     # 浏览器 ~15s 后释放
            result = self._submitter.submit(draft, cred)     # 协议立即 replay
            if result.success:
                return result
            raise SubmitRejected(result.reason)
        except (MintFailed, SubmitRejected) as e:
            return await self._fallback.handle(proxy, idx, draft, e)
```

`RegistrationResult`：`{success, email, password, refresh_token, mode_used: "hybrid"|"browser_fallback", error}`

### 吞吐设计：BrowserPool 信号量

`mint()` 进出时 acquire/release 一个 `BrowserPool(max_concurrent=N)` 异步信号量；`submit()` 不持有浏览器。于是 N 个浏览器只在"铸 token"阶段被占用，校验/抽 token/存库全在协议侧无锁并发 → 少量浏览器喂多个在途任务，这就是"只为验证码用浏览器"的吞吐兑现。进程模型下，BrowserPool 在单进程内限流该进程的浏览器并发；跨进程并发由 multiprocessing 控制。

## 平台集成

### 文件落位

新建包 `outlook_hybrid/`，每个类一个小文件：

```
outlook_hybrid/
  __init__.py          # 暴露 register_outlook_hybrid(proxy_str, idx) 门面函数
  account_draft.py     # AccountDraft + AccountFactory
  credential.py        # MintedCredential
  minter.py            # SessionMinter
  submitter.py         # ProtocolSubmitter
  fallback.py          # FallbackPolicy
  orchestrator.py      # HybridOutlookOrchestrator
  errors.py            # MintFailed / SubmitRejected
```

复用的函数从 `register_outlook_standalone` import（`solve_perimeterx_capsolver` / `verify_registered_outlook` / `generate_*` / `_proxy_for_requests` / `_register_one_browser`），不重写。

### 模式选择（Strategy/Factory）

`step_engine.OutlookRegistrationFlow` 第二步读 `context["mode"]`，按表分派：

```python
ENTRY = {
    "hybrid":   register_outlook_hybrid,
    "browser":  _register_one_browser,      # 现有，已跑通
    "protocol": register_outlook_protocol,  # 现有纯协议
}
```

- 默认仍是 `browser`（已稳定）；**Phase 0 验证通过后**再把默认切到 `hybrid`
- 前端注册表单加"注册模式"下拉 → Gateway → process_manager `context` → flow，全链路透传

### 进程模型

不变。`_worker_process` 子进程里 `flow.run(context)` 跑 async Orchestrator；`submit()` 是同步 requests，在子进程内短暂阻塞可接受（一进程一任务）。

## Phase 0：验证 spike（实现第一步，去风险）

整个设计押在一个假设上：**浏览器铸的 HSol，协议 replay 时 MS 会接受**。先用一次性脚本验证：

```
spike: 浏览器铸 HSol+canary+cookies+UA → 立即 requests replay → 看 MS 是否建号成功
```

- **PASS** → 按本设计建完整混合
- **FAIL（token 被拒）** → 绑定理论错，组件边界不变但语义切换：SessionMinter 改为"浏览器跑完建号"，ProtocolSubmitter 退化为"只做校验+抽 token"。设计仍成立，不白做

成本 ~1 小时，避免在错误假设上盖楼。

## 错误处理汇总

| 情况 | 处理 |
|------|------|
| PerimeterX 解不了 / Arkose 弹可见拼图 | `MintFailed` → 重试1次 → 回退浏览器 |
| HSol 被 MS 拒 | `SubmitRejected` → 重点日志 → 回退浏览器 |
| token 窗口超时 | submit 前零延迟；超时按拒绝处理 |
| 网络错误 | submit 窗口内重发1次 |
| 建号成功但抽不到 token | 仍算成功，`has_token=false` 存库 |
| 邮箱被占 | 换 draft 重来 |

## 测试策略（沿用现有 pytest 体系）

- **单元**：cookie 转植（Playwright→requests）、FallbackPolicy 决策表、payload replay 构造（mock requests）、AccountDraft 唯一性
- **集成**：SessionMinter 配 mock 路由（断言截获 HSol 且 abort）、ProtocolSubmitter 配 mock MS 端点（断言 replay 头/体一致）
- **E2E（人工/gated）**：真实跑 N 次混合，统计成功率对比浏览器模式

## 复用的现有代码清单

- `register_outlook_standalone.solve_perimeterx_capsolver` — CapSolver 过 PerimeterX
- `register_outlook_standalone.generate_email_password` / `generate_name` / `generate_birthday` — 账号资料生成
- `register_outlook_standalone.verify_registered_outlook` — 注册成功校验
- `register_outlook_standalone._register_one_browser` — 完整浏览器模式（回退用）
- `register_outlook_standalone.register_outlook_protocol` — 纯协议模式（保留）
- `register_outlook_standalone._proxy_for_requests` — 代理格式化
- `extract_graph_tokens`（via LegacyBridge）— refresh_token 抽取
- `common/browser_provider` / `common/ixbrowser_provider` — 浏览器启动

## 决策记录

- 选方案 A（浏览器铸会话凭证 → 协议提交），否决 B（独立解码，token 绑定风险高）和 C（解码微服务，多一层基建且绑定风险同 B）
- 解码方式：全自动 CapSolver（无人值守、可并发）
- 捕获方式：路由拦截 CreateAccount 请求体（最可靠，拿到的是已签名完整 payload）
- 提交方式：逐字 replay 截获的请求体，不重建
- 回退：复用现有 `_register_one_browser`，不重写
