# 移除代理每日绑定、改回 1024proxy sid 轮换 设计

- 日期：2026-09-05
- 需求：去掉当前「每 IP 每天只绑一个窗口」的限制，改回原来「用 1024proxy、每个注册窗口轮换 sid 拿不同住宅出口 IP」的模型。彻底删除 Phase A 引入的 ProxyBinding 绑定机制；代理池管理保留；不再需要 Webshare。
- 执行方式：以原始提交 `84dd280`（并发注册轮换 1024proxy sid，每窗口不同出口 IP）为参照恢复 sid 轮换逻辑，前向删除全部绑定产物，新增迁移删表。**不采用**盲目 `git revert` Phase A 提交——其后代码已大幅演进（Ant provider、config、前端），revert 会冲突并撤掉捆绑的无关改动。

## 0. 背景

- **原始模型（要恢复的）**：`registration` 解析出一条代理串（`_pick_active_proxy` 取池中活跃条目 / `proxy_id` / 显式串），对每个并发窗口 `rotate_proxy_sid(proxy)` 轮换 1024proxy 的 sid → 每窗口不同住宅出口 IP。无每日/每 IP 限制。
- **Phase A（要删的）**：`ProxyBindingService.claim()` 按 `UNIQUE(proxy_id, bound_date)` 给每个窗口每天绑定一个池 IP；拒绝裸 proxy 串、强制 `proxy_id`；worker 跟踪绑定生命周期；前端展示已绑窗口/今日计数/配额。
- **产品口径（已确认）**：完全删除绑定机制；代理源来自代理池；不再需要 Webshare（直接删 100 条机房条目）。

## 1. 最终形态

注册任务从代理池取活跃代理（那条 1024proxy），对每任务 `rotate_proxy_sid` → 每窗口一个全新住宅出口 IP。无「每天/每 IP 一次」限制。代理池的增/删/测/导入管理保留；Webshare 条目删除；整个 ProxyBinding 层删除。

## 2. 删除的绑定基础设施

| 文件 | 处理 |
|---|---|
| `services/gateway/proxy_binding_service.py` | 整文件删除 |
| `services/gateway/models.py` | 删 `ProxyBinding` 模型 |
| `services/tests/gateway/test_proxy_binding_service.py` | 整文件删除 |
| `services/gateway/routers/registration.py` | 见 §3 |
| `services/gateway/routers/proxy.py` | 删 `/proxy/quota` 与 `/proxy/{proxy_id}/bindings` 两个端点及 `ProxyBindingService` 引用 |
| `services/worker/local_task_manager.py` | 删 `_persist_binding` / `_finalize_binding` / `_release_binding` 方法、`event_type == "binding"` 分支、以及所有 `_release_binding`/`_finalize_binding` 调用点 |
| `services/worker/flows/outlook.py` | 删 `_on_window` 回调与 `emit("binding", …)`；`_register_one_browser` 的 `on_window` 传参改回不传 |
| `services/worker/flows/gmail.py` | 删 `emit("binding", …)` |

## 3. 恢复 sid 轮换（registration.py）

`services/gateway/routers/registration.py` 改为：

- 恢复 `_proxy_url(proxy)`、`_pick_active_proxy(session)`（取 `status in ("active","available","slow")` 的池条目）、`_resolve_proxy(session, proxy_id, proxy)`（`proxy_id` 优先，其次显式 `proxy` 串，再次 `_pick_active_proxy`）。
- 循环 `count` 次派发：解析出 `base_proxy` 后，对每个窗口 `submit(..., proxy=rotate_proxy_sid(base_proxy), …)`。
- 删除 `ProxyBindingService`/`claim`/`claim_specific`/`ACTIVE_STATUSES` 相关分支与「不再支持直接传 proxy」的 422 拦截。
- `rotate_proxy_sid` 从 `common.proxy` 导入（已存在，非该格式原样返回）。

原始的每日「池空则部分派发/skipped」语义随绑定一并移除（1024proxy 单上游 + sid 轮换本就无「池见底」概念）。

## 4. 数据与迁移

- 新增 Alembic 迁移：`DROP TABLE proxy_bindings`（`downgrade` 重建表结构以可回滚）。
- **删除 Webshare 条目**：清掉代理池中 100 条机房 HTTP 条目（`host` 非 `us.1024proxy.io`），运行期用 `DELETE /api/proxy/{id}` 或一次性脚本。
- **重新启用 1024proxy 条目**：状态改 `active`。其失效 sid 无所谓——`rotate_proxy_sid` 每任务生成新 sid。跑真号需 1024proxy 账户有余额（用户负责充值）。
- 保留 `services/shared/database.py` 的事务控制改动（`isolation_level=None` + 显式 BEGIN，属通用正确性，非绑定专属）；仅清理带 `binding` 字样的注释。

## 5. 前端

- `frontend/src/pages/ProxyPage.tsx`：删除「已绑窗口 / 今日计数 / 展开明细 / 配额」相关列与请求，保留普通池管理（列表/新增/测试/状态/导入）。
- `frontend/src/pages/ProxyPage.test.tsx`：去掉绑定/配额相关断言与 mock。
- `frontend/src/pages/AccountsPage.tsx`：删除绑定相关展示。
- `frontend/src/pages/AccountsPage.test.tsx`：同步更新。

## 6. 测试

- 新增/恢复 `services/tests/gateway/test_registration_routes.py` 的「注册按窗口轮换 sid」用例（参照 `84dd280`：`count=2` 时两窗口 sid 不同、上游 host 不变）。
- `services/tests/gateway/test_proxy_routes.py`：删除 `quota`/`bindings` 端点断言。
- `services/tests/gateway/test_registration_routes.py`：删除 claim/绑定相关断言，改为 sid 轮换与 `_resolve_proxy` 断言。
- 保留 `services/tests/shared/test_database_transactions.py`（测通用事务语义，不依赖 ProxyBinding；若其 fixture 建 `proxy_bindings` 则改用其它表或普通事务）。
- `rotate_proxy_sid` 已有单测（`common` 侧）；确认覆盖 sid 段替换与非该格式原样返回。

## 7. 范围外 / 约束

- 不动 Ant/ixBrowser provider 相关代码（浏览器 provider 与本次代理选择逻辑正交）。
- 不改 `common.proxy.rotate_proxy_sid` 的实现。
- 工作区当前有未提交的 ixBrowser 代理注入改动（`common/ixbrowser_provider.py`、`common/browser.py`、`register_outlook_standalone.py`、`tests/test_ixbrowser_provider.py`）；实现本设计前应先提交或暂存，保持改动分离。
- 单活跃/并发：`max_concurrency` 语义不变；sid 轮换在派发时按窗口进行。

## 8. 验收

- `POST /register/outlook count=2`：两个子进程各拿到 sid 不同、上游同为 `us.1024proxy.io` 的代理串。
- 代理池不含任何 Webshare 条目；`proxy_bindings` 表不存在；`/api/proxy/quota`、`/api/proxy/{id}/bindings` 返回 404。
- 前端代理页无「已绑窗口/配额」，仅普通池管理。
- 后端全套单测通过；前端 ProxyPage/AccountsPage 测试通过。
