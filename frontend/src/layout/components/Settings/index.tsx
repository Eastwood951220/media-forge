import { useMemo } from 'react'
import { SettingOutlined } from '@ant-design/icons'
import { Button, ColorPicker, Drawer, Switch } from 'antd'
import type { AggregationColor } from 'antd/es/color-picker/color'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './index.module.less'

const COLOR_PRESETS = [
  '#006AFF',
  '#722ED1',
  '#13C2C2',
  '#52C41A',
  '#FA8C16',
  '#F5222D',
  '#EB2F96',
  '#2F54EB',
]

type SettingItemProps = {
  label: string
  checked: boolean
  onChange: () => void
}

function SettingItem({ label, checked, onChange }: SettingItemProps) {
  return (
    <div className={styles['setting-row']}>
      <span className={styles['setting-label']}>{label}</span>
      <Switch size="small" checked={checked} onChange={onChange} />
    </div>
  )
}

function ColorDot({
  color,
  active,
  onClick,
}: {
  color: string
  active: boolean
  onClick: () => void
}) {
  const cls = `${styles['color-dot']} ${active ? styles['color-dot--active'] : ''}`
  return (
    <span
      className={cls}
      style={{ backgroundColor: color }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Set primary color to ${color}`}
    />
  )
}

function SettingsContent() {
  const showTagsView = useSettingsStore((s) => s.showTagsView)
  const showSidebarLogo = useSettingsStore((s) => s.showSidebarLogo)
  const fixedHeader = useSettingsStore((s) => s.fixedHeader)
  const toggleTagsView = useSettingsStore((s) => s.toggleTagsView)
  const toggleSidebarLogo = useSettingsStore((s) => s.toggleSidebarLogo)
  const toggleFixedHeader = useSettingsStore((s) => s.toggleFixedHeader)

  const darkMode = useThemeStore((s) => s.darkMode)
  const toggleMode = useThemeStore((s) => s.toggleMode)
  const primaryColor = useThemeStore((s) => s.primaryColor)
  const setPrimaryColor = useThemeStore((s) => s.setPrimaryColor)

  const handleColorChange = (_value: AggregationColor, css: string) => {
    setPrimaryColor(css)
  }

  const presetDots = useMemo(
    () =>
      COLOR_PRESETS.map((c) => (
        <ColorDot
          key={c}
          color={c}
          active={primaryColor.toLowerCase() === c.toLowerCase()}
          onClick={() => setPrimaryColor(c)}
        />
      )),
    [primaryColor, setPrimaryColor],
  )

  return (
    <div className={styles['drawer-body']}>
      <section className={styles.section}>
        <h4 className={styles['section-title']}>Interface</h4>
        <SettingItem label="Tags View" checked={showTagsView} onChange={toggleTagsView} />
        <SettingItem label="Sidebar Logo" checked={showSidebarLogo} onChange={toggleSidebarLogo} />
        <SettingItem label="Fixed Header" checked={fixedHeader} onChange={toggleFixedHeader} />
        <SettingItem label="Dark Mode" checked={darkMode} onChange={toggleMode} />
      </section>

      <section className={styles.section}>
        <h4 className={styles['section-title']}>Theme Color</h4>
        <div className={styles['color-presets']}>{presetDots}</div>
        <ColorPicker
          value={primaryColor}
          onChange={handleColorChange}
          showText
          disabledAlpha
          size="small"
        />
      </section>
    </div>
  )
}

export default function Settings() {
  const { isMobile } = useBreakpoint()
  const open = useSettingsStore((s) => s.showSettingsDrawer)
  const setOpen = useSettingsStore((s) => s.setShowSettingsDrawer)

  const handleClose = () => setOpen(false)

  return (
    <>
      {!isMobile && (
        <Button
          className={styles.trigger}
          icon={<SettingOutlined />}
          aria-label="Open settings"
          onClick={() => setOpen(true)}
        />
      )}
      <Drawer
        title="Settings"
        placement="right"
        width={isMobile ? '80vw' : 320}
        open={open}
        onClose={handleClose}
        destroyOnClose
      >
        <SettingsContent />
      </Drawer>
    </>
  )
}
