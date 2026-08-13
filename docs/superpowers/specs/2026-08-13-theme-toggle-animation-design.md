# Theme Toggle Animation Design

## Context

Media Forge is a React 19 + Vite SPA using Ant Design 6 for UI components and
theme tokens. Theme state is stored in `useThemeStore`, and the root
`ConfigProvider` switches between `theme.defaultAlgorithm` and
`theme.darkAlgorithm`.

The app already has a custom `useThemeViewTransition` hook that uses the native
View Transition API for a circular reveal from the theme toggle position. The
current `ThemeModeToggle` still renders an Ant Design `Switch`, which has a
functional switch interaction but limited icon animation. A recent fix removed
`loading` and `disabled` from the switch during transitions because that state
made the theme change feel paused.

The desired next step is to use `@theme-toggles/react` for a smoother animated
toggle button while keeping and tuning the page-level View Transition effect.

## Goals

- Replace the Ant Design `Switch` inside `ThemeModeToggle` with an animated
  toggle from `@theme-toggles/react`.
- Use `@theme-toggles/react@5.0.0-rc.0`, which declares React 19 peer support.
- Use the `Classic` toggle style.
- Keep `useThemeStore` as the source of truth for light/dark mode.
- Keep Ant Design theme switching through `ConfigProvider.theme.algorithm`.
- Keep the native View Transition API for the whole-page circular reveal.
- Tune the whole-page transition to feel smoother and more responsive.
- Preserve accessibility: a named button, keyboard activation, focus styles,
  and reduced-motion behavior.
- Avoid heavy animation libraries such as Framer Motion or GSAP for this
  change.

## Non-Goals

- Do not replace the theme store.
- Do not change route structure or page layout.
- Do not redesign the app color system or Ant Design token mapping.
- Do not add a system-theme preference mode.
- Do not animate every page element individually.
- Do not force motion for users who request reduced motion.

## Dependency Findings

`@theme-toggles/react` provides animated React theme-toggle components. The
current npm latest version found during design exploration is `5.0.0-rc.0`.

Relevant package characteristics:

- Peer dependency: `react: ^19.0.0`
- Dependency: `clsx`
- Component props include `toggled`, `onToggle`, `duration`, `reversed`,
  `forceMotion`, and button attributes.
- CSS drives the animation through SVG element transitions such as `transform`,
  `opacity`, and SVG path changes.
- The package CSS respects `prefers-reduced-motion: reduce` when `forceMotion`
  is not enabled.

This matches the current project because the app already uses React 19 and
already has `clsx` installed.

## UI/UX Guidance Applied

This design follows animation guidance from `ui-ux-pro-max`:

- Respect `prefers-reduced-motion`.
- Animate one or two key elements, not the whole interface element-by-element.
- Keep UI transitions responsive; avoid long transitions that feel sluggish.
- Prefer transform and opacity for animation performance.
- Avoid loading indicators for short non-network interactions.

## Proposed Approach

Use a two-layer animation model:

1. `@theme-toggles/react` animates only the button's sun/moon microinteraction.
2. `useThemeViewTransition` animates the whole page's theme reveal.

This keeps responsibilities clear. The toggle component provides polished icon
motion, while the existing hook continues to coordinate app-wide theme state,
HTML theme attributes, Ant Design token recalculation, and View Transition
timing.

## Components

`ThemeModeToggle`

- Import the chosen toggle component from `@theme-toggles/react`.
- Import the matching package CSS for the chosen style.
- Render the toggle as a button with `aria-label="切换明暗模式"`.
- Pass `toggled={darkMode}` so the button reflects store state.
- Use `onToggle={() => void runTransition()}` to start the page transition.
- Pass `duration={450}` for the toggle icon animation.
- Do not pass `forceMotion`.
- Do not render Ant Design `Switch`.
- Keep the existing `variant` and `size` props, mapping them to CSS classes
  rather than Ant Design switch sizes.
