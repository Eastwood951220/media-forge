# Theme Transition CSS Origin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every theme switch reveal from the theme toggle area on the first rendered View Transition frame.

**Architecture:** Move the root reveal from post-`transition.ready` Web Animations API calls to CSS keyframes driven by CSS variables prepared before `document.startViewTransition()`. `ThemeModeToggle` passes the clicked button into the hook, while the hook falls back to a fixed upper-right point when no trigger element is available.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, React Testing Library, CSS View Transitions, `@theme-toggles/react`.

## Global Constraints

- Do not redesign the login page or application shell.
- Do not change the persisted theme store model.
- Do not replace `@theme-toggles/react`.
- Do not change crawler task behavior.
- Use CSS-driven View Transition animation for `::view-transition-new(root)`.
- Prepare transition CSS variables before calling `document.startViewTransition()`.
- If View Transition API is unavailable or reduced motion is requested, toggle immediately without animation.
- Manual Chrome verification must include a full refresh followed by the first light-to-dark toggle.

---

## File Structure

- `frontend/src/hooks/useThemeViewTransition/index.ts`
  - Owns feature detection, transition locking, origin/radius calculation, CSS variable setup, theme state mutation, wait/cleanup.
- `frontend/src/hooks/useThemeViewTransition/types.ts`
  - Defines the local View Transition shape used by tests and implementation.
- `frontend/src/components/ThemeModeToggle/index.tsx`
  - Passes the actual clicked toggle button to `runTransition`.
- `frontend/src/styles/view-transition.css`
  - Owns root View Transition pseudo-element animation and default animation overrides.
- `frontend/src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx`
  - Recreate or update focused hook tests.
- `frontend/src/components/ThemeModeToggle/ThemeModeToggle.test.tsx`
  - Recreate or update focused component tests.

---

### Task 1: Recreate Failing Hook Tests For CSS-Prepared Origin

**Files:**
- Create/Modify: `frontend/src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx`
- Read: `frontend/src/hooks/useThemeViewTransition/index.ts`
- Read: `frontend/src/hooks/useThemeViewTransition/types.ts`

**Interfaces:**
- Consumes: `useThemeViewTransition({ toggleTheme, duration?, easing? })`
- Produces test requirements for:
  - `runTransition(originEl?: HTMLElement | null): Promise<void>`
  - pre-`startViewTransition` CSS variables:
    - `--theme-transition-x`
    - `--theme-transition-y`
    - `--theme-transition-radius`
    - `--theme-transition-duration`
    - `--theme-transition-easing`

- [ ] **Step 1: Recreate the hook test file if it is deleted**

Write this complete focused test file:

```tsx
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useThemeViewTransition } from './index'
import { useThemeStore } from '@/stores/useThemeStore'

type MockViewTransition = ReturnType<typeof vi.fn>

function mockViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  })
  Object.defineProperty(window, 'innerHeight', {
    configurable: true,
    writable: true,
    value: height,
  })
}

function mockButtonRect(element: HTMLElement, rect: Pick<DOMRect, 'top' | 'left' | 'width' | 'height'>) {
  element.getBoundingClientRect = () => ({
    x: rect.left,
    y: rect.top,
    top: rect.top,
    left: rect.left,
    right: rect.left + rect.width,
    bottom: rect.top + rect.height,
    width: rect.width,
    height: rect.height,
    toJSON: () => ({}),
  })
}

describe('useThemeViewTransition', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.startViewTransition = undefined as unknown as Document['startViewTransition']
    document.documentElement.dataset.theme = 'light'
    document.documentElement.className = ''
    document.documentElement.removeAttribute('style')
    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)' ? false : false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    mockViewport(2000, 1000)
  })

  it('prepares button-centered CSS variables before the first View Transition frame', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock
    let cssStatePreparedBeforeCallback = false
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = vi.fn((callback: () => void) => {
      cssStatePreparedBeforeCallback =
        document.documentElement.classList.contains('theme-transition-active') &&
        document.documentElement.style.getPropertyValue('--theme-transition-x') === '1920px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-y') === '92px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-radius') === '2123.879469273151px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-duration') === '280ms' &&
        document.documentElement.style.getPropertyValue('--theme-transition-easing') === 'linear'
      callback()
      return {
        ready: Promise.resolve(),
        finished: Promise.resolve(),
        updateCallbackDone: Promise.resolve(),
        skipTransition: () => {},
        types: new Set<string>(),
      }
    })

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))
    const trigger = document.createElement('button')
    mockButtonRect(trigger, { top: 72, left: 1900, width: 40, height: 40 })

    await act(async () => {
      await result.current.runTransition(trigger)
    })

    expect((document as unknown as { startViewTransition: MockViewTransition }).startViewTransition).toHaveBeenCalledTimes(1)
    expect(useThemeStore.getState().darkMode).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(cssStatePreparedBeforeCallback).toBe(true)
    expect(animateMock).not.toHaveBeenCalled()
    expect(document.documentElement).not.toHaveClass('theme-transition-active')
    expect(document.documentElement.style.getPropertyValue('--theme-transition-x')).toBe('')
  })

  it('falls back to the upper-right visible point when no trigger is supplied', async () => {
    let cssStatePreparedBeforeCallback = false
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = vi.fn((callback: () => void) => {
      cssStatePreparedBeforeCallback =
        document.documentElement.style.getPropertyValue('--theme-transition-x') === '1956px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-y') === '44px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-radius') === '2177.1247093356874px'
      callback()
      return {
        ready: Promise.resolve(),
        finished: Promise.resolve(),
        updateCallbackDone: Promise.resolve(),
        skipTransition: () => {},
        types: new Set<string>(),
      }
    })

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))

    await act(async () => {
      await result.current.runTransition()
    })

    expect(cssStatePreparedBeforeCallback).toBe(true)
    expect(useThemeStore.getState().darkMode).toBe(true)
  })

  it('switches immediately without root animation when reduced motion is requested', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock
    ;(window.matchMedia as MockViewTransition).mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return { ready: Promise.resolve(), finished: Promise.resolve(), updateCallbackDone: Promise.resolve(), skipTransition: () => {}, types: new Set<string>() }
    })

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))
    result.current.triggerRef.current = document.createElement('button') as never

    await act(async () => {
      await result.current.runTransition()
    })

    expect(useThemeStore.getState().darkMode).toBe(true)
    expect((document as unknown as { startViewTransition: MockViewTransition }).startViewTransition).not.toHaveBeenCalled()
    expect(animateMock).not.toHaveBeenCalled()
  })

  it('switches immediately when View Transition API is unavailable', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))
    result.current.triggerRef.current = document.createElement('button') as never

    await act(async () => {
      await result.current.runTransition()
    })

    await waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true)
    })
    expect(animateMock).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the hook test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx
```

Expected: FAIL before implementation because `runTransition` does not accept the origin element, does not prepare CSS variables before `startViewTransition`, and still calls `document.documentElement.animate`.

- [ ] **Step 3: Commit the failing test**

```bash
git add frontend/src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx
git commit -m "test: cover css-prepared theme transition origin"
```

---

### Task 2: Recreate Failing Component Test For Clicked Button Origin

**Files:**
- Create/Modify: `frontend/src/components/ThemeModeToggle/ThemeModeToggle.test.tsx`
- Read: `frontend/src/components/ThemeModeToggle/index.tsx`

**Interfaces:**
- Consumes: `ThemeModeToggle`
- Produces test requirement that `ThemeModeToggle` calls `runTransition(event.currentTarget)` through real user click behavior.

- [ ] **Step 1: Recreate the component test file if it is deleted**

Write this complete focused test file:

```tsx
// @ts-nocheck - test file, uses require('react') inside hoisted mock factory
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeModeToggle } from './index'
import { useThemeStore } from '@/stores/useThemeStore'

vi.mock('@theme-toggles/react/styles/classic.css', () => ({}))

vi.mock('@theme-toggles/react', () => {
  const React = require('react')
  const Classic = React.forwardRef<HTMLButtonElement, Record<string, unknown>>(
    (props, ref) => {
      const className = props.className
      const ariaLabel = props['aria-label']
      const onClick = props.onClick
      return React.createElement('button', {
        className,
        'aria-label': ariaLabel,
        onClick,
        ref,
        type: 'button',
        title: props.title,
      })
    },
  )
  Classic.displayName = 'Classic'
  return { Classic }
})

describe('ThemeModeToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.startViewTransition = undefined as unknown as Document['startViewTransition']
    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
    document.documentElement.dataset.theme = 'light'
    document.documentElement.className = ''
    document.documentElement.removeAttribute('style')
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)' ? false : false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 2000,
    })
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      writable: true,
      value: 1000,
    })
  })

  it('renders an accessible animated theme button instead of an Ant Design switch', () => {
    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    expect(button).toBeInTheDocument()
    expect(screen.queryByRole('switch', { name: '切换明暗模式' })).not.toBeInTheDocument()
    expect(button).toHaveClass('theme-toggle')
    expect(button).not.toHaveClass('ant-switch')
  })

  it('uses store state as the toggled visual state and toggles theme on click', async () => {
    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    await userEvent.click(button)

    await waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true)
    })
    expect(button).not.toBeDisabled()
  })

  it('keeps login label copy while using the animated button', () => {
    useThemeStore.setState({ mode: 'dark', darkMode: true, primaryColor: '#006AFF' })

    render(<ThemeModeToggle variant="login" />)

    expect(screen.getByText('深色模式')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '切换明暗模式' })).toHaveClass('theme-toggle')
  })

  it('prepares CSS origin from the clicked theme button before the first transition frame', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock
    let cssStatePreparedBeforeCallback = false
    document.startViewTransition = vi.fn((callback: () => void) => {
      cssStatePreparedBeforeCallback =
        document.documentElement.classList.contains('theme-transition-active') &&
        document.documentElement.style.getPropertyValue('--theme-transition-x') === '1920px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-y') === '92px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-radius') === '2123.879469273151px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-duration') === '280ms' &&
        document.documentElement.style.getPropertyValue('--theme-transition-easing') === 'linear'
      callback()
      return {
        ready: Promise.resolve(),
        finished: Promise.resolve(),
        updateCallbackDone: Promise.resolve(),
        skipTransition: () => {},
        types: new Set<string>(),
      }
    }) as unknown as Document['startViewTransition']

    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    button.getBoundingClientRect = () => ({
      x: 1900,
      y: 72,
      top: 72,
      left: 1900,
      right: 1940,
      bottom: 112,
      width: 40,
      height: 40,
      toJSON: () => ({}),
    })

    await userEvent.click(button)

    await waitFor(() => {
      expect(cssStatePreparedBeforeCallback).toBe(true)
    })
    expect(animateMock).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the component test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/components/ThemeModeToggle/ThemeModeToggle.test.tsx
```

Expected: FAIL before implementation because the component still calls `runTransition()` without passing `event.currentTarget`, or because the hook still starts WAAPI after `transition.ready`.

- [ ] **Step 3: Commit the failing component test**

```bash
git add frontend/src/components/ThemeModeToggle/ThemeModeToggle.test.tsx
git commit -m "test: cover clicked theme toggle transition origin"
```

---

### Task 3: Move Theme Reveal Setup Into The Hook Before View Transition Creation

**Files:**
- Modify: `frontend/src/hooks/useThemeViewTransition/index.ts`
- Modify: `frontend/src/hooks/useThemeViewTransition/types.ts`
- Test: `frontend/src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx`

