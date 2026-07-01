# Media Forge Login Page Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the login page with enterprise glassmorphism left-right split layout, animated background orbs, brand panel, and themed glass login card.

**Architecture:** LoginPage becomes a layout container composing 3 new sub-components: `LoginBackground` (CSS-only animated orbs), `LoginBrandPanel` (left brand area), `LoginForm` (right glass card with form logic). Theme primary color updated to `#006AFF`. All existing auth/login/routing logic preserved.

**Tech Stack:** React 19, TypeScript 6, Ant Design 6, Less Modules, CSS animations

## Global Constraints

- No `any`, `@ts-ignore`, `@ts-nocheck` in application code
- No inline `style` props (use CSS Modules)
- No new npm dependencies
- Primary color: `#006AFF` (rgb(0, 106, 255))
- Glassmorphism: `backdrop-filter: blur(20px) saturate(130%)` with `@supports` fallback
- CSS animations only (no framer-motion or animation libraries)
- `prefers-reduced-motion: reduce` must disable animations
- Login API, auth store, route definitions untouched
- `tsc -b`, `eslint .`, `npm run build`, `vitest run` all pass

## Reference Spec

[Design Spec](../specs/2026-07-01-media-forge-login-redesign.md) — contains exact color values, glassmorphism parameters, animation specs, input/button states, and responsive breakpoints.

---

### Task 1: Update `useThemeStore` primary color default

**Files:**
- Modify: `frontend/src/stores/useThemeStore.ts:24`

**Interfaces:**
- Produces: `primaryColor` default changes from `'#0f3076'` to `'#006AFF'`
- Consumed by: ConfigProvider in `routes/index.tsx` (already reads `primaryColor` from store)

- [ ] **Step 1: Change the default primaryColor**

Read `src/stores/useThemeStore.ts`. Change line 24 from:
```typescript
        primaryColor: '#0f3076',
```
To:
```typescript
        primaryColor: '#006AFF',
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/stores/useThemeStore.ts
git commit -m "feat: update primary color to #006AFF"
```

---

### Task 2: Create `LoginBackground` component (animated orbs)

**Files:**
- Create: `frontend/src/pages/login/components/LoginBackground.tsx`
- Create: `frontend/src/pages/login/components/LoginBackground.module.less`

**Interfaces:**
- Produces: `<LoginBackground />` — absolutely positioned container with 3 blurred orbs
- Consumed by: LoginPage layout (Task 5)

- [ ] **Step 1: Write LoginBackground.module.less**

```less
.background {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
}

.orb1 {
  width: 480px;
  height: 480px;
  background: radial-gradient(circle, rgba(0, 106, 255, 0.25), transparent 70%);
  top: -15%;
  left: -10%;
  animation: orbDrift 16s ease-in-out infinite alternate;
}

.orb2 {
  width: 320px;
  height: 320px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.18), transparent 70%);
  bottom: -12%;
  right: 15%;
  animation: orbDrift 13s ease-in-out infinite alternate-reverse;
}

.orb3 {
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.15), transparent 70%);
  top: 45%;
  left: 35%;
  animation: orbDrift 18s ease-in-out infinite alternate;
}

@keyframes orbDrift {
  0% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(20px, -15px) scale(1.08);
  }
  100% {
    transform: translate(-10px, 25px) scale(0.95);
  }
}

/* Dark mode — dim orbs */
:global([data-theme="dark"]) .orb {
  opacity: 0.18;
}

@media (prefers-reduced-motion: reduce) {
  .orb {
    animation: none;
  }
}
```

- [ ] **Step 2: Write LoginBackground.tsx**

```typescript
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
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/login/components/LoginBackground.tsx src/pages/login/components/LoginBackground.module.less
git commit -m "feat: add LoginBackground with animated orbs"
```

---

### Task 3: Create `LoginBrandPanel` component

**Files:**
- Create: `frontend/src/pages/login/components/LoginBrandPanel.tsx`
- Create: `frontend/src/pages/login/components/LoginBrandPanel.module.less`

**Interfaces:**
- Produces: `<LoginBrandPanel />` — left panel with logo area, system name, tagline, 3 feature bullets
- Consumed by: LoginPage layout (Task 5)

- [ ] **Step 1: Write LoginBrandPanel.module.less**

