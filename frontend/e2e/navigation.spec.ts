import { test, expect, Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
}

// 登录后导航各页面，验证前端路由 + 各页从后端加载数据(真链路)不崩。
test('登录后各页面均加载(前端↔后端真链路)', async ({ page }) => {
  test.setTimeout(90000)  // 导航 8 页 + 登录，给足时间
  await login(page)
  const pages: [string, string][] = [
    ['/accounts/outlook', '账户管理'],
    ['/proxy', '代理配置'],
    ['/sms', '接码平台配置'],
    ['/logs', '日志查询'],
    ['/audit', '操作审计'],
    ['/alerts', '告警通知'],
    ['/schedules', '定时任务'],
    ['/settings', '设置'],
  ]
  for (const [path, title] of pages) {
    await page.goto(path, { waitUntil: 'domcontentloaded' })
    await expect(page.getByText(title).first()).toBeVisible({ timeout: 10000 })
  }
})
