import { clsx } from 'clsx'
import { InputNumber, type InputNumberProps } from 'antd'
import styles from './FullWidthNumberInput.module.less'

export function FullWidthNumberInput(props: InputNumberProps) {
  const { className, ...rest } = props
  return <InputNumber {...rest} className={clsx(styles.fullWidth, className)} />
}
