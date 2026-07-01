import { useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Form, Input, Button, Checkbox, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { login } from '@/api/login'
import { useAuthStore } from '@/stores/useAuthStore'
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
import styles from './LoginPage.module.less'

interface LoginFormValues {
  username: string
  password: string
  rememberMe: boolean
}

function LoginPage() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const search = useSearch({ from: '/login' }) as { redirect?: string }
  const setLoginState = useAuthStore((s) => s.setLoginState)

  const handleFinish = async (values: LoginFormValues) => {
    setLoading(true)
    try {
      const res = await login({
        username: values.username,
        password: values.password,
      })
      const token = res.access_token

      if (!token) {
        void message.error('登录失败：未获取到 token')
        return
      }

      setLoginState(token)
      void message.success('登录成功')

      await navigate({ to: search.redirect || '/' })
    } catch {
      void message.error('登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles['login-page']}>
      <div className={styles['theme-toggle']}>
        <ThemeModeToggle variant="login" size="middle" />
      </div>
      <div className={styles['login-card']}>
        <div className={styles['login-title']}>
          <h2>Media Forge</h2>
          <p>媒体处理平台</p>
        </div>

        <Form<LoginFormValues>
          className={styles['login-form']}
          initialValues={{
            username: 'admin',
            password: 'admin123',
            rememberMe: false,
          }}
          onFinish={(values) => {
            void handleFinish(values)
          }}
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入您的账号' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="账号" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入您的密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          <div className={styles['remember-row']}>
            <Form.Item name="rememberMe" valuePropName="checked" noStyle>
              <Checkbox>记住密码</Checkbox>
            </Form.Item>
          </div>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              className={styles['login-btn']}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  )
}

export default LoginPage
