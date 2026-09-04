import { expect, test } from '@playwright/test'

test('登录成功后进入 Outlook 注册结果页', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.locator('button[type="submit"]').click()

  await expect(page).toHaveURL(/\/accounts\/outlook/, { timeout: 15000 })
  await expect(page.getByText('Outlook 账户管理')).toBeVisible({ timeout: 10000 })
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeTruthy()
})

test('登录失败时留在登录页', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('wrong-password')
  await page.locator('button[type="submit"]').click()

  await page.waitForTimeout(2500)
  await expect(page).not.toHaveURL(/\/accounts\/outlook/)
})
