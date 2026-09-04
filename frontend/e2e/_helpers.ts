import { expect, Page } from '@playwright/test'

/** 用种子 admin 登录并进入 Outlook 注册结果页。 */
export async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/accounts\/outlook/, { timeout: 15000 })
}
