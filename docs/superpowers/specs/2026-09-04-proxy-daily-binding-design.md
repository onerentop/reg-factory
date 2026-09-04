# 代理池批量导入与「当天一 IP 一窗口」绑定设计

- 日期：2026-09-04
- 需求：导入 Webshare 100 条静态 IP 到代理列表；每次注册**各自**从代理列表选一个代理；代理列表要能看到绑定的窗口和个数；**当天不允许一个 IP 绑定多个窗口**。
- 核心变化：新增 `proxy_bindings` 绑定表，用 `UNIQUE(proxy_id, bound_date)` 在**数据库层**硬保证当天唯一；注册路由的代理解析从「循环外一次」改为「每个任务各抢一个」。

## 0. 现状与差距（已核对代码）

| 点位 | 现状 | 差距 |
|---|---|---|
| 代理导入 | 仅单条 `POST /proxy`，前端一次加一个 | 无批量导入，100 条要手点 100 次 |
| 代理模型 | `type/host/port/username/password/status/region` | 未存出口 IP，无任何绑定字段 |
| 注册取代理 | `_resolve_proxy()` 在 `for index in range(body.count)` **循环外**只解析一次（`routers/registration.py:93`） | 一批 N 个号，N 个窗口全绑同一 IP——正是要禁的行为 |
| 窗口 | ixBrowser profile，成功改名保留、失败删除（`worker/flows/gmail.py:76`） | DB 无 proxy ↔ profile_id 关联 |
| 账号表 | `Account.proxy_used` 仅存代理串文本 | 无 profile_id、无外键，查不出「该 IP 绑了哪些窗口」 |

**架构硬约束**（`services/SERVICES_RUN.md`）：子进程不直接写 SQLite，任务状态与结果统一由 API 父进程保存。因此窗口 ID 回填**必须走事件流**，不能让 worker 直连数据库。

## 1. 已确认的产品口径

| 议题 | 决定 |
|---|---|
| 什么算「当天已占用」 | **建了窗口就算**，不管注册成功失败 |
| 池子不够时 | **能跑几个跑几个**，剩余明确拒绝并提示「已启动 n/N」 |
| 「当天」边界 | **本地零点重置**（Asia/Shanghai 自然日） |
| 手动指定代理 | **同样受限**，数量强制为 1；该 IP 今日已用则拒绝 |
| 列表展示 | **今日配额 + 累计 + 可展开明细** |
| Webshare 协议 | **HTTP** |
| claimed 但窗口没建成 | **删除记录，还回当天配额** |

## 2. 数据模型

```python
# services/gateway/models.py
class ProxyBinding(TimestampMixin, BaseModel):
    __tablename__ = "proxy_bindings"
    __table_args__ = (
        UniqueConstraint("proxy_id", "bound_date", name="uq_proxy_bindings_proxy_date"),
        Index("ix_proxy_bindings_proxy_date", "proxy_id", "bound_date"),
    )
    proxy_id     = Column(ForeignKey("proxy_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    bound_date   = Column(Date, nullable=False)        # 本地自然日，非 UTC
    task_id      = Column(String(64), nullable=True, index=True)
    profile_id   = Column(String(32), nullable=True)   # ixBrowser 窗口 id，事件回填
    profile_name = Column(String(255), nullable=True)  # 窗口名，成功后=邮箱
    platform     = Column(String(32), nullable=True)
    status       = Column(String(20), nullable=False, default="claimed")
```

**时区**：`TimestampMixin` 的 `created_at/updated_at` 是 UTC，`bound_date` 必须用本地日期（`datetime.now().date()`）计算，两者不可混用。

### 2.1 状态机与释放规则

```
claimed ──(worker 建成窗口, 事件回填)──> opened ──(任务终态)──> success / failed
   │
   └──(窗口从未建成: ixBrowser 未启动 / 代理连不上 / create 失败)──> 删除记录，还回配额
```

- `claimed`：路由抢占成功、任务已派发，窗口尚未创建
- `opened`：`profile_id` 已回填 → **当天永久占用**
- `success` / `failed`：任务终态，仍占用当天
- 从未进入 `opened` 的 `claimed` 记录 → 删除

**崩溃恢复**：API 重启时把未完成 Job 标记 `interrupted` 的现有逻辑中，同步清理对应的 `claimed` 未 opened 记录，避免一次崩溃白烧若干 IP。

## 3. 分配器（策略模式，纯逻辑）

```python
# services/gateway/proxy_manager.py
class DailyUniqueAllocator(ProxyAllocator):
    """装饰器：先滤掉今日已绑定的，再委托内层策略挑选。"""
    def __init__(self, inner: ProxyAllocator, bound_today: set[str]):
        self._inner, self._bound = inner, bound_today

    def select(self, proxies: list[dict]) -> dict | None:
        return self._inner.select([p for p in proxies if str(p.get("id")) not in self._bound])
```

