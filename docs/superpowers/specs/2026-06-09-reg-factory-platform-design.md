# RegFactory 管理平台设计规格

## 1. 项目概述

将现有的纯 Python 账号自动注册系统（reg-factory）升级为完整的微服务管理平台，新增 Web 管理后台、数据库持久化、实时监控和对外 API。

### 1.1 核心目标

- 提供可视化管理界面，替代命令行操作
- 微服务架构，SMS Service 和 Account Service 可独立对外暴露
- 低耦合、高扩展性——新接码平台/指纹浏览器/微服务均可通过添加文件快速接入
- 实时监控注册进度、日志、资源状态

### 1.2 技术栈

| 层级 | 技术选型 |
|------|---------|
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 |
| API 网关 | Python FastAPI（:8000） |
| SMS 微服务 | Python FastAPI（:8001） |
| Account 微服务 | Python FastAPI（:8002） |
| Config 微服务 | Python FastAPI（:8003） |
| 注册 Worker | Celery + gevent 协程池 |
| 数据库 | PostgreSQL 16 + PgBouncer 连接池代理 |
| 消息 | Redis 7（Celery Broker + Streams + Pub/Sub） |
| 实时通信 | WebSocket（Gateway ↔ React） + Redis Streams（Worker → Gateway） |
| 浏览器自动化 | Playwright + BrowserProvider 抽象层（支持 ixBrowser/AdsPower/Multilogin） |

## 2. 系统架构

### 2.1 服务拓扑

```
                    ┌──────────────┐     ┌──────────────┐
                    │  React SPA   │     │  外部服务     │
                    │  管理后台     │     │  (直连API)    │
                    └──────┬───────┘     └───┬─────┬────┘
                           │                 │     │
                    REST + WebSocket    REST  │  REST│
                           │                 │     │
                    ┌──────▼───────┐         │     │
                    │   Gateway    │         │     │
                    │   :8000      │         │     │
                    │  JWT认证      │         │     │
                    │  路由聚合     │         │     │
                    │  WebSocket Hub│         │     │
                    └──┬──┬──┬──┬──┘         │     │
                       │  │  │  │            │     │
            ┌──────────┘  │  │  └────────┐   │     │
            ▼             ▼  ▼           ▼   ▼     ▼
    ┌───────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐
    │SMS Service│  │ Account  │  │  Config   │  │Reg Worker│
    │  :8001    │  │ Service  │  │  Service  │  │ Celery   │
    │  对外暴露  │  │  :8002   │  │  :8003    │  │          │
    │  4平台适配 │  │  对外暴露 │  │  热更新   │  │ 注册流程 │
    └─────┬─────┘  │  CRUD    │  │  版本历史  │  │ 步骤重试 │
          │        └────┬─────┘  └─────┬─────┘  └──┬──┬────┘
          │             │              │            │  │
          └─────────────┴──────────────┴────────────┘  │
                              │                        │
                    ┌─────────▼─────────┐    ┌────────▼────────┐
                    │   PostgreSQL 16    │    │     Redis 7     │
                    │  PgBouncer :6432   │    │  Streams/Queue  │
                    │  Schema 隔离       │    │  Pub/Sub        │
                    └───────────────────┘    └─────────────────┘
```

### 2.2 服务间通信

| 调用方 | 被调用方 | 协议 | 场景 | 同步/异步 |
|--------|---------|------|------|----------|
| React | Gateway | REST + WebSocket | 页面数据 + 实时事件 | 同步 / 长连接 |
| Gateway | SMS/Account/Config | 内部 HTTP | 代理转发 | 同步 |
| Gateway | Worker | Redis Queue | 发布注册任务（Celery delay） | 异步 |
| Worker | SMS Service | 内部 HTTP | 请求验证码 | 同步 |
| Worker | Account Service | 内部 HTTP | 写入注册结果/日志 | 同步 |
| Worker | Gateway | Redis Streams | 实时推送步骤进度 | 异步 |
| Config | All | Redis Pub/Sub | 配置变更广播 | 异步 |
| 外部服务 | SMS/Account | 公开 REST | 直连调用（API Key 认证） | 同步 |

