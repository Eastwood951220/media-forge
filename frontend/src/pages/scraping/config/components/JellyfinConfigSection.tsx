import { useCallback, useEffect, useState } from 'react'
import { Alert, App, Button, Card, Checkbox, Form, Input, Segmented, Space, Switch, Tag, Typography } from 'antd'
import {
  getJellyfinWatchStatus,
  listJellyfinLibraries,
  refreshJellyfinLibraries,
  syncJellyfinWatch,
  testJellyfinConnection,
  type JellyfinLibrary,
  type JellyfinWatchStatus,
} from '@/api/jellyfin'
import { getErrorMessage } from '../utils/error'

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'].map((label, value) => ({ label, value }))

interface Props {
  configured: boolean
  maskedKey: string
  save: () => Promise<boolean>
}

export default function JellyfinConfigSection({ configured, maskedKey, save }: Props) {
  const { message } = App.useApp()
  const form = Form.useFormInstance()
  const scheduleType = Form.useWatch('jellyfin_watch_sync_schedule_type', form)
  const [libraries, setLibraries] = useState<JellyfinLibrary[]>([])
  const [status, setStatus] = useState<JellyfinWatchStatus | null>(null)
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    try {
      const [items, state] = await Promise.all([listJellyfinLibraries(), getJellyfinWatchStatus()])
      setLibraries(items)
      setStatus(state)
    } catch {
      setLibraries([])
    }
  }, [])

  useEffect(() => {
    if (configured) void load()
  }, [configured, load])

  const action = async (kind: string) => {
    setBusy(kind)
    try {
      if (!(await save())) return
      if (kind === 'test') {
        const result = await testJellyfinConnection()
        message.success(`连接成功，发现 ${result.library_count} 个影视库`)
      } else if (kind === 'refresh') {
        const result = await refreshJellyfinLibraries()
        const failed = result.libraries.filter((item) => !item.accepted)
        if (failed.length) message.error(`${failed.length} 个影视库刷新失败`)
        else message.success(`已触发 ${result.libraries.length} 个影视库刷新`)
      } else {
        const result = await syncJellyfinWatch()
        message.success(`已同步 ${result.matched_count} 部电影的观看状态`)
      }
      await load()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setBusy('')
    }
  }

  return (
    <Card title="Jellyfin" >
      <Form.Item name="jellyfin_base_url" label="Jellyfin 服务地址" rules={[{ pattern: /^https?:\/\/\S+$/, message: '请输入有效的 Jellyfin 地址' }]}>
        <Input placeholder="http://jellyfin:8096" />
      </Form.Item>
      <Form.Item label="Jellyfin API Key">
        {configured && <Typography.Text>Jellyfin API Key 已配置: {maskedKey}</Typography.Text>}
        <Form.Item name="jellyfin_api_key" noStyle><Input.Password placeholder="留空保持不变" /></Form.Item>
      </Form.Item>
      <Form.Item name="jellyfin_auto_refresh_enabled" label="生成或删除 STRM 后自动刷新影视库" valuePropName="checked"><Switch /></Form.Item>
      <Form.Item name="jellyfin_watch_sync_enabled" label="定时同步观看状态" valuePropName="checked"><Switch /></Form.Item>
      <Form.Item name="jellyfin_watch_sync_schedule_type" label="同步周期"><Segmented options={[{ label: '每天', value: 'daily' }, { label: '每周', value: 'weekly' }]} /></Form.Item>
      {scheduleType === 'weekly' && <Form.Item name="jellyfin_watch_sync_weekdays" label="星期" rules={[{ validator: (_, value: number[]) => value?.length ? Promise.resolve() : Promise.reject(new Error('请选择星期')) }]}><Checkbox.Group options={weekdays} /></Form.Item>}
      <Form.Item name="jellyfin_watch_sync_time_of_day" label="同步时间" rules={[{ required: true, message: '请选择同步时间' }]}><Input type="time" /></Form.Item>
      <Space wrap>
        <Button loading={busy === 'test'} disabled={!!busy} onClick={() => void action('test')}>测试连接</Button>
        <Button loading={busy === 'refresh'} disabled={!!busy} onClick={() => void action('refresh')}>手动刷新影视库</Button>
        <Button loading={busy === 'sync'} disabled={!!busy} onClick={() => void action('sync')}>立即同步观看状态</Button>
      </Space>
      {status && <Alert style={{ marginTop: 16 }} type="info" title={status.last_success_at ? `上次同步：${status.last_success_at}` : '观看状态尚未同步'} description={status.last_error ?? undefined} />}
      {libraries.length > 0 && <div style={{ marginTop: 16 }}><Typography.Text strong>影视库目录</Typography.Text>{libraries.map((library) => <div key={library.ItemId}><Tag>{library.Name}</Tag>{library.Locations.map((path) => <Typography.Text key={path} code>{path}</Typography.Text>)}</div>)}</div>}
    </Card>
  )
}