- Keep the login label text: `深色模式` or `浅色模式`.

`useThemeViewTransition`

- Continue exposing `runTransition` and `triggerRef`.
- Continue using `transitionLockRef` to ignore repeated clicks while a page
  transition is active.
- Keep reduced-motion detection and direct fallback switching.
- Keep `flushSync` around `toggleTheme()` inside `startViewTransition`.
- Continue setting `document.documentElement.dataset.theme` inside the
  transition callback so CSS variables update in the captured new state.
- Tune default duration to `280ms`.
- Tune default easing to `cubic-bezier(0.2, 0, 0, 1)` for a smoother reveal.
- Animate only `::view-transition-new(root)` with circular `clipPath`.
- Remove `theme-transition-active` in the `finally` block.

`view-transition.css`

- Keep default View Transition cross-fade disabled for root pseudo-elements.
- Keep the CSS narrowly scoped to root view transitions.
- Add or preserve reduced-motion-safe behavior so CSS does not force extra
  animation when the hook skips it.

`ThemeModeToggle` styles

- Keep the wrapper inline-flex alignment.
- Add a button class for the theme-toggles component.
- Provide stable hit area:
  - header variant: at least 40 px practical target
  - login variant: at least 44 px target when paired with text
- Use current text color so the SVG adapts to light/dark header contexts.
- Preserve visible focus outline.

## Interaction Flow

1. User activates the theme toggle with mouse or keyboard.
2. The toggle component starts its SVG animation immediately.
3. `runTransition` checks the internal lock.
4. If the browser does not support View Transition or reduced motion is active,
   it directly toggles the Zustand theme state.
5. If View Transition is available:
   - start a view transition
   - set the next `data-theme` value on `<html>`
   - synchronously toggle the Zustand theme state
   - compute the reveal origin from `triggerRef`
   - animate `::view-transition-new(root)` from a zero-radius circle to a circle
     large enough to cover the viewport
6. When the animation finishes or fails, the lock is released.

The button animation may last slightly longer than the page reveal. The page
should finish in 280 ms, while the button should finish in 450 ms. This
keeps the application feeling responsive while allowing the icon to complete a
more expressive sun/moon transition.

## Error Handling

- If View Transition setup throws, catch the error, log a warning, remove the
  transition class, and release the lock.
- If the browser lacks View Transition support, switch theme immediately.
- If package import or CSS fails during implementation, fail at build time
  rather than silently falling back to a different visual control.

## Testing

Add or update focused tests:

- `ThemeModeToggle` renders an accessible button named `切换明暗模式`.
- `ThemeModeToggle` no longer renders an Ant Design switch.
- Clicking the toggle calls the theme transition path and updates checked visual
  state through `toggled`.
- No `ant-switch-loading` or `ant-switch-disabled` classes appear.
- `useThemeViewTransition` calls `document.startViewTransition` when supported.
- The hook calls `root.animate` for `::view-transition-new(root)` with the tuned
  duration and easing.
- Reduced-motion path toggles theme without calling `root.animate`.
- Unsupported-browser path toggles theme without calling
  `document.startViewTransition`.

Verification commands:

```bash
cd frontend && npm test -- src/components/ThemeModeToggle src/hooks/useThemeViewTransition
cd frontend && npm run build
```

The implementation should account for any unrelated dirty-worktree files before
claiming the build result.

## Acceptance Criteria

- Header and login theme toggles use `@theme-toggles/react`.
- The chosen toggle style is `Classic`.
- Toggle animation begins immediately on click and does not enter a loading or
  disabled visual state.
- Whole-page theme switching remains anchored at the toggle position.
- Page reveal feels smoother than the current implementation, using a 280 ms
  duration.
- Reduced-motion users get an immediate theme change without forced animation.
- Ant Design theme tokens still update through `ConfigProvider`.
- No heavy animation dependency is added.
