# Theme Transition Button Origin Smoothness Fix Design

## Problem

The frontend light/dark theme transition still expands from the top-middle or top edge area instead of the theme toggle button. The attached video also shows the animation visually stopping near the end, then completing abruptly.

Current code evidence:

- `ThemeModeToggle` renders the animated toggle inside a wrapper and currently keeps the transition `triggerRef` on that wrapper.
- `useThemeViewTransition` currently hard-codes the origin:

```ts
const x = window.innerWidth
const y = 0
```

- `useThemeViewTransition` currently uses:

```ts
const DEFAULT_DURATION = 5000
```

- The previous design kept `cubic-bezier(0.2, 0, 0, 1)`, which is an ease-out curve. That pacing intentionally slows near the end and can still read as a tail pause.

That combination explains both symptoms. The reveal is not anchored to the actual toggle button, and a 5-second clip-path expansion leaves a long tail where most of the screen is already covered but the animation is still running. The final fix must also use linear radial pacing so the circle edge does not visibly speed up, slow down, pause, or snap.

The current working tree contains many unrelated crawler/run-list changes. This fix must not touch or revert those files.

## Decision

Use the real theme button center as the reveal origin and restore a short UI transition duration.

The selected behavior is:

- The reveal starts from the visual center of the theme toggle button.
- The same logic works on the authenticated header and the login page's fixed top-right toggle.
- The transition duration is `280ms`.
- The easing is exactly `linear`.
- The reveal radius covers the whole viewport from the button center.
- Reduced-motion behavior remains immediate and non-animated.

## User-Facing Behavior

- Clicking the theme toggle on the login page expands the new theme from the button in the top-right corner.
- Clicking the theme toggle in the app header expands the new theme from that header button.
- The reveal no longer starts from the top-middle area.
- The reveal edge moves at a constant radial pace from start to finish.
- The reveal does not suddenly accelerate, pause near completion, or snap at the end.
- Repeated clicks during an active reveal do not queue multiple transitions.
- If the browser does not support the View Transition API, the theme still switches immediately.

## Architecture

### Button Ref Ownership

`ThemeModeToggle` will attach `triggerRef` to the actual `Classic` button instead of a wrapper element.

The wrapper remains only for layout and login label copy:

```tsx
<div className={`${styles.toggleWrap} ${styles[variant]} ${className ?? ''}`}>
  {variant === 'login' ? (
    <span className={styles.label}>
      {darkMode ? '深色模式' : '浅色模式'}
    </span>
  ) : null}
  <Classic
    ref={triggerRef}
    aria-label="切换明暗模式"
    className={clsx('theme-toggle', styles.toggleButton, styles[size])}
    duration={450}
    onClick={() => {
      void runTransition()
    }}
  />
</div>
```

The hook ref type becomes:

```ts
const triggerRef = useRef<HTMLButtonElement | null>(null)
```

This makes the animation origin track the actual click target rather than a parent box or a hard-coded viewport coordinate.

### Reveal Origin Calculation

`useThemeViewTransition` will compute the origin from the button rectangle:

```ts
const { top, left, width, height } = triggerEl.getBoundingClientRect()
const x = left + width / 2
const y = top + height / 2
```

The maximum radius will be the largest distance from that point to the four viewport corners:

```ts
const maxRadius = Math.max(
  Math.hypot(x, y),
  Math.hypot(window.innerWidth - x, y),
  Math.hypot(x, window.innerHeight - y),
  Math.hypot(window.innerWidth - x, window.innerHeight - y),
)
```

This is more precise than assuming the farthest corner is always the bottom-left corner. It covers header and login layouts, all viewport sizes, and both left/right toggle positions.

### Duration And Completion

`DEFAULT_DURATION` will be:

```ts
const DEFAULT_DURATION = 280
```

`DEFAULT_EASING` will be:

```ts
const DEFAULT_EASING = 'linear'
```

Do not use an ease-out curve for the circular reveal. The animation must use linear timing so the clip-path radius expands at a constant rate. This is a deliberate exception to the usual UI preference for eased motion because the user-visible defect is non-linear pacing: the reveal appears to stop near the end, then finish abruptly.

The hook will keep awaiting `newAnim.finished`, but the lock duration is now short enough for a UI interaction. The `finally` block continues to remove `theme-transition-active` and release `transitionLockRef`.

The CSS override remains:

```css
::view-transition-old(root),
::view-transition-new(root) {
  animation: none !important;
}
```

That keeps the browser's default cross-fade out of the way while the hook controls the circular clip-path reveal.

## Error Handling And Fallbacks

- Missing button ref: switch theme immediately.
- Missing `document.startViewTransition`: switch theme immediately.
- `prefers-reduced-motion: reduce`: switch theme immediately and do not call `root.animate`.
- Animation error: keep the existing warning, remove `theme-transition-active`, and release the lock.

## Testing

Update focused tests:

- `useThemeViewTransition` uses the button rectangle center in `clipPath`.
- A button at `left: 1900, top: 72, width: 40, height: 40` produces origin `1920px 92px`.
- `useThemeViewTransition` does not use `window.innerWidth 0` as the origin.
- `useThemeViewTransition` uses `duration: 280`.
- `useThemeViewTransition` uses `easing: 'linear'`.
- `ThemeModeToggle` passes `triggerRef` to the actual `Classic` button.
- Reduced-motion and unsupported-browser fallbacks still skip `root.animate`.

Run:

```bash
cd frontend && npm test -- src/components/ThemeModeToggle/ThemeModeToggle.test.tsx src/hooks/useThemeViewTransition/useThemeViewTransition.test.tsx
cd frontend && npm run build
```

Manual verification at `http://localhost:18643`:

- Login page toggle starts from the top-right toggle button.
- App header toggle starts from the header toggle button.
- The circular reveal expands at a constant pace without sudden acceleration, a long tail pause, or an end snap.
- The toggle remains clickable after the reveal completes.

## Out Of Scope

- Crawler task changes.
- Run list changes.
- Storage task changes.
- Backend changes.
- Changing the theme store.
- Replacing `@theme-toggles/react`.
- Redesigning login or header layout.
