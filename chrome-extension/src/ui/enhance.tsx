import { Button, ConfigProvider, Input, theme } from 'antd'
import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'

// Mount before existing controllers bind their DOM handlers.
export function enhanceControls() {
  const dark = matchMedia('(prefers-color-scheme: dark)')
  const mounts: (() => void)[] = []
  const setters = new Map<string, (value: string) => void>()
  document.querySelectorAll<HTMLButtonElement | HTMLInputElement>('button, input').forEach(element => {
    const container = document.createElement('span')
    container.style.display = 'contents'
    const root = createRoot(container)
    const password = element.getAttribute('type') === 'password'
    let passwordValue = (element as HTMLInputElement).value ?? ''
    element.replaceWith(container)
    const render = () => flushSync(() => root.render(
      <ConfigProvider theme={{ algorithm: dark.matches ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: { colorPrimary: '#2563eb', borderRadius: 10, controlHeight: 42 } }}>
        {element.tagName === 'BUTTON' ? <Button id={element.id} className={element.className} type={element.classList.contains('primary') ? 'primary' : 'default'}>{element.textContent}</Button>
          : password ? <Input.Password id={element.id} value={passwordValue} autoComplete="off"
              placeholder={element.getAttribute('placeholder') ?? undefined}
              style={{ minWidth: 0 }}
              onChange={event => { passwordValue = event.target.value; render() }} />
          : <Input id={element.id} type={element.getAttribute('type') ?? 'text'} placeholder={element.getAttribute('placeholder') ?? undefined} autoComplete="off" />}
      </ConfigProvider>
    ))
    if (password) setters.set(element.id, value => { passwordValue = value; render() })
    mounts.push(render)
    render()
  })
  dark.addEventListener('change', () => mounts.forEach(render => render()))
  return {
    setValue(id: string, value: string) {
      const setter = setters.get(id)
      if (setter) setter(value)
      else {
        const input = document.getElementById(id) as HTMLInputElement | null
        if (input) input.value = value
      }
    },
  }
}
