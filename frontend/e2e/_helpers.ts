import { Page, expect } from '@playwright/test'

/** 用种子 admin 登录，跳到 dashboard。所有 walkthrough 复用。 */
export async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
}
