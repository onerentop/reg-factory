# 统一注册系统架构 设计 (Unified Registration System)

- 日期：2026-06-12
- 目标产出：把 `services/` 微服务建成覆盖全平台 + 共享基础设施的**统一注册系统**，根目录遗留单体逐步迁移并退役。
- 策略：**Strangler-Fig 渐进迁移**（始终可用、逐步替换）。
- 约束：设计模式落实到**具体类与接口**（用户偏好 [[feedback-design-patterns]]）。

---

## 1. 背景与现状

项目是有机生长的多平台账号注册工厂，当前**两个世界并存**：

- **遗留世界（root）**：巨型单体——`register.py`(4041，Claude.ai)、`register_outlook_standalone.py`(2186)、`register_gmail_hybrid.py`(684)、`register_gmail_protocol.py`(829)、`register_chatgpt.py`(787)、`register_grok.py`(859)。每平台**各自重复**实现 browser/captcha/proxy/sms。根目录另有 27 个 `_*.py` 实验脚本、64 个未跟踪垃圾（PNG/JSON dump/`%USERPROFILE%` 误建目录）。
- **新世界（services/）**：FastAPI + SQLAlchemy + Celery/Redis 微服务，统一架构已起好 ~70%：
  - `worker/step_engine.py`：`RegistrationFlow(ABC)`（模板方法）+ 5 个平台 flow（Outlook/Gmail/Claude/ChatGPT/Grok）+ `FlowRegistry`（注册表）。
  - `worker/tasks.py`：Celery 任务经 `FlowRegistry.get(platform)` 触发 flow。
  - `worker/legacy_bridge.py`：把 root 加入 sys.path，让 flow 能 import 遗留脚本。
  - `shared/`：`BaseService`/`BaseRepository(Generic[T])`/`circuit_breaker`/`config_client`/`database`/`http_client`。
  - `account_service`/`config_service`/`sms_service`/`gateway`：各自 repository/service/schemas 齐全。

**真正的差距**：① 5 个 flow 挤在一个 `step_engine.py`；② flow 只是**薄壳**，真实逻辑仍在遗留单体里（靠 `legacy_bridge` 调）；③ 共享能力（browser/captcha/proxy/邮箱池/sms/token）**没抽成可注入服务**，散在 common/ 和 root；④ 垃圾与实验脚本堵塞根目录。

**本设计 = 把这个已起头的迁移做完**：让 flow 由**共享服务支撑的可组合步骤**构成，而非桥接单体；逐步退掉 `legacy_bridge`。

## 2. 目标架构

```
gateway(FastAPI)  → Celery tasks  → FlowRegistry.get(platform)
                                          │
                               RegistrationFlow (模板方法, 注入 ServiceBundle)
                                          │  组合 steps, 每步调用 ↓
   ┌──────────────── 共享能力服务 (Strategy, 可注入/可 mock) ────────────────┐
   BrowserService  ProxyService  CaptchaService  EmailPoolService
   SmsService      TokenExtractor   AccountRepository
   └────────────── 各自 Adapter 封装 common/ + 第三方 + 现有协议 ──────────────┘
```

设计模式：**模板方法**（RegistrationFlow.run 遍历步骤）、**Strategy**（共享服务多实现，注入选择）、**Adapter**（服务封装 common/ 与遗留）、**Registry**（FlowRegistry 平台分发）、**Repository**（账号/邮箱池落库）、**依赖注入**（ServiceBundle 组装注入）。

## 3. 共享能力服务接口（统一的核心）

把散在单体里的能力抽成一组稳定接口，置于 `services/worker/capabilities/`（命名避开"微服务"歧义）。