```less
.panel {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 80px 64px;
  height: 100%;
}

.logo {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: linear-gradient(135deg, #006AFF, #3399FF);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 28px;
  box-shadow: 0 4px 16px rgba(0, 106, 255, 0.3);

  .logoIcon {
    color: white;
    font-size: 24px;
    font-weight: 700;
  }
}

.name {
  font-size: 32px;
  font-weight: 700;
  color: #1E293B;
  margin: 0 0 12px;
  letter-spacing: -0.5px;

  :global([data-theme="dark"]) & {
    color: #F1F5F9;
  }
}

.tagline {
  font-size: 15px;
  color: #64748B;
  margin: 0 0 40px;
  line-height: 1.6;

  :global([data-theme="dark"]) & {
    color: #94A3B8;
  }
}

.features {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.featureItem {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: #475569;

  :global([data-theme="dark"]) & {
    color: #94A3B8;
  }
}

.featureDot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #006AFF;
  flex-shrink: 0;
  box-shadow: 0 0 8px rgba(0, 106, 255, 0.3);
}

/* Responsive */
@media (max-width: 768px) {
  .panel {
    display: none;
  }
}
```

- [ ] **Step 2: Write LoginBrandPanel.tsx**

```typescript
import styles from './LoginBrandPanel.module.less'

const features = [
  '高效的多媒体文件处理引擎',
  '智能批量转码与格式转换',
  '企业级安全与权限管理',
]

function LoginBrandPanel() {
  return (
    <div className={styles.panel}>
      <div className={styles.logo}>
        <span className={styles.logoIcon}>M</span>
      </div>
      <h1 className={styles.name}>Media Forge</h1>
      <p className={styles.tagline}>
        专业的媒体处理平台，助力企业高效管理
        <br />
        和转换所有数字媒体资产
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
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/login/components/LoginBrandPanel.tsx src/pages/login/components/LoginBrandPanel.module.less
git commit -m "feat: add LoginBrandPanel component"
```

---

### Task 4: Create `LoginForm` component (glassmorphism card + form logic)

**Files:**
- Create: `frontend/src/pages/login/components/LoginForm.tsx`
- Create: `frontend/src/pages/login/components/LoginForm.module.less`

**This extracts form logic from the current `LoginPage.tsx` and adds glassmorphism styling.**

- [ ] **Step 1: Write LoginForm.module.less**

```less
.card {
  width: 420px;
  padding: 44px 40px;
  background: rgba(255, 255, 255, 0.64);
  backdrop-filter: blur(20px) saturate(130%);
  -webkit-backdrop-filter: blur(20px) saturate(130%);
  border: 1px solid rgba(255, 255, 255, 0.48);
  border-radius: 22px;
  box-shadow:
    0 24px 60px rgba(15, 23, 42, 0.12),
    0 4px 12px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.45);
  transition: background-color 300ms, border-color 300ms, box-shadow 300ms;

  // Dark mode
  :global([data-theme="dark"]) & {
    background: rgba(20, 28, 45, 0.72);
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow:
      0 24px 60px rgba(0, 0, 0, 0.35),
      0 4px 12px rgba(0, 0, 0, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.08);
  }

  // No backdrop-filter fallback
  @supports not (backdrop-filter: blur(1px)) {
    background: rgba(255, 255, 255, 0.92);

    :global([data-theme="dark"]) & {
      background: rgba(20, 28, 45, 0.92);
    }
  }
}

.title {
  font-size: 24px;
  font-weight: 700;
  color: #1E293B;
  margin: 0 0 8px;
  text-align: center;

  :global([data-theme="dark"]) & {
    color: #F1F5F9;
  }
}

.subtitle {
  font-size: 14px;
  color: #64748B;
  margin: 0 0 36px;
  text-align: center;

  :global([data-theme="dark"]) & {
    color: #94A3B8;
  }
}

.form {
  :global(.ant-input-affix-wrapper) {
    height: 46px;
    border-radius: 10px;
    border-color: rgba(0, 0, 0, 0.12);
    transition: border-color 200ms, box-shadow 200ms;

    &:hover {
      border-color: rgba(0, 0, 0, 0.2);
    }

    &:focus-within,
    :global(.ant-input-affix-wrapper-focused) {
      border-color: #006AFF;
      box-shadow: 0 0 0 3px rgba(0, 106, 255, 0.15);
    }

    :global([data-theme="dark"]) & {
      background: rgba(255, 255, 255, 0.06);
      border-color: rgba(255, 255, 255, 0.1);

      &:hover {
        border-color: rgba(255, 255, 255, 0.18);
      }
    }
  }

  :global(.ant-input) {
    font-size: 15px;
  }

  :global(.ant-form-item-explain-error) {
    font-size: 13px;
    padding-top: 4px;
  }
}

.actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.forgotLink {
  font-size: 14px;
  color: #006AFF;
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  transition: color 200ms;

  &:hover {
    color: #0056CC;
  }
}

.submitBtn {
  width: 100%;
  height: 46px;
  font-size: 16px;
  border-radius: 10px;

  :global(.ant-btn-primary) {
    background: #006AFF;
    border-color: #006AFF;
    box-shadow: 0 2px 8px rgba(0, 106, 255, 0.25);
    transition: all 200ms;

    &:hover {
      background: #0056CC !important;
      border-color: #0056CC !important;
      transform: translateY(-1px);
      box-shadow: 0 4px 16px rgba(0, 106, 255, 0.35);
    }

    &:active {
      background: #004299 !important;
      transform: translateY(0) scale(0.985);
      box-shadow: 0 1px 4px rgba(0, 106, 255, 0.2);
    }
  }
}

/* Responsive */
@media (max-width: 768px) {
  .card {
    width: 100%;
    max-width: 420px;
    padding: 36px 28px;
    border-radius: 18px;
  }
}
```

