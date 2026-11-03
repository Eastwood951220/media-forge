import { Button, ConfigProvider, Input, theme } from 'antd'
import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'

// Mount before existing controllers bind their DOM handlers.
export function enhanceControls() {
  const dark = matchMedia('(prefers-color-scheme: dark)')
  const mounts: (() => void)[] = []
  document.querySelectorAll<HTMLButtonElement | HTMLInputElement>('button, input').forEach(element => {
    const container = document.createElement('span')
    container.style.display = 'contents'
    const root = createRoot(container)
    element.replaceWith(container)
    const render = () => flushSync(() => root.render(
      <ConfigProvider theme={{ algorithm: dark.matches ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: { colorPrimary: '#2563eb', borderRadius: 10, controlHeight: 42 } }}>
        {element.tagName === 'BUTTON' ? <Button id={element.id} className={element.className} type={element.classList.contains('primary') ? 'primary' : 'default'}>{element.textContent}</Button>
          : <Input id={element.id} type={element.getAttribute('type') ?? 'text'} placeholder={element.getAttribute('placeholder') ?? undefined} autoComplete="off" />}
      </ConfigProvider>
    ))
    mounts.push(render)
    render()
  })
  dark.addEventListener('change', () => mounts.forEach(render => render()))
}