### 2.3 数据库 Schema 隔离

```
PostgreSQL
├── sms.*           — 接码平台配置、订单记录
├── account.*       — 账户表、注册步骤、步骤日志
├── config.*        — 配置项、版本历史、服务注册表
├── gateway.*       — 用户认证、API Key、操作审计
└── shared.*        — 集中日志表
```

## 3. 前端设计

### 3.1 整体布局

亮色双栏导航（Linear/Notion 风格）：
- 左侧图标侧栏（48px）— 一级导航
- 二级文字导航面板（180px）— 子菜单
- 右侧主内容区 — 页面内容

### 3.2 页面清单

| 页面 | 路由 | 功能 |
|------|------|------|
| 仪表盘 | `/dashboard` | 账户统计卡片、资源余额、注册趋势图、实时活动流 |
| 接码平台配置 | `/sms` | 各平台 API Key 配置、启用/禁用、余额查询、优先级排序 |
| Outlook 账户 | `/accounts/outlook` | 分页表格、行内展开步骤条、失败重试、批量操作、日志查看 |
| Google 账户 | `/accounts/google` | 同 Outlook |
| 代理配置 | `/proxy` | 代理列表 CRUD、健康状态、分配策略、一键测试 |
| 并发设置 | `/settings/concurrency` | 并发滑块、分平台限制、资源监控面板、智能保护开关 |
| 配置中心 | `/settings/config` | 全局配置管理、版本历史、热更新 |
| 日志查询 | `/logs` | 按服务/级别/时间/trace_id 筛选、实时日志流 |
| 告警通知 | `/alerts` | 告警规则配置、通知渠道、历史告警记录 |
| API Key 管理 | `/settings/api-keys` | 给外部服务发放/撤销 API Key |
| 定时任务 | `/settings/schedules` | 计划注册、定时清理、cron 配置 |
| 操作审计 | `/audit` | 敏感操作记录、按用户/时间/类型筛选 |
| 用户管理 | `/settings/users` | 用户 CRUD、角色分配 |
| 主题设置 | `/settings/theme` | 预设主题切换、自定义颜色、紧凑模式、圆角大小 |
| 数据导入 | `/settings/import` | 上传历史 txt/json 文件批量导入 |

### 3.3 账户管理页面详细设计

**表格功能：**
- 分页（每页 20/50/100 可选）
- 列：邮箱、平台、状态（成功/失败/运行中）、进度（3/7）、注册时间、操作
- 筛选：状态、时间范围、关键词搜索
- 排序：时间、状态
- 多选 checkbox + 顶部批量操作栏

**行内展开（点击行）：**
- 水平步骤条：每步显示 ✓/✗/数字，失败步骤高亮红色
- 错误信息卡片：具体报错内容
- 操作按钮：「从此步重试」「换接码平台重试」「查看完整日志」

**批量操作：**
- 批量重试（从失败步骤）
- 批量删除（二次确认）
- 批量导出（txt / csv / json / SUB2API / CPA 格式）
- 批量注册（启动 N 个新任务）

**导出格式：**
- 原始格式：`email----password----refresh_token----client_id`
- CSV：标准 CSV，含表头
- JSON：结构化 JSON 数组
- SUB2API 格式：access_token/refresh_token 标准 Token
- CPA 格式：Codex 授权文件
- 自定义模板：用户定义字段顺序和分隔符

### 3.4 主题系统

**实现方案：** CSS 变量 + ThemeProvider + Ant Design ConfigProvider 适配

**语义化 Token（非具体颜色）：**
- `--bg-primary`、`--bg-card`、`--bg-sidebar`
- `--text-primary`、`--text-secondary`
- `--border`、`--accent`、`--success`、`--error`、`--warning`

**内置主题：** Light（默认）/ Dark / Cyberpunk / Terminal

**自定义主题：** 设置页可视化调整主色调、背景、侧边栏、文字色、圆角大小

**持久化：** localStorage 即时生效 + 用户偏好 API 跨设备同步 + 系统 prefers-color-scheme 跟随

