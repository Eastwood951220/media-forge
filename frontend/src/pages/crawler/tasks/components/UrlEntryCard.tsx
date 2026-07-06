import { useEffect, useState } from 'react'
import { MinusCircleOutlined, SearchOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Select, Switch } from 'antd'
import { extractTaskName } from '@/api/crawlTask'
import {
  buildFinalUrlPreview,
  detectUrlType,
  SEARCH_SORT_OPTIONS,
  SORT_OPTIONS,
  type UrlType,
  URL_TYPE_LABELS,
} from '../taskUrlUtils'
import styles from '../TaskPages.module.less'

export default function UrlEntryCard({
  index,
  remove,
  onNameExtracted,
  onUrlTypeDetected,
}: {
  index: number
  remove?: () => void
  onNameExtracted: (index: number, name: string) => void
  onUrlTypeDetected: (index: number, urlType: UrlType) => void
}) {
  const { message } = App.useApp()
  const form = Form.useFormInstance()
  const [extracting, setExtracting] = useState(false)

  // Reactively watch the URL value to detect URL type changes
  const url = Form.useWatch(['urls', index, 'url'], form) as string | undefined

  // Detect URL type from URL value and sync to form
  useEffect(() => {
    const urlStr = url ?? ''
    const detected = urlStr ? detectUrlType(urlStr) : null
    const currentType = form.getFieldValue(['urls', index, 'url_type']) as UrlType | undefined

    if (detected && detected !== currentType) {
      onUrlTypeDetected(index, detected)
    }
  }, [url, form, index, onUrlTypeDetected])

  return (
    <Card
      size="small"
      title={`URL ${index + 1}`}
      className={styles.urlCard}
      extra={
        remove ? (
          <Button
            type="text"
            danger
            icon={<MinusCircleOutlined />}
            onClick={remove}
            size="small"
            className={styles.urlCardDelete}
          />
        ) : null
      }
    >
      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url !== cur.urls?.[index]?.url}>
        {({ getFieldValue }) => {
          const url = (getFieldValue(['urls', index, 'url']) as string) ?? ''
          const detected = url ? detectUrlType(url) : null
          return (
            <>
              <Form.Item name={[index, 'url']} label="URL" rules={[{ required: true, message: '请输入 URL' }]}>
                <Input placeholder="https://javdb.com/actors/..." />
              </Form.Item>
              <Form.Item label="URL 类型">
                <Input
                  value={detected ? URL_TYPE_LABELS[detected] : url ? '无法识别' : '请输入 URL'}
                  disabled
                  style={{
                    color: detected ? '#1e40af' : undefined,
                    fontWeight: detected ? 500 : undefined,
                  }}
                />
              </Form.Item>
              <Form.Item name={[index, 'url_type']} hidden>
                <Input />
              </Form.Item>
              <Form.Item name={[index, 'url_name']} hidden>
                <Input />
              </Form.Item>
            </>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url_type !== cur.urls?.[index]?.url_type}>
        {({ getFieldValue }) => {
          const urlType = getFieldValue(['urls', index, 'url_type']) as UrlType
          if (!urlType) return null
          const sortOptions = urlType === 'search' ? SEARCH_SORT_OPTIONS : SORT_OPTIONS
          const showSort = urlType === 'video_codes' || urlType === 'search'
          return (
            <>
              <Form.Item name={[index, 'has_magnet']} label="含磁力链接" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name={[index, 'has_chinese_sub']} label="含中文字幕" valuePropName="checked">
                <Switch />
              </Form.Item>
              {showSort ? (
                <Form.Item name={[index, 'sort_type']} label="排序方式">
                  <Select options={sortOptions} />
                </Form.Item>
              ) : null}
            </>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const baseUrl = (getFieldValue(['urls', index, 'url']) as string) ?? ''
          const urlType = getFieldValue(['urls', index, 'url_type']) as UrlType
          const hasMagnet = (getFieldValue(['urls', index, 'has_magnet']) as boolean) ?? false
          const hasSub = (getFieldValue(['urls', index, 'has_chinese_sub']) as boolean) ?? false
          const sortType = (getFieldValue(['urls', index, 'sort_type']) as number) ?? 0
          const finalUrl = urlType ? buildFinalUrlPreview(baseUrl, urlType, hasMagnet, hasSub, sortType) : baseUrl
          return (
            <Form.Item label="最终 URL 预览">
              <Input
                value={finalUrl}
                disabled
                style={{
                  fontFamily: "'Fira Code', 'Cascadia Code', monospace",
                  fontSize: 12,
                  background: 'rgba(148, 163, 184, 0.06)',
                }}
              />
            </Form.Item>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url_name !== cur.urls?.[index]?.url_name}>
        {({ getFieldValue }) => {
          const urlName = getFieldValue(['urls', index, 'url_name']) as string | undefined
          return urlName ? (
            <Form.Item label="URL 名称">
              <Input
                value={urlName}
                disabled
                style={{
                  color: '#1e40af',
                  fontWeight: 500,
                  background: 'rgba(30, 64, 175, 0.04)',
                }}
              />
            </Form.Item>
          ) : null
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url !== cur.urls?.[index]?.url}>
        {({ getFieldValue }) => {
          const url = (getFieldValue(['urls', index, 'url']) as string) ?? ''
          const detected = url ? detectUrlType(url) : null
          return (
            <Button
              icon={<SearchOutlined />}
              loading={extracting}
              disabled={!url || !detected}
              onClick={async () => {
                if (!detected) return
                setExtracting(true)
                try {
                  const result = await extractTaskName(url, detected)
                  if (result.name) onNameExtracted(index, result.name)
                  else message.warning('未能提取到名称')
                } finally {
                  setExtracting(false)
                }
              }}
            >
              获取名称
            </Button>
          )
        }}
      </Form.Item>
    </Card>
  )
}