内层默认 `LeastUsedAllocator`（累计绑定数最少优先），使 100 个 IP 均匀轮转，避免反复薅同几个。该类无 DB 依赖，可纯单测。

## 4. 抢占服务（事务与冲突重试）

```python
# services/gateway/proxy_binding_service.py
@dataclass(frozen=True)
class ProxyClaim:
    proxy_url: str        # 已组装的连接串，密码不出服务端
    binding_id: UUID
    proxy_id: UUID

class ProxyBindingService:
    async def claim(task_id, platform) -> ProxyClaim | None         # 原子抢占，池空返 None
    async def claim_specific(proxy_id, task_id, platform) -> ProxyClaim | None
    async def mark_opened(task_id, profile_id, profile_name)        # 事件回填
    async def mark_terminal(task_id, status)                        # success / failed
    async def release_unopened(task_id)                             # 删 claimed 未 opened
    async def today_summary() -> dict[UUID, dict]                   # 列表页聚合
```

`claim` 流程：取候选集（`status in (active, available)`）→ `DailyUniqueAllocator.select` → `INSERT` binding → 撞 `IntegrityError`（被并发任务抢走）则把该 id 加入已占集合、重试下一个 → 候选耗尽返回 `None`。

**唯一约束是最后一道闸**，不依赖「先查后插」的应用层判断。

**实现坑**：AsyncSession 撞了 `IntegrityError` 之后整个事务进入失败态，不 rollback 就继续发语句会抛 `PendingRollbackError`。重试必须用嵌套事务隔离每次尝试：

```python
try:
    async with session.begin_nested():      # SAVEPOINT，失败只回滚这一次尝试
        session.add(binding)
except IntegrityError:
    bound.add(proxy_id); continue           # 外层事务仍可用，换下一个 IP
```

这样第 5 节里「binding 与 enqueue 同事务提交」才成立——否则一次冲突就会把待提交的 Job 一起回滚掉。

## 5. 注册路由改造

`services/gateway/routers/registration.py`——把代理解析从循环外挪进循环：

```python
svc = ProxyBindingService(session)
if body.proxy_id and body.count > 1:
    raise HTTPException(422, "手动指定代理时数量只能为 1")

task_ids, skipped = [], 0
for index in range(body.count):
    task_id = str(uuid.uuid4())
    claim = (await svc.claim_specific(body.proxy_id, task_id, platform)
             if body.proxy_id else await svc.claim(task_id, platform))
    if claim is None:
        if body.proxy_id:
            raise HTTPException(409, "该代理今日已绑定窗口")
        skipped = body.count - index      # 自动分配：池子见底，部分派发
        break
    await job_service.enqueue(task_id, platform)
    await session.commit()                # 先提交 queued + binding，子进程才能安全更新
    await runtime.submit_registration(task_id, platform=platform, idx=index,
                                      proxy=claim.proxy_url, config=config)
    task_ids.append(task_id)

return {"task_ids": task_ids, "dispatched": len(task_ids), "skipped": skipped,
        "message": f"当天可用 IP 不足，已启动 {len(task_ids)}/{body.count}" if skipped else None}
```

注意 `binding` 的 INSERT 必须与 `enqueue` 在**同一个事务**内提交，否则「抢到了 IP 但任务没落库」会留下永不回收的悬挂占用。

## 6. 窗口 ID 回填（走事件流）

**现状核对**：`emit: Callable[[dict], None]` 只到 `worker/tasks/registration.py::execute_registration` 这一层；flow 步骤签名是 `(context, services)`，而 `RegistrationFlow.__init__(services)` 目前恒为 `None`（base.py:39「本里程碑各平台仍走 LegacyBridgeStep，可为 None」）。这个 `services` 注入位正是为此预留的扩展点。

**为什么必须尽早发**：若等 flow 跑完再回传 profile_id，子进程中途崩溃就会丢失「窗口已建成」的事实，导致 `release_unopened` 错误地把已经暴露给目标站点的 IP 还回池子——恰好破坏核心规则。因此必须在窗口创建成功的**当下**发出。

**注入 emitter**（接口 + 具体实现，走既有 `services` 位）：

```python
# services/worker/flows/base.py
class TaskEventEmitter(ABC):
    @abstractmethod
    def emit(self, event_type: str, data: dict) -> None: ...

class QueueEventEmitter(TaskEventEmitter):
    """把事件塞进 multiprocessing.Queue，由父进程落库。"""
    def __init__(self, emit: Callable[[dict], None], task_id: str, platform: str): ...
    def emit(self, event_type, data):
        self._emit({"type": event_type, "task_id": self._task_id,
                    "platform": self._platform, **data})
```