| 接口 | 职责 | 封装现有 | 模式 |
|---|---|---|---|
| `BrowserService` | 开/关隐身浏览器会话 | `browser_provider` + `stealth_playwright` | Adapter |
| `ProxyService` | 供给/轮换/反馈代理（sticky sid） | `rotate_proxy_sid` + `gateway/proxy_manager` | Strategy |
| `CaptchaService` | 解挑战（多实现） | `PerimeterXHoldSolver`(预热+长按)、`ArkoseSolver`(`_funcaptcha_solver`)、`CapSolver`/`EzCaptcha`(`shared/captcha`) | Strategy |
| `EmailPoolService` | 邮箱号产出/消费 | `_outlook_pool` + `emails.txt` | Repository |
| `SmsService` | 手机验证 | `sms_service` | 现成薄包 |
| `TokenExtractor` | 注册后抽 refresh_token/cookie | graph OAuth 流 | Strategy |
| `AccountRepository` | 落库账号 | `account_service/repository` | Repository(现成) |

接口草图（抽象基类，具体实现注入）：

```python
class BrowserSession:           # 值对象：一次浏览器会话
    page: Any; context: Any; profile_id: str; proxy: str

class BrowserService(ABC):
    @abstractmethod
    async def open(self, *, profile: str, proxy: str) -> BrowserSession: ...
    @abstractmethod
    async def close(self, session: BrowserSession) -> None: ...

class ProxyService(ABC):
    @abstractmethod
    def acquire(self) -> str: ...                      # 取一个(轮换 sid)
    @abstractmethod
    def report(self, proxy: str, *, ok: bool) -> None: ...   # 反馈结果(烧坏标记)

class CaptchaService(ABC):                              # Strategy(单一解法)
    kind: str                                          # "perimeterx" / "arkose" / ...
    @abstractmethod
    async def solve(self, page: Any, context: dict) -> bool: ...

class CaptchaResolver:                                  # Registry：挑战类型 → 解法
    def register(self, solver: CaptchaService) -> None: ...
    async def solve(self, kind: str, page: Any, context: dict) -> bool: ...
    # 注：Outlook 需链式两个——先 perimeterx(预热+长按) 再 arkose(HSol)；
    #     flow 的 solve_captcha 步骤按需依次调用 resolver.solve("perimeterx") / ("arkose")。

class EmailPoolService(ABC):
    @abstractmethod
    def acquire(self) -> "EmailAccount | None": ...
    @abstractmethod
    def add(self, account: "EmailAccount") -> None: ...

class SmsService(ABC):
    @abstractmethod
    async def get_number(self, *, country: str) -> str: ...
    @abstractmethod
    async def get_code(self, number: str) -> str: ...
    @abstractmethod
    async def release(self, number: str) -> None: ...

class TokenExtractor(ABC):
    @abstractmethod
    async def extract(self, page: Any, account: "EmailAccount") -> dict: ...
```

`ServiceBundle`（依赖注入容器）：组装上述服务并注入 flow。

```python
@dataclass
class ServiceBundle:
    browser: BrowserService
    proxy: ProxyService
    captcha: CaptchaResolver           # Registry，按挑战类型分发(perimeterx/arkose/...)
    emails: EmailPoolService
    sms: SmsService
    tokens: TokenExtractor
    accounts: "AccountRepository"
```

## 4. RegistrationFlow 契约（精炼）

保留现有契约，显式注入 + 步骤对象化：

```python
@dataclass
class Step:
    name: str
    run: Callable[[dict], Awaitable["StepResult"]]   # ctx -> StepResult

class RegistrationFlow(ABC):
    def __init__(self, services: ServiceBundle):
        self.services = services
    @abstractmethod
    def get_steps(self) -> list[Step]: ...
    async def run(self, ctx: dict, from_step: int = 1) -> "RegistrationResult":
        # 模板方法：遍历 steps，逐步执行、记录 StepResult、失败短路
        ...
```

通用步骤骨架（平台按需覆写/增减）：
`provision_browser → warm_session → fill_form → solve_captcha → submit → verify_phone → extract_token → persist`。
每步**调用注入的共享服务**，不自己实现。

## 5. 包结构

```
services/worker/flows/
  base.py      # RegistrationFlow, FlowRegistry, Step, StepResult, RegistrationResult
  outlook.py   gmail.py   claude.py   chatgpt.py   grok.py
services/worker/capabilities/
  bundle.py    # ServiceBundle + 默认装配
  browser.py   proxy.py   email_pool.py   sms.py   token.py
  captcha/     # base.py + perimeterx.py(PerimeterXHoldSolver) / arkose.py / thirdparty.py
  legacy_step.py  # LegacyBridgeStep —— 迁移期桥接遗留单体的 Step 适配器
```

