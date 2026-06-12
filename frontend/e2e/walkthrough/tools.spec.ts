import { test, expect } from '@playwright/test'
import { login } from '../_helpers'

/**
 * Tools/运维 Walkthrough: 真实 UI 走查
 *
 * 这 5 个工具原先无前端操作（unlock-outlook / validate-keys / activate-plus /
 * orchestrate all-platforms / full-flow），现补了 ToolsPage。
 *
 * 走查触发副作用最低的「校验 Session Key」：后端 .delay() 入队即返回 task_id，
 * 不创建真实账号、不等 worker。断言：请求真发出 + 后端 200 + UI 回显 task_id。
 * 其余 4 卡只断言渲染存在（真触发批量/全流程注册代价大，留人工/专项跑）。
 */
test.describe('工具/运维页面 walkthrough', () => {
  test('页面加载 + 5 个工具卡片渲染', async ({ page }) => {
    test.setTimeout(60000)

    await login(page)
    await page.goto('/tools', { waitUntil: 'domcontentloaded' })

    await expect(page.getByText('工具 / 运维')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('解锁 Outlook 账号')).toBeVisible()
    await expect(page.getByText('校验 Session Key')).toBeVisible()
    await expect(page.getByText('激活 ChatGPT Plus')).toBeVisible()
    await expect(page.getByText('多平台批量注册')).toBeVisible()
    await expect(page.getByText('全流程注册')).toBeVisible()
  })

  test('校验 Session Key: 真实触发 → 入队 → 回显 task_id', async ({ page }) => {
    test.setTimeout(60000)

    await login(page)
    await page.goto('/tools', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('校验 Session Key')).toBeVisible({ timeout: 10000 })

    // 在「校验 Session Key」卡片内填 key
    const card = page.locator('.ant-card').filter({ hasText: '校验 Session Key' })
    await card.getByPlaceholder('refresh_token / session key').fill('e2e-test-key-123')

    // 点该卡「执 行」前挂监听，捕获真实请求 + 响应
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/tools/validate-keys') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await card.getByRole('button', { name: /执\s*行/ }).click()

    const resp = await respPromise
    expect(resp.status()).toBe(200) // 后端真入队成功
    const json = await resp.json()
    expect(json.success).toBe(true)
    expect(json.data?.task_id).toBeTruthy()

    // UI 回显：成功 Tag 含 task 字样
    await expect(card.getByText(/已触发，task:/)).toBeVisible({ timeout: 10000 })
  })
})
