import { useMemo } from 'react'
import { Collapse, Tag, Typography } from 'antd'
import type { AgentEvent } from '@/api/crawler/crawlerAgent/types'
import styles from '../RunDetailPage.module.less'

const eventLabels: Record<string, string> = {
  'work.created': '创建列表任务',
  'work.assigned': 'Agent 已领取',
  'work.started': '开始执行',
  'tab.opened': '浏览器标签页已打开',
  'page.loading': '等待页面加载',
  'page.loaded': '页面加载完成',
  'snapshot.collecting': '正在采集页面',
  'snapshot.collected': '页面采集完成',
  'snapshot.uploading': '正在上传快照',
  'work.requeued': '连接断开，任务重新入队',
  'work.completed': 'Agent 任务完成',
  'work.failed': 'Agent 任务失败',
  'work.claim_timeout': 'Agent 领取超时',
  'work.execution_timeout': 'Agent 执行超时',
}

const errorMessages: Record<string, string> = {
  agent_claim_timeout: 'Agent 在线但未及时领取任务',
  agent_execution_timeout: 'Agent 已领取任务但页面执行超时',
  agent_connection_lost: 'Agent 连接断开，任务失败',
  agent_backend_restarted: '后端重启，任务被终止',
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

function formatElapsed(fromIso: string | null, toIso: string | null): string {
  if (!fromIso) return ''
  const from = Date.parse(fromIso)
  const to = toIso ? Date.parse(toIso) : Date.now()
  if (Number.isNaN(from) || Number.isNaN(to)) return ''
  const seconds = Math.max(0, Math.floor((to - from) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  return `${minutes} 分 ${seconds % 60} 秒`
}

function eventLabel(event: AgentEvent): string {
  return eventLabels[event.event_type] ?? event.message
}

function eventTone(event: AgentEvent): string {
  if (event.level === 'error' || event.event_type.includes('failed') || event.event_type.includes('timeout')) {
    return styles.timelineItemError
  }
  if (event.level === 'warning' || event.event_type.includes('requeued')) {
    return styles.timelineItemWarning
  }
  if (event.event_type.includes('completed') || event.event_type.includes('loaded') || event.event_type.includes('collected')) {
    return styles.timelineItemSuccess
  }
  return styles.timelineItemInfo
}

function statusColor(status: string): string {
  if (status === 'failed') return 'red'
  if (status === 'completed') return 'green'
  if (!status) return 'default'
  return 'processing'
}

interface AgentExecutionTimelineProps {
  events: AgentEvent[]
  workItemId: string
  url: string
  pageKind: string
  status: string
  attempt: number
  maxAttempts: number
  errorReason: string | null
  startedAt: string | null
  finishedAt: string | null
}

export default function AgentExecutionTimeline({
  events,
  workItemId,
  url,
  pageKind,
  status,
  attempt,
  maxAttempts,
  errorReason,
  startedAt,
  finishedAt,
}: AgentExecutionTimelineProps) {
  const ordered = useMemo(
    () => [...events].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [events],
  )

  const terminalError = useMemo(() => {
    if (!errorReason) return null
    return errorMessages[errorReason] ?? errorReason
  }, [errorReason])

  const title = pageKind === 'list' ? '列表页' : pageKind === 'detail' ? '详情页' : '运行级事件'

  return (
    <div className={styles.agentTimeline}>
      <div className={styles.agentTimelineHeader}>
        <div className={styles.agentTimelineTitleRow}>
          <Typography.Text strong>{title}</Typography.Text>
          {url && <Typography.Text code className={styles.agentTimelineUrl}>{url}</Typography.Text>}
        </div>
        <div className={styles.agentTimelineTags}>
          {attempt > 0 && <Tag color="blue">尝试 {attempt} / {maxAttempts}</Tag>}
          {status && (
            <Tag color={statusColor(status)}>
            {status}
            </Tag>
          )}
          {terminalError && <Tag color="red">{terminalError}</Tag>}
        </div>
      </div>

      <Collapse
        size="small"
        items={[
          {
            key: 'tech',
            label: '技术详情',
            children: (
              <div className={styles.agentTechDetails}>
                <p>
                  work_item_id: <Typography.Text code>{workItemId}</Typography.Text>
                </p>
                <p>耗时: {formatElapsed(startedAt, finishedAt) || '-'}</p>
                {ordered.map((event) => (
                  <div key={event.id} className={styles.agentTechEvent}>
                    <div>
                      {event.event_type} · {event.source} · attempt {event.attempt ?? '-'}
                    </div>
                    {event.details && (
                      <div>
                        <Typography.Text code style={{ fontSize: 12 }}>
                          {JSON.stringify(event.details)}
                        </Typography.Text>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />

      <ol className={styles.timelineList}>
        {ordered.map((event) => (
          <li key={event.id} className={`${styles.timelineItem} ${eventTone(event)}`}>
            <span className={styles.timelineRail} aria-hidden="true" />
            <div className={styles.timelineContent}>
              <div className={styles.timelineMain}>
                <Typography.Text strong className={styles.timelineEventLabel}>
                  {eventLabel(event)}
                </Typography.Text>
                <Typography.Text type="secondary" className={styles.timelineTime}>
                  {formatTime(event.created_at)}
                </Typography.Text>
              </div>
              <div className={styles.timelineMeta}>
                <Tag className={styles.timelineTag}>{event.source}</Tag>
                <Tag className={styles.timelineTag}>
                  {event.level === 'error' ? '错误' : event.level === 'warning' ? '警告' : '信息'}
                </Tag>
                {event.attempt != null && <Tag className={styles.timelineTag}>attempt {event.attempt}</Tag>}
                {event.level === 'warning' && <Tag color="orange" className={styles.timelineTag}>重试</Tag>}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
