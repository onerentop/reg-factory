# 工具/运维页（ToolsPage）设计 —— 给无 UI 的后端功能补前端操作

- 日期：2026-06-13
- 缺口：5 个 gateway 后端功能有能力、无前端操作——`/tools/unlock-outlook`、`/tools/validate-keys`、`/tools/activate-plus`、`/orchestrate/all-platforms`、`/orchestrate/full-flow`。
- 决策：新增一个「工具/运维」页集中这 5 个操作。
- 关键：用 `apiClient`(axios+token 拦截器)包装，**自动带 auth**，避免 raw-fetch 无 auth 静默失败 bug（刚在 AlertsPage 修过同类）。

## 1. `src/api/tools.ts`（apiClient 包装，自动注入 token）

```ts
import apiClient from './client'
export const toolsApi = {
  unlockOutlook: (email, password) => apiClient.post('/tools/unlock-outlook', { email, password }),
  validateKey:   (key) => apiClient.post('/tools/validate-keys', { key }),
  activatePlus:  (access_token, email, card) => apiClient.post('/tools/activate-plus', { access_token, email, card }),
  orchestrateAllPlatforms: (email, password, platforms) =>
    apiClient.post('/orchestrate/all-platforms', { email, password, platforms }),
  orchestrateFullFlow: (count, platforms) =>
    apiClient.post('/orchestrate/full-flow', { count, platforms }),
}
```
（apiClient 响应拦截器返回 `response.data`，即 `{success,data,message}`。）

## 2. `src/pages/ToolsPage.tsx`（antd Card 分区，5 操作）

| 卡片 | 表单字段(antd Form) | 提交 | 反馈 |
|---|---|---|---|
| 解锁 Outlook | email, password | `unlockOutlook` | message + task_id |
| 校验 Session Key | key | `validateKey` | message + 结果 |
| 激活 ChatGPT Plus | access_token, email, card(选填) | `activatePlus` | message + task_id |
| 多平台批量注册 | email, password, platforms(多选,默认 claude/chatgpt/grok) | `orchestrateAllPlatforms` | message + task_id |
| 全流程注册 | count(数字,默认1), platforms(多选) | `orchestrateFullFlow` | message + task_id |

- 每卡：`Form` + "执行"`Button`(loading 态) → 调 toolsApi → 成功 `message.success('已触发: ' + data.task_id)`，失败 `message.error`。
- 用 `useState` 存各卡最近一次 task_id/结果，卡内展示。
- 布局：响应式 Row/Col 网格的 Card；页头 Title「工具 / 运维」。

## 3. 接线

- `src/App.tsx`：在 MainLayout 子路由加 `<Route path="/tools" element={<ToolsPage />} />`。
- `src/layouts/MainLayout.tsx`：菜单数组加 `{ key: '/tools', icon: <ToolOutlined />, label: '工具/运维' }`（从 @ant-design/icons 引 ToolOutlined）。

## 4. 测试

- **vitest 冒烟** `src/pages/ToolsPage.test.tsx`：mock `@/api/tools`，`renderWithProviders(<ToolsPage/>)` → 断言页头 + 5 个卡片标题/执行按钮在。
- **E2E walkthrough** `e2e/walkthrough/tools.spec.ts`：登录 → 进 `/tools` → 填一个工具表单(如校验 key) → 点执行 → 断言请求真发出(`waitForResponse /api/tools/...` 或 /orchestrate/) + UI 反馈。门槛操作(注册编排)真触发到入队即可、不等 worker。

## 5. 非目标

- 不改后端 tools/orchestrate（已有能力，只补前端）。
- 不做工具操作的历史/任务详情页（task_id 展示即可，详情查 worker/日志）。
- 不动其它页面。
