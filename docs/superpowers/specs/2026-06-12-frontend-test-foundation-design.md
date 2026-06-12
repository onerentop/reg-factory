# 前端测试基础 + 单测覆盖 设计

- 日期：2026-06-12
- 范围：前端优先（前端 0 测试、最大缺口）。后端 168 测试已有，本次不动。
- 深度：逻辑层彻底单测 + 11 页面渲染冒烟。
- 可行性已确认：frontend/node_modules 已装(144包)、node22/npm10、npm 可联网、vitest 待装。

## 1. 框架（vitest）

Vite 原生测试栈。新增 devDeps：
`vitest`、`@testing-library/react`、`@testing-library/jest-dom`、`@testing-library/user-event`、`jsdom`。

- `frontend/vitest.config.ts`：`test.environment='jsdom'`、`test.globals=true`、`test.setupFiles=['./src/test/setup.ts']`、复用 vite 的 react 插件 + `@` 别名（若有）。
- `frontend/src/test/setup.ts`：`import '@testing-library/jest-dom'`；全局 stub（`window.matchMedia`(antd 需)、`localStorage` 在 jsdom 已有）。
- `frontend/src/test/utils.tsx`：`renderWithProviders(ui)` = 包 `ThemeProvider` + `MemoryRouter`（+ 按需 mock store）。
- `package.json` scripts：`test: vitest run`、`test:watch: vitest`、`test:cov: vitest run --coverage`。

## 2. 逻辑层彻底单测（一文件一 test，mock 外部依赖）

| 测试文件 | 被测 | 要点 |
|---|---|---|
| `src/utils/format.test.ts` | `utils/format` 各函数 | 正常+边界(空/0/大数/无效)输入 |
| `src/api/client.test.ts` | axios 拦截器 | ① 请求注入 `Authorization: Bearer <token>`(localStorage 有token时)；② 响应解包 `response.data`；③ 401→清 token + 跳 `/login`；④ 其它错误 reject。mock axios 实例 + localStorage + `window.location`。 |
| `src/api/accounts.test.ts` 等(auth/sms/dashboard) | 各 API 包装函数 | mock `apiClient`，断言调对 method+path+params |
| `src/stores/authStore.test.ts` | zustand authStore | login 存 token+用户态、logout 清、isAuthenticated 派生 |
| `src/stores/accountStore.test.ts` | accountStore | fetch/set/CRUD action 改 state 正确 |
| `src/hooks/usePagination.test.ts` | usePagination | renderHook：page/pageSize 改变、total 计算、翻页 |
| `src/hooks/useWebSocket.test.ts` | useWebSocket | mock WS：连接、onmessage 更新、卸载断开 |
| `src/websocket/WebSocketClient.test.ts` | WebSocketClient | mock 全局 WebSocket：connect/send/重连/close |

## 3. 11 页面渲染冒烟（`renderWithProviders` + mock store/API）

每页一个 `src/pages/<Page>.test.tsx`：渲染该页 → ① 不抛错；② 关键元素在（页面标题/主表格/主按钮，用 `getByText`/`getByRole`）；③ 若页面 mount 即调 API，断言被 mock 调用。
页面：Login / Dashboard / Accounts / Import / Proxy / Sms­Config / Alerts / Audit / Logs / Schedules / Settings。

mock 策略：`vi.mock('@/api/...')` 返回假数据；`vi.mock('@/stores/...')` 或注入初始 state；antd 组件真渲染（jsdom）；路由用 MemoryRouter；图表(recharts)在 jsdom 下渲染容器即可。

## 4. 验证 / 容错

- `cd frontend && npm test` 全绿；`npm run test:cov` 出覆盖率（逻辑层目标高，页面冒烟保证 render 通过）。
- 每个 test 独立、mock 隔离（`beforeEach` 清 mock/localStorage）。
- 页面冒烟若因缺 mock 抛错 → 补该页所需 mock（store 初始态/API stub），不放宽到忽略错误。

## 5. 非目标（YAGNI）

- 不做页面全交互测（填表/点击全流程）——本次冒烟即可（深交互留后续）。
- 不动后端 168 测试。
- 不测纯样式/主题 token 值（低价值）。
- 不引入 E2E(Playwright)——单测+冒烟范围内。

## 6. 文件结构

```
frontend/
  vitest.config.ts            (新)
  src/test/setup.ts           (新)
  src/test/utils.tsx          (新, renderWithProviders)
  src/**/<unit>.test.ts(x)    (新, 与被测同目录)
  package.json                (改, 加 devDeps + scripts)
```