**Interfaces:**
- Produces: `runTransition(originEl?: HTMLElement | null): Promise<void>`
- Produces: CSS variable preparation and cleanup helpers kept local to the hook module.
- Consumes: `ViewTransitionLike.finished?: Promise<void>`

- [ ] **Step 1: Update local View Transition type**

In `frontend/src/hooks/useThemeViewTransition/types.ts`, use:

```ts
export type ViewTransitionLike = {
  ready: Promise<void>
  finished?: Promise<void>
  skipTransition?: () => void
}

export type StartViewTransition = (callback: () => void | Promise<void>) => ViewTransitionLike

export type UseThemeViewTransitionOptions = {
  duration?: number
  easing?: string
  toggleTheme: () => void
}
```

- [ ] **Step 2: Replace the hook implementation**

In `frontend/src/hooks/useThemeViewTransition/index.ts`, use:

```ts
import { useCallback, useRef } from 'react'
import { flushSync } from 'react-dom'
import { useThemeStore } from '@/stores/useThemeStore'
import type { StartViewTransition, UseThemeViewTransitionOptions } from './types'

const DEFAULT_DURATION = 280
const DEFAULT_EASING = 'linear'
const TRANSITION_CLASS = 'theme-transition-active'
const TRANSITION_X = '--theme-transition-x'
const TRANSITION_Y = '--theme-transition-y'
const TRANSITION_RADIUS = '--theme-transition-radius'
const TRANSITION_DURATION = '--theme-transition-duration'
const TRANSITION_EASING = '--theme-transition-easing'
const TOP_RIGHT_ORIGIN_INSET = 44

function shouldSkipTransition(): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return true
  }
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function getStartViewTransition(): StartViewTransition | null {
  if (typeof document === 'undefined') {
    return null
  }
  const doc = document as Document & { startViewTransition?: StartViewTransition }
  const fn = doc.startViewTransition
  return typeof fn === 'function' ? fn.bind(doc) : null
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function getTransitionOrigin(originEl?: HTMLElement | null) {
  if (originEl) {
    const { top, left, width, height } = originEl.getBoundingClientRect()
    return {
      x: left + width / 2,
      y: top + height / 2,
    }
  }

  return {
    x: Math.max(window.innerWidth - TOP_RIGHT_ORIGIN_INSET, 0),
    y: TOP_RIGHT_ORIGIN_INSET,
  }
}

function getCoveringRadius(x: number, y: number) {
  return Math.max(
    Math.hypot(x, y),
    Math.hypot(window.innerWidth - x, y),
    Math.hypot(x, window.innerHeight - y),
    Math.hypot(window.innerWidth - x, window.innerHeight - y),
  )
}

function prepareTransition(root: HTMLElement, originEl: HTMLElement | null, duration: number, easing: string) {
  const { x, y } = getTransitionOrigin(originEl)
  const maxRadius = getCoveringRadius(x, y)

  root.style.setProperty(TRANSITION_X, `${x}px`)
  root.style.setProperty(TRANSITION_Y, `${y}px`)
  root.style.setProperty(TRANSITION_RADIUS, `${maxRadius}px`)
  root.style.setProperty(TRANSITION_DURATION, `${duration}ms`)
  root.style.setProperty(TRANSITION_EASING, easing)
  root.classList.add(TRANSITION_CLASS)
}

function clearPreparedTransition(root: HTMLElement) {
  root.classList.remove(TRANSITION_CLASS)
  root.style.removeProperty(TRANSITION_X)
  root.style.removeProperty(TRANSITION_Y)
  root.style.removeProperty(TRANSITION_RADIUS)
  root.style.removeProperty(TRANSITION_DURATION)
  root.style.removeProperty(TRANSITION_EASING)
}

export function useThemeViewTransition({
  duration = DEFAULT_DURATION,
  easing = DEFAULT_EASING,
  toggleTheme,
}: UseThemeViewTransitionOptions) {
  const transitionLockRef = useRef(false)
  const triggerRef = useRef<HTMLElement | null>(null)

  const runTransition = useCallback(async (originEl?: HTMLElement | null) => {
    if (transitionLockRef.current) {
      return
    }

    const startViewTransition = getStartViewTransition()

    if (!startViewTransition || shouldSkipTransition()) {
      toggleTheme()
      return
    }

    transitionLockRef.current = true

    const root = document.documentElement
    prepareTransition(root, originEl ?? triggerRef.current, duration, easing)

    try {
      const transition = startViewTransition(() => {
        const nextDark = !useThemeStore.getState().darkMode
        root.dataset.theme = nextDark ? 'dark' : 'light'
        root.classList.toggle('dark', nextDark)
        flushSync(() => {
          toggleTheme()
        })
      })

      await transition.ready
      await (transition.finished ?? wait(duration))
    } catch (error) {
      console.warn('[theme transition] failed:', error)
    } finally {
      clearPreparedTransition(root)
      transitionLockRef.current = false
    }
  }, [duration, easing, toggleTheme])

  return { runTransition, triggerRef }
}

export type { UseThemeViewTransitionOptions, ViewTransitionLike, StartViewTransition } from './types'
```

