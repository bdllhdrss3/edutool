import { expect, type Locator, type Page, type TestInfo } from '@playwright/test'
import { documentTitle } from './fixtures'

export const isPhone = (page: Page) => page.viewportSize()!.width <= 676

export async function loadLibrary(page: Page) {
  await page.goto('/')
  await expect(page.locator('.library-item')).toHaveCount(2)
  await expect(page.locator('.chat-history-row')).toHaveCount(3)
  await page.evaluate(() => document.fonts.ready)
}

export async function showNavigation(page: Page) {
  if (page.viewportSize()!.width <= 900) await page.getByRole('button', { name: 'Open navigation', exact: true }).click()
}

export async function hideNavigation(page: Page) {
  if (page.viewportSize()!.width <= 900) await page.locator('.sidebar').getByRole('button', { name: 'Close navigation', exact: true }).click()
}

export async function openDocument(page: Page) {
  await page.locator('.library-row').filter({ hasText: documentTitle }).click()
  await expect(page.locator('.pdf h2')).toHaveText('Page 1')
}

export async function openQuiz(page: Page) {
  if (isPhone(page)) await page.getByRole('button', { name: 'Open study tools', exact: true }).click()
  else if (!await page.locator('.tools').isVisible()) await page.getByRole('button', { name: 'Show tools', exact: true }).click()
  await page.locator('.tabs').getByRole('button', { name: 'Check Me', exact: true }).click()
  await expect(page.locator('.quiz-panel')).toBeVisible()
}

export async function moveReader(page: Page) {
  // Up to 900px the tools are intentionally an overlay, not a second column.
  // Close via the overlay's own visible button before using reader controls.
  if (page.viewportSize()!.width <= 900 && await page.locator('.tools').isVisible()) {
    await page.getByRole('button', { name: 'Close study tools', exact: true }).click()
  }
  if (isPhone(page)) {
    await page.getByRole('button', { name: 'Next page', exact: true }).click()
  } else await page.locator('.paginate').getByRole('button', { name: 'Next', exact: true }).click()
}

export async function reopenQuiz(page: Page) {
  if (isPhone(page)) await page.getByRole('button', { name: 'Open study tools', exact: true }).click()
  else await page.getByRole('button', { name: 'Show tools', exact: true }).click()
  await expect(page.locator('.quiz-panel')).toBeVisible()
}

export async function box(locator: Locator) {
  await expect(locator).toBeVisible()
  const bounds = await locator.boundingBox()
  expect(bounds).not.toBeNull()
  return bounds!
}

export async function inViewport(locator: Locator, page: Page) {
  const bounds = await box(locator)
  const viewport = page.viewportSize()!
  expect(bounds.x).toBeGreaterThanOrEqual(-1)
  expect(bounds.y).toBeGreaterThanOrEqual(-1)
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width + 1)
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height + 1)
}

export async function noBodyOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    width: innerWidth, height: innerHeight,
    htmlWidth: document.documentElement.scrollWidth, htmlHeight: document.documentElement.scrollHeight,
    bodyWidth: document.body.scrollWidth, bodyHeight: document.body.scrollHeight,
    x: scrollX, y: scrollY,
  }))
  expect(metrics.htmlWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.width + 1)
  expect(metrics.bodyWidth, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.width + 1)
  expect(metrics.htmlHeight, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.height + 1)
  expect(metrics.bodyHeight, JSON.stringify(metrics)).toBeLessThanOrEqual(metrics.height + 1)
  expect(metrics.x).toBe(0)
  expect(metrics.y).toBe(0)
}

export async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  const path = testInfo.outputPath(`${name}.png`)
  await page.screenshot({ path, fullPage: true, animations: 'disabled' })
  await testInfo.attach(name, { path, contentType: 'image/png' })
}

// Prove that the intended inner viewport actually scrolls, without prohibiting
// legitimate overflow in the PDF, quiz, navigation or chat message containers.
export async function scrollInnerKeepingChrome(page: Page, scroller: Locator, chrome: Locator[]) {
  const before = await Promise.all(chrome.map(item => box(item)))
  const dimensions = await scroller.evaluate(element => ({ client: element.clientHeight, scroll: element.scrollHeight }))
  expect(dimensions.client).toBeGreaterThan(40)
  expect(dimensions.scroll).toBeGreaterThan(dimensions.client)
  await scroller.evaluate(element => element.scrollTo({ top: element.scrollHeight, behavior: 'instant' }))
  await expect.poll(() => scroller.evaluate(element => element.scrollTop)).toBeGreaterThan(0)
  const after = await Promise.all(chrome.map(item => box(item)))
  after.forEach((bounds, index) => {
    expect(Math.abs(bounds.y - before[index]!.y)).toBeLessThanOrEqual(1)
    expect(Math.abs(bounds.height - before[index]!.height)).toBeLessThanOrEqual(1)
  })
  for (const item of chrome) await inViewport(item, page)
  await noBodyOverflow(page)
}