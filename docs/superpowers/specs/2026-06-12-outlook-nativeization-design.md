# 里程碑2：Outlook 原生化 设计

- 日期：2026-06-12
- 上游 spec：`docs/superpowers/specs/2026-06-12-unified-registration-system-design.md`（统一架构，已批准）
- 策略：Strangler-Fig——把 `services/worker/flows/outlook.py` 的 `LegacyBridgeStep` 换成调 capabilities 原生服务的 native Step；逻辑经**根目录安全抽取**为共享函数（根/worker 共用一份源），根 loop 行为不变。
- 关键决策（用户已定）：**允许在根 `register_outlook_standalone.py` 里做行为保留的纯抽取**（不改行为，根 loop 照常出号）。

## 1. 背景

`services/worker/flows/outlook.py` 现有 2 个 `LegacyBridgeStep`：`Generate credentials`（调 `generate_*`）、`Browser registration with proxy`（按 mode 调 `_register_one_browser`/`register_outlook_hybrid`/`register_outlook_protocol`）。真实逻辑全在根 `register_outlook` 单体（623-1497，~870 行）内联：导航+预热 → Step1-5 表单 → Step6 验证码(PerimeterX 长按+Arkose 兜底) → `extract_graph_token`。

阶段边界清晰，可安全抽取为函数。

## 2. 根目录安全抽取（纯重构，行为逐字保留）

从 `register_outlook` 抽出可调用函数（`register_outlook` 重构为薄编排，仍按原顺序调用，**行为不变**）：

| 函数 | 来自（register_outlook 内 Step） | 签名 | 返回 |
|---|---|---|---|
| `_fill_signup_form` | Step 1-5（邮箱/密码/国家生日/用户名/姓名+勾选） | `(page, context, idx=0, tag="")` | `bool`（成功填完并提交到验证码前） |
| `_solve_perimeterx_hold` | Step 6 内：预热+9-12s 长按循环 | `(page, idx=0, tag="")` | `bool`（长按是否通过） |
| `_solve_signup_captcha` | Step 6 全编排（调 `_solve_perimeterx_hold` + Arkose 兜底 + 重试） | `(page, context, idx=0, tag="")` | `bool`（验证码是否过） |

已是函数、直接复用：`_warm_session`、`extract_graph_token`、`_open_ixbrowser_page`、`generate_email_password`/`generate_name`/`generate_birthday`、`rotate_proxy_sid`（在 `outlook_reg_loop.py`）。

`register_outlook` 重构后骨架：
```
navigate(referer) → _warm_session → _fill_signup_form → _solve_signup_captcha → extract_graph_token → return (email, password, graph)
```
**验证：** 抽取前后 `register_outlook` 的调用序列/参数/返回逐一对照；根 `outlook_reg_loop` 端到端行为不变（注：真正端到端只能靠干净 IP 实跑验证，见 §6）。

## 3. Worker 能力适配器（Adapter，包根函数，单一真源）

新增 `services/worker/capabilities/` 下实现：

| 文件 | 类 | 接口 | 包装 |
|---|---|---|---|
| `browser.py` | `IxBrowserService` | `BrowserService` | `browser_provider.get_browser_provider()` + `_open_ixbrowser_page` |
| `captcha/perimeterx.py` | `PerimeterXHoldSolver`(kind="perimeterx") | `CaptchaService` | `_solve_perimeterx_hold` |
| `token.py` | `GraphTokenExtractor` | `TokenExtractor` | `extract_graph_token` |
| `outlook_bundle.py` | `default_outlook_bundle()` | 工厂 | 组装上述 + `CaptchaResolver`(注册 PerimeterXHoldSolver) → `ServiceBundle` |

适配器只做"接口 → 根函数"的转接，不复制逻辑。根函数签名是这些适配器的依赖契约。

**`PerimeterXHoldSolver` 的角色（重要）**：它是 PerimeterX 长按的**类型化、可测能力**（包 `_solve_perimeterx_hold`），建好、注册进 bundle 的 `CaptchaResolver`、单测覆盖。但**验证码编排（长按重试 + Arkose 兜底）单源留在根 `_solve_signup_captcha`**——生产 flow 的 solve_captcha 步骤直接调它，避免根/worker 双轨编排漂移。`PerimeterXHoldSolver` 供单测与未来细粒度/通用 captcha 路径使用。

**`ProxyService` 延后**：worker 的代理由 `tasks.py` 经 context 注入（`ctx["proxy"]`），flow 不主动 acquire，故本里程碑不做 `StickyProxyService`（YAGNI）。

