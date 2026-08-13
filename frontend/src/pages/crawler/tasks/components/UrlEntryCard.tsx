import { MinusCircleOutlined } from '@ant-design/icons'
import { Button, Card } from 'antd'
import type { UrlType } from '../taskUrlUtils'
import styles from '../TaskPages.module.less'
import UrlEntryFields from './UrlEntryFields'

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
      <UrlEntryFields
        index={index}
        onNameExtracted={onNameExtracted}
        onUrlTypeDetected={onUrlTypeDetected}
      />
    </Card>
  )
}