import styles from './LoginBrandPanel.module.less'

const features = [
  '高效的多媒体文件处理引擎',
  '智能批量转码与格式转换'
]

function LoginBrandPanel() {
  return (
    <div className={styles.panel}>
      <div className={styles.logo}>
        <span className={styles.logoIcon}>MF</span>
      </div>
      <h1 className={styles.name}>Media Forge</h1>
      <p className={styles.tagline}>
        专业的媒体处理平台
          <br />
          转换所有数字媒体资产
      </p>
      <ul className={styles.features}>
        {features.map((text) => (
          <li key={text} className={styles.featureItem}>
            <span className={styles.featureDot} />
            {text}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default LoginBrandPanel
