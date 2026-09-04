import { expect, Page, test } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/accounts\/outlook/, { timeout: 15000 })
}

test('登录后仅可导航 Outlook、Google、接码和代理页面', async ({ page }) => {
  await login(page)
  const pages: [string, string][] = [
    ['/accounts/outlook', 'Outlook 账户管理'],
    ['/accounts/google', 'Google 账户管理'],
    ['/proxy', '代理配置'],
    ['/sms', '接码平台配置'],
  ]
  for (const [path, title] of pages) {
    await page.goto(path, { waitUntil: 'domcontentloaded' })
    await expect(page.getByText(title).first()).toBeVisible({ timeout: 10000 })
  }
})