**扩展：** `themes/` 目录新增一个 ts 文件即可添加主题，零改组件代码

**目录结构：**
```
frontend/src/theme/
├── tokens.ts              — CSS 变量 token 定义
├── themes/
│   ├── light.ts           — ☀️ 亮色
│   ├── dark.ts            — 🌙 暗色
│   ├── cyberpunk.ts       — 💜 赛博紫
│   └── terminal.ts        — 🌿 终端绿
├── ThemeProvider.tsx       — React Context + CSS 变量注入
├── useTheme.ts            — Hook：获取/切换主题
├── antd-adapter.ts        — CSS 变量 → Ant Design token 映射
└── ThemeEditor.tsx         — 设置页主题编辑器组件
```

## 4. 后端设计

### 4.1 微服务共享基础库

```
services/shared/
├── base_service.py        — FastAPI 基类（自动注册到 Config、挂载日志/健康检查/认证）
├── base_model.py          — SQLAlchemy 基类
├── base_schema.py         — Pydantic 基类（分页/响应/错误码）
├── log_handler.py         — 统一日志 Handler（异步批量写入 PG）
├── config_client.py       — Config 热更新客户端（启动拉取 + Redis 订阅变更）
├── http_client.py         — 带连接池/限流/熔断的 HTTP 客户端
├── auth.py                — JWT 认证 + API Key 认证中间件
├── audit.py               — 操作审计装饰器
├── concurrency.py         — DynamicSemaphore（可动态调整大小的信号量）
└── browser_providers/     — 指纹浏览器适配器
    ├── base.py            — BrowserProvider 抽象基类
    ├── ixbrowser.py       — ixBrowser 适配器
    └── playwright.py      — 原生 Playwright 降级兜底
```

**BaseService 自动提供的能力（零额外代码）：**
- 统一日志采集（→ shared.logs 表）
- 配置热更新（从 Config Service 拉取 + 监听变更）
- 健康检查端点（GET /health）
- API Key / JWT 认证中间件
- 请求 trace_id 传播
- PgBouncer 连接池
- OpenAPI/Swagger 文档自动生成

### 4.2 SMS Service（:8001）

**对外 REST API：**

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/sms/providers` | 列出所有已注册平台（含 config_schema） |
| GET | `/sms/providers/{name}/balance` | 查询指定平台余额 |
| POST | `/sms/number/acquire` | 获取号码 |
| GET | `/sms/number/{order_id}/code` | 轮询验证码 |
| POST | `/sms/number/{order_id}/complete` | 完成激活 |
| POST | `/sms/number/{order_id}/cancel` | 取消释放 |
| GET | `/sms/config` | 获取平台配置 |
| PUT | `/sms/config/{name}` | 更新平台配置 |

**策略模式 + 自动注册：**

```python
# sms_service/providers/base.py
class SMSProvider(ABC):
    name: str
    config_schema: dict  # 前端动态渲染配置表单

    async def get_balance(self) -> float: ...
    async def get_number(self, service: str, country: str) -> AcquireResult: ...
    async def get_code(self, order_id: str) -> CodeResult: ...
    async def complete(self, order_id: str) -> None: ...
    async def cancel(self, order_id: str) -> None: ...

def register(name: str):
    """装饰器：自动注册到 ProviderRegistry"""
```

**已实现的适配器：** HeroSMS、SMSPool、SMS Cloud、SmsBower

**扩展新平台：** 新建 `providers/xxx.py`，加 `@register("xxx")`，实现 5 个方法。前端自动识别，零代码修改。

### 4.3 Account Service（:8002）

**对外 REST API：**

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/accounts` | 分页列表（筛选：平台/状态/时间/关键词） |
| GET | `/accounts/{id}` | 账户详情（含步骤列表） |
| POST | `/accounts` | 创建账户记录 |
| PUT | `/accounts/{id}` | 更新账户信息 |
| DELETE | `/accounts/{id}` | 删除账户 |
| POST | `/accounts/batch/delete` | 批量删除 |
| POST | `/accounts/batch/export` | 批量导出（指定格式） |
| POST | `/accounts/batch/retry` | 批量从失败步骤重试 |
| GET | `/accounts/{id}/steps` | 获取注册步骤列表 |
| PUT | `/accounts/{id}/steps/{step}` | 更新步骤状态 |
| GET | `/accounts/{id}/logs` | 获取关联日志 |
| POST | `/accounts/import` | 导入历史数据（txt/json） |

