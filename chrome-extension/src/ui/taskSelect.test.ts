// @vitest-environment happy-dom
import { expect, it } from 'vitest'
import { mountTaskSelect } from './taskSelect'

it('ignores pending updates after dialog destruction and removes its popup', () => {
  const host = document.createElement('div')
  document.body.append(host)
  const shadow = host.attachShadow({ mode: 'open' })
  const container = document.createElement('div')
  shadow.append(container)
  const value = document.createElement('select')
  const selector = mountTaskSelect(container, shadow, value)
  selector.destroy()
  expect(() => {
    selector.setBusy(false)
    selector.update([{ id: 'one', name: 'late result' }])
    selector.destroy()
  }).not.toThrow()
  expect(container.childElementCount).toBe(0)
  expect(shadow.querySelector('[style*="2147483647"]')).toBeNull()
  host.remove()
})
