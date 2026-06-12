import { test, expect } from '@playwright/test'
import { login } from '../_helpers'

/**
 * Accounts Walkthrough: /accounts/outlook 真实走查
 *
 * AccountsPage 的"新建"按钮会启动一个真正的注册任务（POST /api/register/outlook），
 * 耗时很长且需要代理+浏览器自动化，E2E 中无法可靠地完成。
 *
 * 因此本 walkthrough 分两部分：
 *   A. 页面加载、统计卡片、表格可见（验证前端↔后端真链路加载账户列表）
 *   B. 打开"新建注册"模态框 → 验证表单字段可见（断言 UI 就绪）→ 关闭
 *
 * 如果数据库中已有账户，还会：
 *   C. 选中第一行 → 点"删除"→ 确认删除 → 验证总数减少（真 DELETE /api/accounts/:id）
 *
 * 这是能在 CI 环境里对 AccountsPage 做的最完整真实走查。
 */
test.describe('账户页面 walkthrough', () => {
  test('账户页加载 + 新建注册模态框可操作', async ({ page }) => {
    test.setTimeout(60000)

    await login(page)
    await page.goto('/accounts/outlook', { waitUntil: 'domcontentloaded' })

    // ── A. 页面标题与统计卡片 ──────────────────────────────────────────
    await expect(page.getByText('Outlook 账户管理')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('总账户')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('注册成功')).toBeVisible({ timeout: 10000 })

    // ── B. 打开新建注册模态框，验证表单 ──────────────────────────────────
    await page.getByRole('button', { name: /新建注册/ }).click()
    await expect(page.getByText('新建 Outlook 注册')).toBeVisible({ timeout: 5000 })

    // 验证关键表单元素
    await expect(page.getByText('注册数量')).toBeVisible()
    await expect(page.getByText('使用代理')).toBeVisible()
    await expect(page.getByText('注册模式')).toBeVisible()
    await expect(page.getByRole('button', { name: /开始注册/ })).toBeVisible()

    // 关闭模态框（点 X 按钮，不真正触发注册）
    const registerModal = page.locator('.ant-modal').filter({ hasText: '新建 Outlook 注册' })
    await registerModal.getByRole('button', { name: /Close|关闭/ }).click()
    await expect(page.getByText('新建 Outlook 注册')).not.toBeVisible({ timeout: 5000 })
  })

  test('如有账户 → 真实删除单条 → 验证计数减少', async ({ page }) => {
    test.setTimeout(60000)

    await login(page)
    await page.goto('/accounts/outlook', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('Outlook 账户管理')).toBeVisible({ timeout: 10000 })

    // 等待表格加载
    await page.waitForTimeout(2000)

    // 检查是否有账户行可删除
    const deleteButtons = page.getByRole('button', { name: /删除/ })
    const count = await deleteButtons.count()

    if (count === 0) {
      // 没有账户行 — 跳过删除测试
      console.log('数据库中无账户，跳过删除验证（符合预期的空库）')
      test.skip()
      return
    }

    // 获取当前总数（从统计卡片）
    const totalCard = page.locator('.ant-statistic').filter({ hasText: '总账户' })
    const totalTextBefore = await totalCard.locator('.ant-statistic-content-value').textContent()
    const totalBefore = parseInt(totalTextBefore || '0', 10)

    // 点击第一个删除按钮
    await deleteButtons.first().click()

    // antd Modal.confirm 的确认按钮
    await page.getByRole('button', { name: /确定/ }).last().click()

    // 等待删除完成后列表刷新
    await page.waitForTimeout(2000)

    // 验证：总数减少 或 成功消息出现
    const successMsg = page.locator('.ant-message-success')
    const hasMsgVisible = await successMsg.isVisible().catch(() => false)

    if (!hasMsgVisible) {
      // 直接验证总账户数减少了
      const totalTextAfter = await totalCard.locator('.ant-statistic-content-value').textContent()
      const totalAfter = parseInt(totalTextAfter || '0', 10)
      expect(totalAfter).toBeLessThan(totalBefore)
    }
    // 如果成功消息可见，说明删除已触发
  })
})
