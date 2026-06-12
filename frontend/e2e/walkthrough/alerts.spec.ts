import { test, expect } from '@playwright/test'
import { login } from '../_helpers'

/**
 * Alerts Walkthrough: 真实 UI 走查
 *
 * 说明：addRule 的"无 Auth 头 → 静默不持久化"bug 已修复(带 Auth 头 + 检查响应)。
 * Test 1: 经 UI 真创建规则 → 模态框关闭 → 规则真出现在列表(真链路持久化)。
 * Test 2: 用 page.evaluate 直调真实 API 复核持久化。
 * (后端无 DELETE /alerts/rules/:id，留测试数据 e2e-*rule-* 命名,易手动清理)
 */
test.describe('告警页面 walkthrough', () => {
  test('告警规则: 页面加载 + 模态框 UI 交互', async ({ page }) => {
    test.setTimeout(60000)

    await login(page)
    await page.goto('/alerts', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('告警通知')).toBeVisible({ timeout: 10000 })

    // 确保在"告警规则"标签页
    const rulesTab = page.getByRole('tab', { name: /告警规则/ })
    if (await rulesTab.isVisible()) {
      await rulesTab.click()
    }

    // 按钮可见
    await expect(page.getByRole('button', { name: /添加规则/ })).toBeVisible()

    // 打开添加模态框
    await page.getByRole('button', { name: /添加规则/ }).click()
    const modal = page.locator('.ant-modal').filter({ hasText: '添加告警规则' })
    await expect(modal).toBeVisible({ timeout: 5000 })

    // 填写规则名称
    const ts = Date.now()
    const ruleName = `e2e-rule-${ts}`
    await modal.locator('input#name').fill(ruleName)

    // 选择规则类型
    const typeSelectTrigger = modal.locator('.ant-select').filter({ has: page.locator('[id="rule_type"]') })
    await typeSelectTrigger.click()
    await page.locator('.ant-select-item-option').filter({ hasText: '接码余额不足' }).click()

    // 填写阈值
    await page.getByPlaceholder('例: 10 ($)').fill('10')

    // 提交（antd 2-char 按钮 "确 定"）
    await modal.getByRole('button', { name: /确\s*定/ }).click()

    // 模态框关闭 + 规则真实持久化（addRule 已修复：带 Auth 头 + 检查响应，失败不再假成功）
    await expect(modal).not.toBeVisible({ timeout: 10000 })
    // 真链路持久化验证：经 UI 创建的规则真出现在列表
    await expect(page.getByText(ruleName)).toBeVisible({ timeout: 10000 })
  })

  test('告警规则: 真实 API 创建 → 刷新页面验证持久化', async ({ page }) => {
    test.setTimeout(60000)

    const ts = Date.now()
    const ruleName = `e2e-api-rule-${ts}`

    await login(page)

    // 用 page.evaluate 借 localStorage 里的 token 调用真实 API
    const created = await page.evaluate(async (name) => {
      const token = localStorage.getItem('token')
      const resp = await fetch('/api/alerts/rules', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          name,
          rule_type: 'sms_balance',
          threshold: '5',
          enabled: true,
          notify_channels: ['web'],
        }),
      })
      return resp.json()
    }, ruleName)

    // 真实写入成功（success=true, data.id 非空）
    expect(created.success).toBe(true)
    expect(created.data?.id).toBeTruthy()

    // 导航到告警页 → 刷新后能看到新规则（真实 DB 持久化验证）
    await page.goto('/alerts', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('告警通知')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(ruleName)).toBeVisible({ timeout: 10000 })

    // 注：后端无 DELETE /alerts/rules/:id 端点，UI 也无删除按钮，无法清理
    // 测试数据会留在 DB（e2e-api-rule-* 命名模式，易于手动识别清理）
  })
})
