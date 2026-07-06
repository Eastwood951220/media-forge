import styles from '../StorageConfigPage.module.less'

export default function SectionTitle({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <span className={styles.sectionTitle}>
      {icon}
      {text}
    </span>
  )
}
