import { useEffect, useState } from 'react'
import { App, Button, Card, Checkbox, Form, Input, InputNumber, Radio, Select, Space, Switch, Table, Tag, TimePicker, Typography, Upload } from 'antd'
import {
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PlayCircleOutlined,
  SaveOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import type { ColumnsType } from 'antd/es/table'

import {
  deleteBackupFile,
  getBackupConfig,
  getBackupDownloadUrl,
  getBackupJob,
  inspectBackupFile,
  listBackupFiles,
  restoreLocalBackup,
  startBackupExport,
  startBackupRestore,
  updateBackupConfig,
  type BackupConfig,
  type BackupFileInfo,
  type BackupGroup,
  type BackupGroupStats,
  type BackupInspectResult,
  type BackupJob,
  type BackupRestoreRequest,
  type RestoreMode,
} from '@/api/backup'
import { queryKeys } from '@/api/queryKeys'
import { invalidateBackupAfterRestore, invalidateBackupConfig, invalidateBackupFiles } from '@/api/queryInvalidation'
import styles from './BackupPage.module.less'

const GROUP_OPTIONS: Array<{ label: string; value: BackupGroup }> = [
  { label: '电影数据', value: 'movies' },
  { label: '任务与定时', value: 'tasks' },
  { label: '配置', value: 'config' },
]

const GROUP_LABELS: Record<BackupGroup, string> = {
  movies: '电影数据',
  tasks: '任务与定时',
  config: '配置',
}

const WEEKDAY_OPTIONS = [
  { label: '周一', value: 1 },
  { label: '周二', value: 2 },
  { label: '周三', value: 3 },
  { label: '周四', value: 4 },
  { label: '周五', value: 5 },
  { label: '周六', value: 6 },
  { label: '周日', value: 0 },
]

const DEFAULT_GROUPS: BackupGroup[] = ['movies', 'tasks', 'config']

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

function groupStatsSummary(result: Record<string, unknown>): string {
  const groups = ['movies', 'tasks', 'config'] as BackupGroup[]
  const parts = groups
    .filter((group) => result[group] !== undefined)
    .map((group) => {
      const stats = result[group] as BackupGroupStats
      return `${GROUP_LABELS[group]}: 新增 ${stats.created} / 更新 ${stats.updated} / 跳过 ${stats.skipped} / 冲突 ${stats.conflicts} / 错误 ${stats.errors}`
    })
  if (result.partial) parts.push('部分数据未能恢复，请检查错误数')
  return parts.join('；')
}

type PendingJob = {
  jobId: string
  onSuccess: (job: BackupJob) => void
}

export default function BackupPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [autoForm] = Form.useForm<BackupConfig>()
  const scheduleType = Form.useWatch('schedule_type', autoForm) ?? 'daily'

  // Manual export state.
  const [exportGroups, setExportGroups] = useState<BackupGroup[]>(DEFAULT_GROUPS)
  const [exportSensitive, setExportSensitive] = useState(false)

  // Restore state.
  const [restoreFile, setRestoreFile] = useState<File | null>(null)
  const [inspected, setInspected] = useState<BackupInspectResult | null>(null)
  const [restoreMode, setRestoreMode] = useState<RestoreMode>('merge')
  const [restoreGroups, setRestoreGroups] = useState<BackupGroup[]>(DEFAULT_GROUPS)
  const [inspecting, setInspecting] = useState(false)

  // Job polling state.
  const [pendingJob, setPendingJob] = useState<PendingJob | null>(null)
  const [jobProgress, setJobProgress] = useState<BackupJob | null>(null)

  const configQuery = useQuery({
    queryKey: queryKeys.backup.config(),
    queryFn: getBackupConfig,
  })

  const filesQuery = useQuery({
    queryKey: queryKeys.backup.files(),
    queryFn: listBackupFiles,
  })

  useEffect(() => {
    if (configQuery.data) {
      autoForm.setFieldsValue({
        ...configQuery.data,
        time_of_day: configQuery.data.time_of_day
          ? dayjs(configQuery.data.time_of_day, 'HH:mm')
          : dayjs('03:30', 'HH:mm'),
      } as unknown as BackupConfig)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only seed once per response.
  }, [configQuery.data])

  // Poll an in-process job until it settles.
  useEffect(() => {
    if (!pendingJob) return
    let stopped = false
    const tick = async () => {
      try {
        const job = await getBackupJob(pendingJob.jobId)
        if (stopped) return
        setJobProgress(job)
        if (job.status === 'succeeded') {
          setPendingJob(null)
          setJobProgress(null)
          pendingJob.onSuccess(job)
        } else if (job.status === 'failed' || job.status === 'skipped') {
          setPendingJob(null)
          setJobProgress(null)
          message.error(job.error || (job.status === 'skipped' ? '已有备份操作在运行，任务被跳过' : '备份任务失败'))
        }
      } catch {
        // Transient poll errors are ignored; the next tick retries.
      }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 1500)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [pendingJob, message])

  const busy = pendingJob !== null

  // -- Manual export -----------------------------------------------------

  const handleManualExport = async () => {
    if (exportGroups.length === 0) return
    const proceed = async () => {
      const response = await startBackupExport({ groups: exportGroups, include_sensitive: exportSensitive })
      setPendingJob({
        jobId: response.job_id,
        onSuccess: (job) => {
          const fileName = String(job.result?.file_name ?? '')
          message.success(fileName ? `备份完成：${fileName}` : '备份完成')
          void invalidateBackupFiles(queryClient)
        },
      })
    }
    if (exportSensitive) {
      modal.confirm({
        title: '包含敏感配置',
        content: '备份将写入 JavDB Cookie 与云盘 API Token 等敏感配置，请妥善保管备份文件。',
        okText: '继续备份',
        cancelText: '取消',
        onOk: () => proceed(),
      })
    } else {
      await proceed()
    }
  }

  // -- Upload restore ----------------------------------------------------

  const handleInspect = async () => {
    if (!restoreFile) return
    setInspecting(true)
    try {
      const result = await inspectBackupFile(restoreFile)
      setInspected(result)
      setRestoreGroups(result.groups.length > 0 ? result.groups : DEFAULT_GROUPS)
      setRestoreMode('merge')
      message.success('备份文件检查完成')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '备份文件检查失败')
    } finally {
      setInspecting(false)
    }
  }

  const handleUploadRestore = async () => {
    if (!restoreFile || !inspected) return
    const payload: BackupRestoreRequest = { mode: restoreMode, groups: restoreGroups }
    const run = async () => {
      const response = await startBackupRestore(restoreFile, payload)
      setPendingJob({
        jobId: response.job_id,
        onSuccess: (job) => {
          message.success(`恢复完成。${groupStatsSummary(job.result)}`)
          invalidateBackupAfterRestore(queryClient, restoreGroups)
        },
      })
    }
    if (restoreMode === 'overwrite') {
      modal.confirm({
        title: '覆盖恢复',
        content: '覆盖恢复会先清空所选分组的现有数据再导入备份内容，且不会恢复历史运行记录。确定继续？',
        okText: '覆盖恢复',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: () => run(),
      })
    } else {
      await run()
    }
  }

  // -- Local file restore / delete --------------------------------------

  const handleLocalRestore = (file: BackupFileInfo, mode: RestoreMode) => {
    const groups = file.groups.length > 0 ? file.groups : DEFAULT_GROUPS
    const run = async () => {
      const response = await restoreLocalBackup(file.name, { mode, groups })
      setPendingJob({
        jobId: response.job_id,
        onSuccess: (job) => {
          message.success(`恢复完成。${groupStatsSummary(job.result)}`)
          invalidateBackupAfterRestore(queryClient, groups)
        },
      })
    }
    if (mode === 'overwrite') {
      modal.confirm({
        title: '覆盖恢复',
        content: `将以覆盖方式恢复「${file.name}」，先清空所选分组现有数据再导入。确定继续？`,
        okText: '覆盖恢复',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: () => run(),
      })
    } else {
      void run()
    }
  }

  const handleDeleteFile = (file: BackupFileInfo) => {
    modal.confirm({
      title: '删除备份文件',
      content: `确定删除备份文件「${file.name}」？删除后无法恢复该文件。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await deleteBackupFile(file.name)
        message.success('备份文件已删除')
        void invalidateBackupFiles(queryClient)
      },
    })
  }

  // -- Automatic backup --------------------------------------------------

  const handleAutoSave = async (values: BackupConfig) => {
    const timeOfDay = values.time_of_day ? dayjs(values.time_of_day).format('HH:mm') : '03:30'
    const scheduleType = values.schedule_type ?? 'daily'
    const weekdays = scheduleType === 'weekly' ? (values.weekdays ?? []) : []
    const payload: BackupConfig = {
      enabled: Boolean(values.enabled),
      backup_dir: values.backup_dir || '/data/backups',
      schedule_type: scheduleType,
      time_of_day: timeOfDay,
      weekdays,
      groups: values.groups && values.groups.length > 0 ? values.groups : DEFAULT_GROUPS,
      include_sensitive: Boolean(values.include_sensitive),
      retention_count: values.retention_count ?? 10,
    }
    const updated = await updateBackupConfig(payload)
    autoForm.setFieldsValue({ ...updated, time_of_day: dayjs(updated.time_of_day, 'HH:mm') } as unknown as BackupConfig)
    void invalidateBackupConfig(queryClient)
    message.success('自动备份设置已保存')
  }

  const columns: ColumnsType<BackupFileInfo> = [
    {
      title: '文件',
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string) => <Typography.Text copyable={{ text: name }}>{name}</Typography.Text>,
    },
    {
      title: '内容',
      dataIndex: 'groups',
      width: 220,
      render: (groups: BackupGroup[], record: BackupFileInfo) => (
        <Space size={4} wrap>
          {groups.map((group) => (
            <Tag key={group} color="blue">{GROUP_LABELS[group] ?? group}</Tag>
          ))}
          {record.include_sensitive && <Tag color="orange">含敏感配置</Tag>}
        </Space>
      ),
    },
    { title: '大小', dataIndex: 'size', width: 100, render: formatSize },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 230,
      render: (_value, record) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            icon={<DownloadOutlined />}
            href={getBackupDownloadUrl(record.name)}
            target="_blank"
            rel="noreferrer"
          >
            下载
          </Button>
          <Button type="link" size="small" icon={<PlayCircleOutlined />} disabled={busy} onClick={() => handleLocalRestore(record, 'merge')}>
            合并恢复
          </Button>
          <Button type="link" size="small" danger disabled={busy} onClick={() => handleLocalRestore(record, 'overwrite')}>
            覆盖恢复
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} disabled={busy} onClick={() => handleDeleteFile(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const fileData = filesQuery.data ?? []

  return (
    <div className={styles.page}>
      <div className={styles.layout}>
        <div className={styles.mainPanel}>
          <Card
            title="手动备份"
            extra={jobProgress ? <JobProgress job={jobProgress} /> : undefined}
          >
            <Space orientation="vertical" size={16} style={{ width: '100%' }}>
              <Checkbox.Group
                options={GROUP_OPTIONS}
                value={exportGroups}
                onChange={(values) => setExportGroups(values as BackupGroup[])}
              />
              <div className={styles.sensitiveRow}>
                <Space>
                  <span>包含敏感配置（JavDB Cookie、云盘 Token）</span>
                  <Switch size="small" checked={exportSensitive} onChange={setExportSensitive} />
                </Space>
              </div>
              <Button type="primary" icon={<CloudUploadOutlined />} loading={busy} disabled={exportGroups.length === 0} onClick={() => void handleManualExport()}>
                开始备份
              </Button>
            </Space>
          </Card>

          <Card title="恢复备份">
            <Space orientation="vertical" size={16} style={{ width: '100%' }}>
              <Space size={8} wrap>
                <Upload
                  accept=".mfbackup"
                  maxCount={1}
                  beforeUpload={() => false}
                  onChange={(info) => {
                    const file = info.fileList[0]?.originFileObj ?? null
                    setRestoreFile(file)
                    setInspected(null)
                  }}
                  onRemove={() => {
                    setRestoreFile(null)
                    setInspected(null)
                  }}
                >
                  <Button icon={<UploadOutlined />}>选择 .mfbackup 文件</Button>
                </Upload>
                <Button icon={<PlayCircleOutlined />} loading={inspecting} disabled={!restoreFile} onClick={() => void handleInspect()}>
                  检查备份内容
                </Button>
              </Space>

              {inspected && (
                <div className={styles.inspectSummary}>
                  <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                    <Space size={8} wrap>
                      <span>包含分组：</span>
                      {inspected.groups.length > 0 ? (
                        inspected.groups.map((group) => (
                          <Tag key={group} color="blue">{GROUP_LABELS[group] ?? group}</Tag>
                        ))
                      ) : (
                        <Tag>未知</Tag>
                      )}
                      {inspected.include_sensitive && <Tag color="orange">含敏感配置</Tag>}
                    </Space>
                    <Typography.Text type="secondary">
                      {Object.entries(inspected.row_counts)
                        .map(([name, count]) => `${name.replace('data/', '').replace('.jsonl', '')}: ${count}`)
                        .join('，')}
                    </Typography.Text>
                  </Space>
                </div>
              )}

              <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                <Radio.Group value={restoreMode} onChange={(event) => setRestoreMode(event.target.value as RestoreMode)}>
                  <Radio value="merge">合并（保留现有数据，冲突跳过）</Radio>
                  <Radio value="overwrite">覆盖（清空所选分组后导入）</Radio>
                </Radio.Group>
                <div>
                  <div className={styles.groupLabel}>恢复分组</div>
                  <Checkbox.Group
                    options={GROUP_OPTIONS}
                    value={restoreGroups}
                    disabled={!inspected}
                    onChange={(values) => setRestoreGroups(values as BackupGroup[])}
                  />
                </div>
                <Button
                  type="primary"
                  danger={restoreMode === 'overwrite'}
                  disabled={!restoreFile || !inspected || restoreGroups.length === 0 || busy}
                  loading={busy}
                  onClick={() => void handleUploadRestore()}
                >
                  开始恢复
                </Button>
                <AlertInline text="恢复不会写入历史运行记录；覆盖恢复需要二次确认。" />
              </Space>
            </Space>
          </Card>
        </div>

        <div className={styles.sidePanel}>
          <Card title="自动备份" loading={configQuery.isLoading}>
            <Form form={autoForm} layout="vertical" onFinish={(values) => void handleAutoSave(values as BackupConfig)}>
              <Form.Item name="enabled" label="启用自动备份" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name="backup_dir" label="备份目录" rules={[{ required: true, message: '请输入备份目录' }]}>
                <Input placeholder="默认 data/backups" />
              </Form.Item>
              <Form.Item name="schedule_type" label="执行频率">
                <Radio.Group
                  options={[
                    { label: '每天', value: 'daily' },
                    { label: '每周', value: 'weekly' },
                  ]}
                />
              </Form.Item>
              <Form.Item label="执行时间" required>
                <Space size={12}>
                  <Form.Item name="time_of_day" noStyle>
                    <TimePicker format="HH:mm" minuteStep={5} style={{ width: 130 }} />
                  </Form.Item>
                  <Form.Item name="weekdays" noStyle>
                    <Select
                      mode="multiple"
                      placeholder="选择星期"
                      style={{ minWidth: 260 }}
                      options={WEEKDAY_OPTIONS}
                      maxTagCount="responsive"
                      disabled={scheduleType !== 'weekly'}
                    />
                  </Form.Item>
                </Space>
              </Form.Item>
              <Form.Item name="groups" label="备份内容">
                <Checkbox.Group options={GROUP_OPTIONS} />
              </Form.Item>
              <Form.Item name="include_sensitive" label="包含敏感配置" valuePropName="checked">
                <Switch size="small" />
              </Form.Item>
              <Form.Item name="retention_count" label="本地保留份数">
                <InputNumber min={1} max={365} style={{ width: 140 }} />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} block>
                保存设置
              </Button>
            </Form>

            <div className={styles.fileListHeader}>近期备份文件</div>
            <Table<BackupFileInfo>
              rowKey="name"
              size="small"
              columns={columns}
              dataSource={fileData}
              loading={filesQuery.isLoading}
              pagination={{ pageSize: 5, hideOnSinglePage: true }}
              locale={{ emptyText: '暂无本地备份文件' }}
            />
          </Card>
        </div>
      </div>
    </div>
  )
}

function JobProgress({ job }: { job: BackupJob }) {
  const percent = job.total ? Math.min(100, Math.round((job.processed / job.total) * 100)) : undefined
  return (
    <Space size={8}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {job.phase}
      </Typography.Text>
      <span style={{ width: 140, display: 'inline-block' }}>
        {percent === undefined ? <ProgressLine /> : <ProgressLine percent={percent} />}
      </span>
    </Space>
  )
}

function ProgressLine({ percent }: { percent?: number }) {
  // Small dependency-free progress bar to avoid pulling antd Progress into the
  // Card extra slot with unexpected layout.
  return (
    <div className={styles.progressTrack}>
      <div className={styles.progressFill} style={{ width: percent === undefined ? '40%' : `${percent}%` }} />
    </div>
  )
}

function AlertInline({ text }: { text: string }) {
  return <Typography.Text type="secondary" style={{ fontSize: 12 }}>{text}</Typography.Text>
}
