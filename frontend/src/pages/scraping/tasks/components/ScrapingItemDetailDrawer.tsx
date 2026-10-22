import { useEffect, useMemo } from 'react'
import { Alert, Button, Card, Descriptions, Drawer, Empty, Skeleton, Tag, Timeline, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getScrapingItem, getScrapingItemLogs } from '@/api/scraping/scrapingTasks'
import type { ScrapingTaskItem, ScrapingTaskLog } from '@/api/scraping/scrapingTasks'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent } from '@/realtime/types'
import { ITEM_STATUS_COLOR, ITEM_STATUS_TEXT } from '../utils/status'
import { formatTime, levelColors, stepColor, stepLabels, stepOrder } from '../utils/itemSteps'
import styles from './ScrapingItemDetailDrawer.module.less'

interface Props {
  itemId: string
  onClose: () => void
}

export function ScrapingItemDetailDrawer({ itemId, onClose }: Props) {
  const queryClient = useQueryClient()
  const itemKey = useMemo(() => ['scrapingTasks', 'item', itemId] as const, [itemId])
  const logsKey = useMemo(() => ['scrapingTasks', 'item', itemId, 'logs'] as const, [itemId])
  const itemQuery = useQuery({ queryKey: itemKey, queryFn: () => getScrapingItem(itemId) })
  const logsQuery = useQuery({ queryKey: logsKey, queryFn: () => getScrapingItemLogs(itemId) })

  useEffect(() => {
    const updateItem = (event: RealtimeEvent<Partial<ScrapingTaskItem>>) => {
      if (event.resource_id === itemId) void queryClient.invalidateQueries({ queryKey: itemKey })
    }
    const updateLogs = (event: RealtimeEvent<ScrapingTaskLog>) => {
      if (event.resource_id === itemId) void queryClient.invalidateQueries({ queryKey: logsKey })
    }
    const resync = () => {
      void queryClient.invalidateQueries({ queryKey: itemKey })
      void queryClient.invalidateQueries({ queryKey: logsKey })
    }
    const unsubscribeItem = subscribeRealtime('scraping.item.updated', updateItem)
    const unsubscribeLogs = subscribeRealtime('scraping.item.log.appended', updateLogs)
    const unsubscribeResync = subscribeRealtime('system.resync_required', resync)
    return () => { unsubscribeItem(); unsubscribeLogs(); unsubscribeResync() }
  }, [itemId, itemKey, logsKey, queryClient])

  const item = itemQuery.data
  const logs = logsQuery.data ?? []

  return (
    <Drawer title={`子任务详情 · ${item?.movie_code ?? ''}`} open onClose={onClose} width="min(720px, 100vw)">
      {itemQuery.isPending ? <Skeleton active /> : itemQuery.isError ? (
        <Alert type="error" message="子任务加载失败" action={<Button size="small" onClick={() => void itemQuery.refetch()}>重试</Button>} />
      ) : item ? (
        <>
          <Card title="基本信息" className={styles.sectionCard}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="番号">{item.movie_code}</Descriptions.Item>
              <Descriptions.Item label="标题">{item.movie_title || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={ITEM_STATUS_COLOR[item.status]}>{ITEM_STATUS_TEXT[item.status] ?? item.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="当前步骤">{stepLabels[item.step ?? ''] ?? item.step ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="来源">{item.source || '-'}</Descriptions.Item>
              <Descriptions.Item label="文件夹">
                <Typography.Text className={styles.path}>{item.folder || '-'}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="耗时">{item.duration_ms ? `${item.duration_ms} ms` : '-'}</Descriptions.Item>
              {item.error_message && <Descriptions.Item label="错误"><Typography.Text type="danger">{item.error_message}</Typography.Text></Descriptions.Item>}
            </Descriptions>
          </Card>

          <Card title="步骤时间线" className={styles.sectionCard}>
            <Timeline items={stepOrder.map((step) => {
              const matching = logs.filter((log) => log.step === step)
              return {
                color: stepColor(item, logs, step),
                children: (
                  <div>
                    <Typography.Text strong>{stepLabels[step]}</Typography.Text>
                    {matching.length > 0 ? matching.map((log, index) => (
                      <div key={`${log.timestamp}-${index}`}>
                        <Typography.Text type={log.level === 'ERROR' ? 'danger' : 'secondary'}>
                          {formatTime(log.timestamp)} {log.message}
                        </Typography.Text>
                      </div>
                    )) : <div><Typography.Text type="secondary">等待执行</Typography.Text></div>}
                  </div>
                ),
              }
            })} />
          </Card>

          <Card title="任务日志">
            {logsQuery.isPending ? <Skeleton active paragraph={{ rows: 3 }} /> : logsQuery.isError ? (
              <Alert type="error" message="日志加载失败" action={<Button size="small" onClick={() => void logsQuery.refetch()}>重试</Button>} />
            ) : logs.length > 0 ? (
              <div className={styles.logScroll}>
                <Timeline items={logs.map((log, index) => ({
                  color: levelColors[log.level] || 'default',
                  children: (
                    <div key={`${log.timestamp}-${index}`} className={styles.logEntry}>
                      <Typography.Text type="secondary" className={styles.logTime}>{formatTime(log.timestamp)}</Typography.Text>
                      <Tag color={levelColors[log.level] || 'default'}>{log.level}</Tag>
                      <Typography.Text type={log.level === 'ERROR' ? 'danger' : undefined}>{log.message}</Typography.Text>
                    </div>
                  ),
                }))} />
              </div>
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无日志" />}
          </Card>
        </>
      ) : <Empty description="未找到子任务" />}
    </Drawer>
  )
}