`execute_registration` 构造 `QueueEventEmitter(emit, task_id, platform)` 并经 `FlowRegistry.get(platform, services=...)` 注入；gmail / outlook flow 在 `open_and_connect` 返回 `pid` 的下一行调用：

```python
services.emit("binding", {"profile_id": pid, "profile_name": name})
```

父进程 `worker/local_task_manager.py::_handle_event` 新增分支：

```python
elif event_type == "binding":
    await ProxyBindingService(session).mark_opened(
        task_id, event["profile_id"], event.get("profile_name"))
```

终态分支（`result` / `failed` / `done`）调 `mark_terminal`；`failed` 且从未 opened 时调 `release_unopened`。`services` 为 `None` 时所有 emit 调用需静默跳过，保持既有流程可单独运行。全程遵守「子进程不写库」。

## 7. 批量导入

`POST /proxy/import`，body `{text, type: "http", skip_duplicates: true}`。

解析器置于纯函数模块 `services/gateway/proxy_import.py`（无 DB 依赖）：

```python
@dataclass(frozen=True)
class ProxyDraft:  type; host; port; username; password

@dataclass(frozen=True)
class InvalidLine: line_no; raw; reason

def parse_proxy_lines(text: str, default_type: str) -> tuple[list[ProxyDraft], list[InvalidLine]]
```

支持格式：`host:port:user:pass`（Webshare 导出格式）、`user:pass@host:port`、`host:port`、带 `scheme://` 前缀；跳过空行与 `#` 注释。去重按 `(host, port)` 与库内比对。返回 `{imported, duplicates, invalid: [{line_no, raw, reason}]}`。导入记录 `status="active"`，`region` 留空待检测。

### 7.1 顺带修复的既有缺陷

`common/ixbrowser_provider.py:112-120` 对 `host:port:user:pass` 格式**硬编码为 socks5**。Webshare 这批是 HTTP，不修则窗口内代理协议填错、直接连不上。改为按调用方传入类型决定，默认行为不变以免影响 1024proxy。

## 8. API 变更

| 端点 | 变更 |
|---|---|
| `GET /proxy` | 每行新增 `today_bound` / `today_profile_name` / `total_bound` / `available_today`；一次 GROUP BY 聚合，不做 N+1 |
| `GET /proxy/{id}/bindings` | 新增，明细分页 `[{bound_date, profile_id, profile_name, platform, status, created_at}]` |
| `GET /proxy/quota` | 新增，`{total, used_today, available_today}` |
| `POST /proxy/import` | 新增，见第 7 节 |
| `POST /register/{platform}` | 返回体新增 `dispatched` / `skipped` / `message` |

## 9. 前端

**ProxyPage**
- 顶部「批量导入」按钮 → Modal（TextArea 粘贴 + 类型下拉默认 HTTP + 「跳过重复」勾选），提交后展示导入结果统计
- 表格新增「今日 / 累计」列：`今日 1/1` 红标、`今日 0/1` 绿标，附 `累计 N`
- `expandable.expandedRowRender` 懒加载 `/proxy/{id}/bindings` 明细小表
- 顶部统计条新增「今日可用 63/100」

**AccountsPage**
- 代理下拉中今日已用满的选项**标灰禁选**并加后缀「（今日已用）」
- 选中具体代理时数量输入框锁为 1 并提示
- 提交后 `skipped > 0` 时 `message.warning`「当天可用 IP 不足，已启动 3/10」

## 10. 测试

全部为纯逻辑 / mock 测试，**不触发真实注册与代理请求**。

| 文件 | 覆盖 |
|---|---|
| `tests/gateway/test_proxy_import.py` | 4 种格式、空行注释、非法行、去重 |
| `tests/gateway/test_proxy_binding_service.py` | claim 排除今日已绑 / `IntegrityError` 换下一个 / 池空返 None / `release_unopened` 只删未 opened |
| `tests/gateway/test_proxy_routes.py`（扩展） | import 端点、bindings 端点、列表聚合字段 |
| `tests/gateway/test_registration_routes.py`（扩展） | 部分派发 3/10、`count>1` → 422、已用 → 409、每任务代理互不相同 |
| `tests/worker/test_local_task_manager.py` | binding 事件回填、失败释放 |
| `frontend/src/pages/ProxyPage.test.tsx`（扩展） | 新列渲染、导入 Modal |

## 11. 迁移

新 alembic revision：建 `proxy_bindings` 表 + 唯一约束 + 索引。不改动 `proxy_entries`，导入的 100 条走普通 INSERT。
