import { Button, Space, Switch, Tag, Typography } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'

export interface SourcePriorityListProps {
  sources: string[]
  labels: Record<string, string>
  onChange: (sources: string[]) => void
}

const ALL_SOURCES = ['javdb', 'javbus']

export default function SourcePriorityList({ sources, labels, onChange }: SourcePriorityListProps) {
  const move = (index: number, offset: number) => {
    const next = index + offset
    if (next < 0 || next >= sources.length) return
    const updated = [...sources]
    ;[updated[index], updated[next]] = [updated[next], updated[index]]
    onChange(updated)
  }

  const toggle = (source: string, enabled: boolean) => {
    if (enabled) {
      onChange([...sources, source])
      return
    }
    const remaining = sources.filter((item) => item !== source)
    if (remaining.length > 0) onChange(remaining)
  }

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      {sources.map((source, index) => (
        <div key={source} style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
          <Tag color="blue">{index + 1}</Tag>
          <Typography.Text style={{ flex: 1 }}>{labels[source] ?? source}</Typography.Text>
          <Button
            size="small"
            icon={<ArrowUpOutlined />}
            aria-label={`上移 ${labels[source] ?? source}`}
            disabled={index === 0}
            onClick={() => move(index, -1)}
          />
          <Button
            size="small"
            icon={<ArrowDownOutlined />}
            aria-label={`下移 ${labels[source] ?? source}`}
            disabled={index === sources.length - 1}
            onClick={() => move(index, 1)}
          />
          <Switch
            checked
            aria-label={`启用 ${labels[source] ?? source}`}
            onChange={(value) => toggle(source, value)}
          />
        </div>
      ))}
      {ALL_SOURCES.filter((source) => !sources.includes(source)).map((source) => (
        <div key={source} style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
          <Tag color="default">-</Tag>
          <Typography.Text type="secondary" style={{ flex: 1 }}>{labels[source] ?? source}</Typography.Text>
          <Switch
            checked={false}
            aria-label={`启用 ${labels[source] ?? source}`}
            onChange={(value) => toggle(source, value)}
          />
        </div>
      ))}
    </Space>
  )
}
