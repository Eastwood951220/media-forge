import styles from './LoginBackground.module.less'

function LoginBackground() {
  return (
    <div className={styles.background}>
      <div className={`${styles.orb} ${styles.orb1}`} />
      <div className={`${styles.orb} ${styles.orb2}`} />
      <div className={`${styles.orb} ${styles.orb3}`} />
    </div>
  )
}

export default LoginBackground
