import LoginBackground from './components/LoginBackground'
import LoginBrandPanel from './components/LoginBrandPanel'
import LoginForm from './components/LoginForm'
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
import styles from './LoginPage.module.less'

function LoginPage() {
  return (
    <div className={styles.page}>
      {/* Background orbs — shared across both panels */}
      <LoginBackground />

      {/* Left brand panel */}
      <div className={styles.left}>
        <div className={styles.gridTexture} />
        <LoginBrandPanel />
      </div>

      {/* Right login panel */}
      <div className={styles.right}>
        <div className={styles.rightEnter}>
          <LoginForm />
        </div>
      </div>

      {/* Theme toggle */}
      <div className={styles.themeToggle}>
        <ThemeModeToggle variant="login" size="middle" />
      </div>
    </div>
  )
}

export default LoginPage
