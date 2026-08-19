import { useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Descriptions,
  Popconfirm,
  Space,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import { useAgentDiagnostics } from '../hooks/useAgentDiagnostics'
import AgentEventList from './AgentEventList'
import styles from '../ConfigPage.module.less'

const statusMeta = {
  not_configured: ['未配置', 'default'],
  offline: ['离线', 'default'],
  online: ['在线', 'success'],
  busy: ['执行中', 'processing'],
  error: ['异常', 'error'],
  upgrade_required: ['需要升级扩展', 'error'],
} as const

const MAX_ATTEMPTS = 3

function formatDuration(startIso: string | null): string {
  if (!startIso) return '-'
  const start = Date.parse(startIso)
  if (Number.isNaN(start)) return '-'
  const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  return `${minutes} 分 ${seconds % 60} 秒`
}

function formatRelative(iso: string | null): string {
  if (!iso) return '-'
  const at = Date.parse(iso)
  if (Number.isNaN(at)) return '-'
  const seconds = Math.max(0, Math.floor((Date.now() - at) / 1000))
  if (seconds < 60) return `${seconds} 秒前`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  return `${hours} 小时前`
}

export default function AgentHealthCard() {
  const {
    status,
    statusLoading,
    events,
    eventsLoading,
    hasNextPage,
    fetchNextPage,
    loadingMore,
    levelFilter,
    setLevelFilter,
    sourceFilter,
    setSourceFilter,
    refresh,
    clearLoading,
    handleClear,
    rotateToken,
    tokenRotating,
  } = useAgentDiagnostics()

  const [agentToken, setAgentToken] = useState<string | null>(null)

  const meta = statusMeta[status?.status ?? 'not_configured']
  const [label, color] = meta

  const counters = useMemo(() => {
    if (!status) {
      return { pending: 0, active: 0 }
    }
    return { pending: status.pending_count, active: status.active_count }
  }, [status])

  const currentWorkItem = status?.current_work_item ?? null
  const currentAttempt = currentWorkItem?.attempt ?? 0

  const handleRotateToken = async () => {
    try {
      setAgentToken(await rotateToken())
    } catch {
      // The mutation already reports the normalized request error.
    }
  }

  return (
    <div className={styles.agentHealthCard}>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="状态">
          <Tag color={color}>{label}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="协议版本">
          {status?.protocol_version != null ? `v${status.protocol_version}` : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="扩展版本">
          {status?.version ?? '-'}
        </Descriptions.Item>
        <Descriptions.Item label="连接时长">
          {status?.status === 'online' || status?.status === 'busy'
            ? formatDuration(status.connected_at)
            : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="相对心跳">
          {formatRelative(status?.last_seen_at ?? null)}
        </Descriptions.Item>
        <Descriptions.Item label="当前阶段">
          {currentWorkItem ? (
            <Typography.Text>
              {currentWorkItem.page_kind === 'list' ? '列表页' : '详情页'} ·{' '}
              {currentWorkItem.status}
            </Typography.Text>
          ) : (
            '-'
          )}
        </Descriptions.Item>
        <Descriptions.Item label="尝试次数">
          {currentWorkItem ? `${currentAttempt} / ${MAX_ATTEMPTS}` : '-'}
        </Descriptions.Item>
      </Descriptions>

      <Space style={{ marginTop: 12 }} size={16}>
        <Statistic title="待领取" value={counters.pending} />
        <Statistic title="执行中" value={counters.active} />
      </Space>

      {agentToken && (
        <Alert
          className={styles.cookieTestResult}
          type="warning"
          showIcon
          title="Agent Token 仅显示一次"
          description={
            <Typography.Text copyable={{ text: agentToken }}>
              {agentToken}
            </Typography.Text>
          }
        />
      )}

      <Space style={{ marginTop: 12 }}>
        <Button onClick={refresh} loading={statusLoading}>
          刷新状态
        </Button>
        <Popconfirm
          title="重新生成 Agent Token？"
          description="重新生成后旧 Token 将失效。"
          okText="确定"
          cancelText="取消"
          onConfirm={() => handleRotateToken()}
        >
          <Button danger loading={tokenRotating}>
            生成 Agent Token
          </Button>
        </Popconfirm>
        <Popconfirm
          title="清理近期诊断日志？"
          description="仅清理 7 天内的操作日志，运行审计日志会保留。"
          onConfirm={handleClear}
        >
          <Button danger loading={clearLoading}>
            清理近期日志
          </Button>
        </Popconfirm>
      </Space>

      <AgentEventList
        events={events}
        loading={eventsLoading}
        levelFilter={levelFilter}
        onLevelFilterChange={setLevelFilter}
        sourceFilter={sourceFilter}
        onSourceFilterChange={setSourceFilter}
        hasNextPage={hasNextPage}
        fetchNextPage={fetchNextPage}
        loadingMore={loadingMore}
      />
    </div>
  )
}