### 4.4 Config Service（:8003）

**管理的配置项：**
- 接码平台：API Key、优先级、启用/禁用
- 代理列表：地址、端口、认证、健康状态
- 注册参数：并发数、重试次数、超时时间
- 邮箱配置：OAuth Client ID、默认密码规则
- 通知设置：余额预警阈值、失败率告警
- 服务注册表：各服务地址和端口
- 浏览器配置：使用哪个指纹浏览器、连接参数

**热更新机制：**
1. 前端修改配置 → POST 到 Config Service
2. Config Service 写入 DB + 记录版本
3. 发布 Redis Pub/Sub 通知 `config:updated`
4. 各服务订阅并热加载（无需重启）

### 4.5 Gateway（:8000）

**职责：**
- JWT 认证（用户登录）
- 路由代理转发（/api/sms → SMS Service, /api/accounts → Account Service...）
- WebSocket Hub（订阅 Redis Streams，推送到前端）
- 仪表盘数据聚合（从各服务拉取数据组装）
- 告警规则评估 + 通知推送

**用户角色：**

| 角色 | 权限 |
|------|------|
| 管理员 | 全部权限（配置/用户管理/API Key/审计） |
| 操作员 | 查看 + 发起注册 + 导出（不能改配置/管理用户） |
| 只读 | 只看仪表盘和账户列表 |

### 4.6 Registration Worker

**Celery 配置：** gevent 协程池（非 prefork），单进程内高并发共享浏览器池

**注册流程编排（以 Outlook 为例）：**
1. 从 Config 获取代理 → 从 BrowserPool 借浏览器
2. 执行步骤链：填写邮箱 → 设密码 → 出生日期 → Arkose 验证 → 完成
3. 每步完成后：HTTP → Account Service 更新步骤状态 + Redis Streams 推送前端
4. 需要验证码时：HTTP → SMS Service 获取号码 + 轮询验证码
5. 全部成功：标记账户成功 + 存 Cookie/Token
6. 某步失败：标记失败步骤 + 记录错误 → 等待用户从此步重试

**步骤重试引擎：**
- 接收重试请求（指定 account_id + from_step）
- 恢复该账户的浏览器会话状态
- 从指定步骤继续执行后续步骤链
- 可选切换接码平台/代理再重试

## 5. 指纹浏览器抽象层

### 5.1 BrowserProvider 抽象基类

```python
class BrowserProvider(ABC):
    async def create_profile(self, proxy: ProxyConfig, fingerprint: FingerprintConfig | None) -> ProfileHandle: ...
    async def open_browser(self, profile: ProfileHandle) -> BrowserContext: ...
    async def close_browser(self, profile: ProfileHandle) -> None: ...
    async def delete_profile(self, profile: ProfileHandle) -> None: ...
    def supports_stealth(self) -> bool: ...
    def supports_proxy_binding(self) -> bool: ...
```

### 5.2 统一数据模型

```python
@dataclass
class ProfileHandle:
    provider: str       # "ixbrowser" / "adspower" / "playwright"
    profile_id: str     # 各平台内部 ID
    ws_endpoint: str    # CDP WebSocket 地址
    metadata: dict      # 平台特定扩展字段

@dataclass
class ProxyConfig:
    type: str           # "socks5" / "http"
    host: str
    port: int
    username: str | None
    password: str | None

@dataclass
class FingerprintConfig:
    user_agent: str | None
    language: str | None
    timezone: str | None
    resolution: tuple[int, int] | None
```

### 5.3 差异屏蔽