- [ ] **Step 2: Write LoginForm.tsx**

```typescript
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
          <a className={styles.forgotLink}>忘记密码</a>
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
```

- [ ] **Step 3: Verify tsc compiles**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | head -10
```

Expected: zero errors (LoginPage still imports old thing — expected, fixed in Task 5).

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/login/components/LoginForm.tsx src/pages/login/components/LoginForm.module.less
git commit -m "feat: add LoginForm component with glassmorphism"
```

---

### Task 5: Rewrite `LoginPage` as left-right split layout

**Files:**
- Rewrite: `frontend/src/pages/login/LoginPage.tsx`
- Rewrite: `frontend/src/pages/login/LoginPage.module.less`

**Context:** The old LoginPage is replaced by a layout container that composes `LoginBackground`, `LoginBrandPanel`, and `LoginForm`.

- [ ] **Step 1: Write LoginPage.module.less**

```less
.page {
  display: flex;
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}

/* Left brand panel */
.left {
  position: relative;
  flex: 0 0 55%;
  display: flex;
  align-items: center;
  background: #F0F4FF;
  overflow: hidden;

  :global([data-theme="dark"]) & {
    background: #0A1628;
  }

  @media (max-width: 768px) {
    display: none;
  }

  @media (min-width: 769px) and (max-width: 1023px) {
    flex: 0 0 45%;
  }
}

.gridTexture {
  position: absolute;
  inset: 0;
  opacity: 0.04;
  background-image:
    linear-gradient(rgba(0, 0, 0, 0.1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.1) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
}

/* Right login panel */
.right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F5F7FA;
  position: relative;
  padding: 40px;

  :global([data-theme="dark"]) & {
    background: #0F172A;
  }

  @media (max-width: 768px) {
    padding: 20px;
  }
}

/* Theme toggle */
.themeToggle {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 10;
}

/* Card enter animation */
.rightEnter {
  animation: fadeInUp 600ms ease-out both;

  @media (prefers-reduced-motion: reduce) {
    animation: none;
    opacity: 1;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

- [ ] **Step 2: Write LoginPage.tsx**

```typescript
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
```

- [ ] **Step 3: Verify full toolchain**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npx eslint . && npm run build 2>&1 | tail -3
```

Expected: zero errors, build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/login/LoginPage.tsx src/pages/login/LoginPage.module.less
git commit -m "feat: rewrite LoginPage with left-right split glassmorphism layout"
```

---

### Task 6: Update smoke test

**Files:**
- Modify: `frontend/tests/App.test.tsx`

**Context:** The login page text changed — "媒体处理平台" is now in the brand panel (only visible on desktop). The test needs to check for the login form subtitle instead.

- [ ] **Step 1: Update test assertions**

Read `tests/App.test.tsx`. Change the unauthenticated test assertion from `screen.getByText(/媒体处理平台/i)` to `screen.getByText(/欢迎回来/i)` (the login form title visible on all screen sizes).

The first test should check for the login form element:
```typescript
  it('redirects unauthenticated user to login page', async () => {
    renderApp('/')

    await waitFor(() => {
      expect(screen.getByText(/欢迎回来/i)).toBeInTheDocument()
      expect(screen.getByText(/请登录您的账户以继续/i)).toBeInTheDocument()
    })
  })
```

Keep the authenticated test unchanged.

- [ ] **Step 2: Run tests**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && ./node_modules/.bin/vitest run
```

Expected: 2 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f tests/App.test.tsx
git commit -m "test: update login page assertions for redesigned page"
```

---

### Task 7: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Run full verification**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
./node_modules/.bin/tsc -b && echo "✅ TSC"
./node_modules/.bin/eslint . && echo "✅ LINT"
npm run build && echo "✅ BUILD"
./node_modules/.bin/vitest run && echo "✅ TEST"
```

Expected: All four pass.

- [ ] **Step 2: Commit any fixes**
