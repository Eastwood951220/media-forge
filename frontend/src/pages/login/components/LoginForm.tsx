import { useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Form, Input, Button, Checkbox, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { login } from '@/api/login'
import { useAuthStore } from '@/stores/useAuthStore'
import type { LoginResult } from '@/api/login/types'
import styles from './LoginForm.module.less'

interface LoginFormValues {
  username: string
  password: string
  rememberMe: boolean
}

function LoginForm() {
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
      const token = (res as LoginResult).access_token

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
    <div className={styles.card}>
      <h2 className={styles.title}>欢迎回来</h2>
      <p className={styles.subtitle}>请登录您的账户以继续</p>

      <Form<LoginFormValues>
        className={styles.form}
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

        <div className={styles.actions}>
          <Form.Item name="rememberMe" valuePropName="checked" noStyle>
            <Checkbox>记住密码</Checkbox>
          </Form.Item>
        </div>

        <Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            className={styles.submitBtn}
          >
            登录
          </Button>
        </Form.Item>
      </Form>
    </div>
  )
}

export default LoginForm