| 差异点 | 抽象方式 |
|--------|---------|
| 连接方式 | 统一返回 BrowserContext，内部各自处理 CDP/直接启动 |
| Profile ID | 封装在 ProfileHandle，上层不关心格式 |
| 代理绑定 | 统一 ProxyConfig，适配器内部转换 |
| 指纹配置 | 统一 FingerprintConfig，适配器映射到各平台参数 |
| Stealth 能力 | supports_stealth() 查询；自带则跳过，Playwright 则注入脚本 |

### 5.4 已实现适配器

- **IXBrowserProvider** — ixBrowser 本地 API（127.0.0.1:53200）
- **PlaywrightProvider** — 原生 Playwright + Stealth 脚本注入（降级兜底）

### 5.5 扩展

新建 `browser_providers/adspower.py`，实现 4 个方法 + 配置中心改一行 `browser_provider: "adspower"`。注册流程、Worker、前端零改动。

## 6. 并发控制

### 6.1 DynamicSemaphore

可运行时动态调整大小的信号量：
- **扩容**：立即释放差额，等待中的任务自动获取
- **缩容**：不中断运行中任务，等自然释放后生效
- **状态查询**：返回 max / active / waiting，WebSocket 推送到前端

### 6.2 多层信号量

```python
total_sem = DynamicSemaphore(10)      # 总并发上限
outlook_sem = DynamicSemaphore(5)     # Outlook 并发上限
gmail_sem = DynamicSemaphore(3)       # Gmail 并发上限
browser_sem = DynamicSemaphore(8)     # 浏览器实例上限
sms_sem = DynamicSemaphore(10)        # 接码请求并发上限
```

### 6.3 智能保护

- 内存 > 80% → 自动暂停新任务入队，< 70% 恢复
- 连续 N 次失败 → 并发自动 -2，恢复成功后逐步回升
- 队列 > 50 → 拒绝新任务，前端提示"队列已满"

### 6.4 前端设置

- 总并发 / 分平台并发：滑块 + 步进器
- 浏览器实例上限 / 接码并发上限：数字输入
- 实时资源监控面板：CPU/内存/任务队列/浏览器池可视化
- 智能保护开关
- 调整后通过 Config Service 热更新，Worker 即时 resize()

## 7. 并发优化措施

| 瓶颈 | 改进方案 |
|------|---------|
| Redis Pub/Sub 丢消息 | 事件推送改用 Redis Streams（持久化 + Consumer Group） |
| Playwright 内存爆炸 | BrowserPool 实例池 + 借还机制 + 全局上限 |
| HTTP 调用雪崩 | httpx.AsyncClient 连接池 + Semaphore 限流 + 熔断器 |
| PG 连接竞争 | PgBouncer 代理（transaction 模式）+ 日志异步批量写 |

**单机 16GB 预估并发能力：**
- ~20 并发注册任务
- ~100 并发 API 请求
- ~50 WebSocket 连接
- ~500 日志写入/秒

## 8. 配置中心

### 8.1 管理范围

接码平台配置、代理列表、注册参数、浏览器选择、通知设置、服务注册表

### 8.2 热更新流程

前端修改 → Config Service 写入 DB（记录版本） → Redis Pub/Sub `config:updated` → 各服务订阅热加载

### 8.3 版本历史

每次配置变更记录：变更人、变更时间、变更前后值。支持一键回滚到历史版本。

## 9. 集中日志系统

### 9.1 采集

统一 `RegFactoryLogHandler`，每个服务自动挂载。异步批量写入 `shared.logs` 表（攒 100 条或 1 秒 flush）。

### 9.2 日志字段

- `trace_id` — 请求链路追踪（跨服务传播）
- `service` — 来源服务名
- `level` — DEBUG / INFO / WARN / ERROR
- `account_id` — 关联账户（可选）
- `message` — 日志内容
- `extra` — JSON 扩展字段
- `created_at` — 时间戳

### 9.3 前端查询

- 筛选：服务名、级别、时间范围、trace_id、account_id、关键词
- 实时日志流（WebSocket 推送，Redis Streams `logs:stream` 频道）
- 历史日志分页表格
- 账户详情页一键跳转关联日志

## 10. 告警 & 通知系统

### 10.1 告警规则