- [ ] **Step 3: Run hook test**

Run:

```bash
cd frontend
npm test -- src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Commit hook implementation**

```bash
git add frontend/src/hooks/useThemeViewTransition/index.ts frontend/src/hooks/useThemeViewTransition/types.ts frontend/src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx
git commit -m "fix: prepare theme transition origin before first frame"
```

---

### Task 4: Wire The Clicked Button Into ThemeModeToggle

**Files:**
- Modify: `frontend/src/components/ThemeModeToggle/index.tsx`
- Test: `frontend/src/components/ThemeModeToggle/ThemeModeToggle.test.tsx`

**Interfaces:**
- Consumes: `runTransition(originEl?: HTMLElement | null): Promise<void>`
- Produces: click handler that passes `event.currentTarget`.

- [ ] **Step 1: Update the click handler**

In `frontend/src/components/ThemeModeToggle/index.tsx`, keep the wrapper ref as fallback and update only the `Classic` click handler:

```tsx
<Classic
  aria-label="切换明暗模式"
  className={clsx('theme-toggle', styles.toggleButton, styles[size])}
  duration={450}
  onClick={(event) => {
    void runTransition(event.currentTarget)
  }}
/>
```

- [ ] **Step 2: Run component test**

Run:

```bash
cd frontend
npm test -- src/components/ThemeModeToggle/ThemeModeToggle.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Commit component implementation**

```bash
git add frontend/src/components/ThemeModeToggle/index.tsx frontend/src/components/ThemeModeToggle/ThemeModeToggle.test.tsx
git commit -m "fix: anchor theme transition to clicked button"
```

---

### Task 5: Move Root Reveal Animation To CSS

**Files:**
- Modify: `frontend/src/styles/view-transition.css`
- Test: `frontend/src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx`
- Test: `frontend/src/components/ThemeModeToggle/ThemeModeToggle.test.tsx`

**Interfaces:**
- Consumes CSS variables prepared by the hook:
  - `--theme-transition-x`
  - `--theme-transition-y`
  - `--theme-transition-radius`
  - `--theme-transition-duration`
  - `--theme-transition-easing`

- [ ] **Step 1: Replace View Transition CSS**

Use:

```css
/*
 * Override the browser's default View Transition cross-fade for root.
 * The page reveal is controlled by CSS variables prepared before
 * document.startViewTransition() is called.
 */

::view-transition,
::view-transition-group(root),
::view-transition-image-pair(root),
::view-transition-old(root) {
  animation: none !important;
}

::view-transition-old(root),
::view-transition-new(root) {
  mix-blend-mode: normal;
}

::view-transition-new(root) {
  animation: theme-root-reveal var(--theme-transition-duration, 280ms) var(--theme-transition-easing, linear) both !important;
}

@keyframes theme-root-reveal {
  from {
    clip-path: circle(0px at var(--theme-transition-x, 100vw) var(--theme-transition-y, 0px));
  }

  to {
    clip-path: circle(var(--theme-transition-radius, 150vmax) at var(--theme-transition-x, 100vw) var(--theme-transition-y, 0px));
  }
}

@media (prefers-reduced-motion: reduce) {
  ::view-transition,
  ::view-transition-group(root),
  ::view-transition-image-pair(root),
  ::view-transition-old(root),
  ::view-transition-new(root) {
    animation: none !important;
  }
}
```

