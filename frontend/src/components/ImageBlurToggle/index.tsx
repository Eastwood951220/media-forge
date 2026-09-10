import { EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons'
import { Button, Tooltip } from 'antd'
import { useImageBlurStore } from '@/stores/useImageBlurStore'

export function ImageBlurToggle() {
  const enabled = useImageBlurStore((state) => state.enabled)
  const toggle = useImageBlurStore((state) => state.toggle)
  const label = enabled ? '关闭图片模糊' : '开启图片模糊'

  return (
    <Tooltip title={label}>
      <Button
        aria-label={label}
        title={label}
        shape="circle"
        icon={enabled ? <EyeInvisibleOutlined /> : <EyeOutlined />}
        onClick={toggle}
      />
    </Tooltip>
  )
}