| 规则 | 触发条件 | 默认阈值 |
|------|---------|---------|
| 接码余额不足 | 任一平台余额低于阈值 | $10 |
| 注册失败率过高 | 近 1 小时失败率超阈值 | 30% |
| 服务不可达 | 健康检查连续 3 次失败 | — |
| 代理全部不可用 | 无可用代理 | — |
| 内存使用过高 | 系统内存超阈值 | 80% |

### 10.2 通知渠道

- 页面内通知（右上角铃铛 + WebSocket 推送）
- 邮件通知
- Webhook（POST JSON，可接入飞书/钉钉/Telegram Bot）

### 10.3 告警历史

记录所有触发的告警：时间、规则、详情、是否已处理。前端可查看和标记已处理。

## 11. 用户认证 & 权限

### 11.1 认证方式

- **管理后台：** JWT（用户名 + 密码登录，Token 存 localStorage）
- **外部 API：** API Key（Header: `X-API-Key`）

### 11.2 角色权限

| 角色 | 仪表盘 | 账户管理 | 发起注册 | 配置修改 | 用户管理 | API Key |
|------|--------|---------|---------|---------|---------|---------|
| 管理员 | ✅ | ✅ 全部 | ✅ | ✅ | ✅ | ✅ |
| 操作员 | ✅ | ✅ 查看+导出 | ✅ | ❌ | ❌ | ❌ |
| 只读 | ✅ | ✅ 只看 | ❌ | ❌ | ❌ | ❌ |

### 11.3 API Key 管理

- 管理员可创建/撤销 API Key
- 每个 Key 可设置权限范围（只访问 SMS / 只访问 Account / 全部）
- 记录每个 Key 的调用量和最后使用时间

## 12. 代理管理

### 12.1 代理 CRUD

手动添加/编辑/删除代理。格式：`type://host:port:username:password`

### 12.2 健康检查

- 定时检测（默认 5 分钟一次，可配置）
- 检测方式：TCP 连接 + HTTP 请求测试
- 状态：🟢 可用 / 🟡 慢（>3s）/ 🔴 不可用
- 一键测试所有代理

### 12.3 分配策略

- 轮询（Round Robin）
- 随机（Random）
- 最少使用优先（Least Used）
- 按地区分配（可选，手动标记代理地区）
- 自动跳过不可用代理

## 13. 定时任务

### 13.1 Celery Beat 实现

| 任务 | 描述 | 默认周期 |
|------|------|---------|
| 计划注册 | 设定时间自动启动 N 个注册任务 | 用户配置 |
| 代理健康检查 | 检测所有代理可用性 | 5 分钟 |
| 接码余额检查 | 查询各平台余额，触发告警 | 10 分钟 |
| 日志清理 | 删除 N 天前的日志 | 每天凌晨 |
| 临时文件清理 | 清理截图、录屏等临时产物 | 每天凌晨 |

### 13.2 前端配置

cron 表达式可视化编辑器，支持启用/禁用/手动触发。

## 14. 操作审计

### 14.1 记录范围

- 配置变更（谁改了什么，变更前后值）
- 账户删除（谁删了哪些账户）
- API Key 创建/撤销
- 并发参数调整
- 用户角色变更
- 批量操作

### 14.2 审计日志字段

operator（操作人）、action（操作类型）、target（操作对象）、before/after（变更前后值）、ip、timestamp

### 14.3 前端查询

按用户/时间/操作类型筛选，分页展示。

## 15. 历史数据迁移

### 15.1 迁移脚本

一次性脚本，将现有文件数据导入 PostgreSQL：

| 源文件 | 目标表 | 解析规则 |
|--------|--------|---------|
| `emails.txt` | `account.accounts` | `email----password----token----client_id` 分隔 |
| `cookies/{platform}/full_*.json` | `account.accounts` + `account.cookies` | Playwright 格式 JSON |
| `_outlook_pool/*.json` | `account.accounts` | 完整账户 JSON |
| `outlook_accounts/*.txt` | `account.accounts` | 同 emails.txt 格式 |
| `*.log` | `shared.logs` | 按行解析时间戳和级别 |

