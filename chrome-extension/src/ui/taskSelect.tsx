import { ConfigProvider, Select } from 'antd'
import { StyleProvider } from '@ant-design/cssinjs'
import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'
import type { PageActionTaskChoice } from '../pageActions/types'

export type TaskSelectMount = {
  update: (choices: PageActionTaskChoice[]) => void
  setBusy: (busy: boolean) => void
  destroy: () => void
}

export function mountTaskSelect(container: HTMLElement, shadow: ShadowRoot, value: HTMLSelectElement, onEscape?: () => void): TaskSelectMount {
  const popup = document.createElement('div')
  popup.style.cssText = 'position:relative;z-index:2147483647'
  shadow.append(popup)
  const root = createRoot(container)
  let choices: PageActionTaskChoice[] = []
  let destroyed = false
  let loading = true
  let busy = false
  let open = false
  let selected: string | undefined
  const render = () => { if (destroyed) return; flushSync(() => root.render(
    <StyleProvider container={shadow}>
      <ConfigProvider getPopupContainer={() => popup} theme={{ token: {
        colorPrimary: '#2563eb', borderRadius: 10, controlHeight: 44,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      } }}>
        <div onKeyDownCapture={event => {
          if (event.key === 'Escape') {
            event.preventDefault(); event.stopPropagation()
            if (open) { open = false; render() } else { onEscape?.() }
          }
        }}>
        <Select id="mf-task-id" aria-label="选择任务" style={{ width: '100%' }}
          showSearch={{ optionFilterProp: 'label' }} allowClear virtual={false}
          loading={loading} disabled={loading || busy || !choices.length}
          placeholder={loading ? '正在加载任务…' : choices.length ? '输入任务名称筛选' : '暂无可用任务'}
          notFoundContent="没有匹配的任务" value={selected}
          options={choices.map(choice => ({ value: choice.id, label: choice.name, title: choice.name }))}
          onChange={(id) => { selected = id; value.value = id ?? ''; render() }}
          open={open} onOpenChange={next => { open = next; render() }}
          onInputKeyDown={event => {
            if (event.key === 'Enter') { event.preventDefault(); event.stopPropagation() }
          }}
        />
        </div>
      </ConfigProvider>
    </StyleProvider>
  )) }
  render()
  return {
    update: next => { choices = next; loading = false; selected = undefined; render() },
    setBusy: next => { busy = next; render() },
    destroy: () => { if (destroyed) return; destroyed = true; root.unmount(); popup.remove() },
  }
}
