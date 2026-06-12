import { test, expect } from '@playwright/test'
import { login } from '../_helpers'

/**
 * Proxy Walkthrough: 真实 CRUD
 * 1. 登录 → 导航到 /proxy
 * 2. 添加一条代理（socks5, host=test-{ts}.example.com）
 * 3. 验证新行出现在表格
 * 4. 点"测试"按钮 → 断言 UI 出现某状态（不要求可用）
 * 5. 删除 → 断言行消失
 */
test.describe('代理页面 CRUD walkthrough', () => {
  test('创建 → 验证 → 测试 → 删除 代理', async ({ page }) => {
    test.setTimeout(60000)

    const ts = Date.now()
    const testHost = `test-${ts}.example.com`
    const testPort = '19999'

    await login(page)
    await page.goto('/proxy', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('代理配置')).toBeVisible({ timeout: 10000 })

    // ── 打开添加模态框 ──────────────────────────────────────────────────
    await page.getByRole('button', { name: /添加代理/ }).click()
    await expect(page.getByText('添加代理').first()).toBeVisible({ timeout: 5000 })

    // 模态框内的表单：类型 select 已默认 socks5
    // 填写地址
    const hostInput = page.locator('input#host').or(page.getByPlaceholder('hk.1024proxy.io'))
    await hostInput.fill(testHost)

    // 填写端口
    const portInput = page.locator('input#port').or(page.getByPlaceholder('3000'))
    await portInput.fill(testPort)

    // 填写用户名（可选但有助于识别）
    const usernameInput = page.locator('input#username').or(page.getByPlaceholder('sb7f3017-region-JP-sid-xxx'))
    await usernameInput.fill(`e2e-user-${ts}`)

    // 点确定 (antd 2-char 按钮渲染为 "确 定"，用宽松正则)
    await page.getByRole('button', { name: /确\s*定/ }).click()

    // ── 验证新行出现 ────────────────────────────────────────────────────
    await expect(page.getByText(testHost)).toBeVisible({ timeout: 10000 })

    // ── 点"测试"按钮（与新行同行） ──────────────────────────────────────
    // 找到含 testHost 的行，点击该行中的"测试"按钮
    const row = page.locator('tr').filter({ hasText: testHost })
    await row.getByRole('button', { name: /测试/ }).click()

    // 等待状态 tag 变化（任意：检测中/可用/不可用/慢）
    await page.waitForTimeout(3000)
    // 断言该行出现某状态标签（4 种可能结果，只要有其中一种即为真结果已回填）
    const hasStatusTag = await row.locator('.ant-tag').count()
    expect(hasStatusTag).toBeGreaterThan(0)

    // ── 删除这一行 ──────────────────────────────────────────────────────
    await row.getByRole('button', { name: /删除/ }).click()
    // antd Popconfirm 的确认按钮（"确 定"）
    await page.getByRole('button', { name: /确\s*定/ }).last().click()

    // 断言行已消失
    await expect(page.getByText(testHost)).not.toBeVisible({ timeout: 10000 })
  })
})