- [ ] **Step 2: Run focused test suite**

Run:

```bash
cd frontend
npm test -- src/components/ThemeModeToggle/ThemeModeToggle.test.tsx src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx
```

Expected: PASS, 8 tests total if Task 1 and Task 2 files are used exactly.

- [ ] **Step 3: Commit CSS implementation**

```bash
git add frontend/src/styles/view-transition.css frontend/src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx frontend/src/components/ThemeModeToggle/ThemeModeToggle.test.tsx
git commit -m "fix: drive theme reveal with css view transition"
```

---

### Task 6: Build And Real Chrome Verification

**Files:**
- Verify only; no source changes expected.

**Interfaces:**
- Consumes the completed implementation from Tasks 1-5.
- Produces browser evidence that the first rendered transition frame is anchored to the upper-right toggle area.

- [ ] **Step 1: Run production build**

Run:

```bash
cd frontend
npm run build
```

Expected: exit 0. Existing Vite chunk size warnings are acceptable.

- [ ] **Step 2: Open the login page in Chrome**

Run:

```bash
open -a 'Google Chrome' 'http://localhost:18643/login'
```

Expected: Chrome opens the login page.

- [ ] **Step 3: Execute real-browser diagnostic**

Use Chrome DevTools console or an automation script to verify this after a full page refresh and first click:

```js
document.getAnimations({ subtree: true })
  .filter((animation) => animation.effect?.target === document.documentElement)
  .map((animation) => ({
    currentTime: animation.currentTime,
    timing: animation.effect?.getTiming?.(),
    keyframes: animation.effect?.getKeyframes?.(),
  }))
```

Expected first root animation keyframe:

```js
{
  clipPath: 'circle(0px at <button-center-x>px <button-center-y>px)'
}
```

For the login page at a `1600x900` viewport, the expected button center is approximately `1556px 46px` when the button is positioned at `right: 24px` with a `40px` button.

- [ ] **Step 4: Manually verify both directions**

Manual checks:

- Refresh `/login`, click once from light to dark. The reveal starts at the upper-right theme toggle area.
- Click again from dark to light. The reveal starts at the same area.
- The animation progresses linearly without a visible end pause or sudden jump.

- [ ] **Step 5: Commit verification note only if source files changed**

If no source files changed during verification, do not create a commit.

If a small source correction was needed during verification:

```bash
git add frontend/src/hooks/useThemeViewTransition/index.ts frontend/src/styles/view-transition.css frontend/src/components/ThemeModeToggle/index.tsx
git commit -m "fix: verify theme transition in chrome"
```

---

## Self-Review

Spec coverage:

- CSS variables prepared before `startViewTransition`: Task 1 and Task 3.
- CSS owns root reveal: Task 5.
- Trigger button center when available: Task 1, Task 2, Task 4.
- Upper-right fallback when trigger unavailable: Task 1 and Task 3.
- Reduced motion and missing API immediate toggle: Task 1 and Task 3.
- Real Chrome first-toggle verification: Task 6.

Placeholder scan:

- No deferred implementation notes remain.

Type consistency:

- `runTransition(originEl?: HTMLElement | null)` is defined in Task 3 and consumed in Task 4.
- `ViewTransitionLike.finished?: Promise<void>` is defined in Task 3 and used by the hook implementation.
- CSS variable names are consistent across Task 1, Task 3, and Task 5.
