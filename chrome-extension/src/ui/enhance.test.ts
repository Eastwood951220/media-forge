// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from 'vitest'
import { enhanceControls } from './enhance'

afterEach(() => vi.unstubAllGlobals())

it('reveals and copies a loaded token without changing its value', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: vi.fn() }))
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  document.body.innerHTML = '<label>Token<input id="token" type="password"></label>'
  const controls = enhanceControls()
  controls.setValue('token', 'test-generated-token')
  const input = document.querySelector<HTMLInputElement>('#token')!
  expect(input.type).toBe('password')
  document.querySelector<HTMLElement>('.ant-input-password-icon')!.click()
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(input.type).toBe('text')
  expect(input.value).toBe('test-generated-token')
  document.querySelector<HTMLButtonElement>('[aria-label="复制密码或 Token"]')!.click()
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(writeText).toHaveBeenCalledWith('test-generated-token')
  document.querySelector<HTMLElement>('.ant-input-password-icon')!.click()
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(input.type).toBe('password')
  expect(input.value).toBe('test-generated-token')
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  setter.call(input, 'edited-token')
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await new Promise(resolve => setTimeout(resolve, 0))
  document.querySelector<HTMLButtonElement>('[aria-label="复制密码或 Token"]')!.click()
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(writeText).toHaveBeenLastCalledWith('edited-token')
})