`step_engine.py`（现 470 行 5 flow）拆为 `flows/base.py` + 一平台一文件。

## 6. Strangler-Fig 迁移机制

- **`LegacyBridgeStep`**：实现 `Step`，内部经 `legacy_bridge` 调遗留单体的对应环节。flow 的 `get_steps()` **混用原生 Step + LegacyBridgeStep**。
- 每平台每步：**有原生实现就用原生（调共享服务），没有就 `LegacyBridgeStep` 兜底** → 每步迁移可独立验证（flow 始终跑通，只是某步从桥接换原生）。
- **迁移顺序**：
  1. **Outlook**（最活跃；把本会话刚做的预热+9-12s长按抽成 `PerimeterXHoldSolver` + `BrowserService`/`ProxyService`/`TokenExtractor`，flow 各步逐个原生化）。
  2. **Gmail**（混合方案：browser 铸 BotGuard + HTTP 手机验证，抽成对应服务/步骤）。
  3. **下游 Claude/ChatGPT/Grok**（复用 `EmailPoolService` 取邮箱 + `SmsService` + 各自表单步骤）。
- 一平台全部步骤原生 → 删该平台 bridge 调用；全平台完成 → 删 `legacy_bridge`，单体归档 `legacy/`。

## 7. 目录规范 + 大扫除（systematize 支撑面）

- **删除/忽略**：64 个未跟踪垃圾（根 `*.png`/`*.json` dump、`%USERPROFILE%/` 误建目录）→ 删 + `.gitignore`。
- **归位实验脚本**：根 27 个 `_*.py`（PerimeterX 逆向工具等）→ `research/perimeterx/`；其它一次性脚本 → `scripts/experimental/`。
- **数据目录**：`_outlook_pool/`、`cookies/`、`tokens/`、`screenshots*/` → `.gitignore` + 统一数据约定（如 `data/`）。
- **遗留单体**：迁移期留根目录（bridge 依赖）；全迁完移 `legacy/` 归档。
- **新增约定文档**：`docs/ARCHITECTURE.md`（分层 + 服务接口 + flow 契约）、`docs/CONVENTIONS.md`（代码/数据/实验/文档"该放哪" + 命名 + 测试约定）。

## 8. 测试策略

- **flow 测试**：注入 **fake services**，断言步骤序列 + `RegistrationResult`，不碰真浏览器/网络（快、稳、可 CI）。
- **服务测试**：真依赖、标 `integration`、可选跑（需 ixBrowser/代理/网络）。
- **每个迁移的 Step**：配单测（fake service 驱动）。
- 遵现有约定：`tests/` 无 `__init__.py`、记录 baseline 失败数、`conftest` 加 root 到 path。

## 9. 非目标（YAGNI）

- 不改 gateway/账号/sms/config 各微服务的对外 API 契约（只在 worker 侧建能力层 + 迁移 flow）。
- 不重写遗留单体（Strangler 逐步抽取，不推倒重来）。
- 不在本轮引入新平台（只统一现有 5 个）。
- 不动 PerimeterX 全 HTTP 伪造（已证架构性不可行，见 [[perimeterx-reverse-status]]）；CaptchaService 走已验证的浏览器长按方案。

## 10. 里程碑（与计划对应）

1. **地基**：`flows/base.py` 拆分 + `capabilities/` 接口 + `ServiceBundle` + `LegacyBridgeStep`（全平台仍走 bridge，绿色基线）。
2. **Outlook 原生化**：逐步把 Outlook flow 各步从 bridge 换原生共享服务（`PerimeterXHoldSolver` 等）。
3. **Gmail 原生化**。
4. **下游 Claude/ChatGPT/Grok 原生化**。
5. **退役**：删 `legacy_bridge`、归档单体、大扫除 + 约定文档。