`IxBrowserService.open(profile, proxy)` 返回 `BrowserSession(page, context, profile_id, proxy)`；`close(session)` 调 `browser_provider` 的 close/delete。

## 4. Flow 改原生步骤 + 依赖注入

`flows/outlook.py` 改为 native Step（`kind="native"`），用注入的 `ServiceBundle`：

| Step | 实现 |
|---|---|
| `Generate credentials`（native） | 调 `generate_*`（纯函数，原 `_step_generate` 去掉 LegacyBridge 标记） |
| `Provision browser`（native） | `session = await services.browser.open(profile=..., proxy=ctx["proxy"])`；存 `ctx["_session"]` |
| `Fill signup form`（native） | `ok = await _fill_signup_form(session.page, ctx, idx)` |
| `Solve captcha`（native） | `ok = await _solve_signup_captcha(session.page, ctx, idx)`（单源编排：长按重试+Arkose 兜底全在根函数内）。`PerimeterXHoldSolver` 已注册进 bundle 供测试/未来，但本步走编排器保真 |
| `Extract token`（native） | `graph = await services.tokens.extract(session.page, account)`；写 `ctx["email"/"password"/"refresh_token"]` |
| `Teardown`（native） | `await services.browser.close(ctx["_session"])` |

**依赖注入（惰性 bundle）**：`RegistrationFlow.__init__(services=None)` 已支持注入。Outlook flow 加 `_bundle()`：`self.services is None` 时惰性 `default_outlook_bundle()`，否则用注入的（测试注入 fake）。`FlowRegistry.get("outlook")` 仍 `flow_cls()`（services=None→生产惰性建真 bundle），`tasks.py` **零改动**。

> 持久化不在本里程碑：flow 产出 `ctx["email"/"password"/"refresh_token"]`，由 `tasks.py` 现有逻辑 POST 到 `account_service`（不变）。

## 5. 测试策略

- **flow 单测**：注入 **fake ServiceBundle**（fake browser/captcha/token，记录调用），断言：步骤序列为 native、按序调用各能力、context 正确流转、某步失败短路。不碰真浏览器/网络。
- **能力单测**：`PerimeterXHoldSolver.solve()` monkeypatch 掉 `_solve_perimeterx_hold` 验证转接；`GraphTokenExtractor` 同理；`IxBrowserService` monkeypatch provider 验证 open/close 转接。
- **根抽取单测**：`_fill_signup_form`/`_solve_perimeterx_hold`/`_solve_signup_captcha` 至少有"可 import + 签名正确 + 纯逻辑分支"层面的烟测（完整逻辑依赖真页面，归 §6 实跑）。
- 遵现有约定（services 测试在 `services/` 下、`pythonpath=["."]`、`asyncio_mode=auto`、test 目录有 `__init__.py`）；根目录 tests 用根 `tests/` 约定（无 `__init__.py`）。
- 全程保持绿色基线（worker 48 + 全量 154 不退）。

## 6. 实弹验证（gated）

根抽取的**端到端行为**只能靠真实注册实跑确认（真 ixBrowser + 干净 IP + 真验证码）。当前 1024proxy BE 池已烧，实跑验证**待干净/移动 IP**。本里程碑交付：① 静态/单测层面证明抽取无逻辑丢失（抽取前后逐行对照 + register_outlook 调用序列不变）；② native flow 接线 + 能力适配器 + 单测全绿。实跑端到端验证作为后续 gate（拿到干净 IP 即跑 `outlook_reg_loop` 确认根 loop 不退、跑 worker flow 确认原生路径出号）。

## 7. 非目标（YAGNI）

- 不动 `tasks.py`、不动 `account_service` 持久化路径。
- 不抽 Arkose 为独立能力（兜底逻辑留 `_solve_signup_captcha`）。
- 不做 `EmailPoolService`（worker 持久化走 account_service）。
- 不碰其它平台（Gmail/下游留各自里程碑）。
- 不改根 loop 的对外行为（纯函数抽取，调用序列/返回不变）。

## 8. 风险

- **根抽取破坏 register_outlook**：缓解——纯函数抽取、抽取前后逐行对照、register_outlook 调用序列与返回不变、worker 与根 loop 都 import 同一份；ast/import 烟测 + 人工 diff 审查；实跑验证 gated（§6）。
- **能力/flow 接线偏差**：fake-bundle 单测覆盖步骤序列与转接。