### 15.2 前端导入

上传 txt/json 文件 → 后端解析 → 预览（显示将导入多少条、格式是否正确） → 确认导入。

## 16. 部署方案

### 16.1 Docker Compose

```yaml
services:
  postgres:    # PostgreSQL 16
  pgbouncer:   # 连接池代理
  redis:       # Redis 7
  gateway:     # API Gateway :8000
  sms:         # SMS Service :8001
  account:     # Account Service :8002
  config:      # Config Service :8003
  worker:      # Celery Worker（gevent）
  beat:        # Celery Beat（定时任务）
  frontend:    # React（nginx 静态托管）
```

### 16.2 开发环境

`docker-compose.dev.yml`：前端 Vite HMR + 后端 uvicorn --reload

### 16.3 无 Docker Fallback

一键启动脚本（PowerShell / Bash），按顺序启动各服务。

## 17. 设计模式总结

| 模式 | 应用场景 |
|------|---------|
| 策略模式（Strategy） | 接码平台适配器、指纹浏览器适配器 |
| 工厂 + 注册表（Registry） | @register 装饰器自动注册，按名称创建实例 |
| 模板方法（Template） | BaseService 标准化服务启动/健康检查/日志/配置加载 |
| 观察者（Observer） | Redis Streams/Pub/Sub 事件发布-订阅 |
| 熔断器（Circuit Breaker） | HTTP 调用保护（连续失败 → 熔断 → 半开探测 → 恢复） |
| 对象池（Object Pool） | BrowserPool 管理浏览器实例借还 |
| 装饰器（Decorator） | @audit 操作审计、@auth 权限检查 |

## 18. 项目目录结构

```
reg-factory/
├── frontend/                      — React SPA
│   ├── src/
│   │   ├── api/                   — API 客户端（自动生成自 OpenAPI）
│   │   ├── components/            — 通用组件
│   │   ├── pages/                 — 页面组件（按路由组织）
│   │   ├── stores/                — 状态管理（Zustand）
│   │   ├── hooks/                 — 自定义 Hooks
│   │   ├── theme/                 — 主题系统
│   │   ├── websocket/             — WebSocket 客户端
│   │   └── utils/                 — 工具函数
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── services/                      — 后端微服务
│   ├── shared/                    — 共享基础库
│   │   ├── base_service.py
│   │   ├── base_model.py
│   │   ├── base_schema.py
│   │   ├── log_handler.py
│   │   ├── config_client.py
│   │   ├── http_client.py
│   │   ├── auth.py
│   │   ├── audit.py
│   │   ├── concurrency.py
│   │   └── browser_providers/
│   │       ├── base.py
│   │       ├── ixbrowser.py
│   │       └── playwright_provider.py
│   │
│   ├── gateway/                   — API Gateway :8000
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── websocket_hub.py
│   │   ├── auth_router.py
│   │   ├── dashboard_aggregator.py
│   │   ├── alert_engine.py
│   │   ├── models.py
│   │   └── schemas.py
│   │
│   ├── sms_service/               — SMS Service :8001
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── service.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── providers/
│   │       ├── base.py
│   │       ├── hero_sms.py
│   │       ├── sms_pool.py
│   │       ├── sms_cloud.py
│   │       └── sms_bower.py
│   │
│   ├── account_service/           — Account Service :8002
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── service.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── exporter.py
│   │   └── importer.py
│   │
│   ├── config_service/            — Config Service :8003
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── service.py
│   │   ├── models.py
│   │   └── schemas.py
│   │
│   └── worker/                    — Registration Worker
│       ├── celery_app.py
│       ├── tasks.py
│       ├── outlook_flow.py
│       ├── gmail_flow.py
│       ├── step_retry_engine.py
│       └── browser_pool.py
│
├── migrations/                    — Alembic 数据库迁移
├── scripts/                       — 部署/迁移/工具脚本
│   ├── migrate_legacy_data.py
│   └── start_all.ps1
├── docker-compose.yml
├── docker-compose.dev.yml
└── docker-compose.prod.yml
```
