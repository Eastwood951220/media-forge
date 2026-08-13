# Theme Toggle Anchor And State Fix Design

## Problem

After adding `@theme-toggles/react`, the theme button has three visible issues:

- The icon keeps showing the sun instead of reflecting the current theme.
- The icon is not horizontally centered in the header control.
- The page-level View Transition reveal starts from the top center of the page instead of the theme button.

The current implementation renders `Classic` from `@theme-toggles/react`, but it does not give the library the dark-mode selector it expects. The installed `Classic` component uses CSS selectors under `.dark` to animate between sun and moon states, while the app currently syncs only `data-theme` on `<html>`. The transition hook also anchors its circle to the wrapper `div`; that wrapper can produce a misleading rectangle compared with the actual button.

## Decision

Use approach A:

- Keep `@theme-toggles/react` and the `Classic` button.
- Sync `html.dark` alongside the existing `html[data-theme="dark"]`.
- Anchor the page reveal to the actual button element, not the wrapper.
- Fix the button box so the SVG is visually centered.

This preserves the existing theme store, Ant Design theme algorithm, and View Transition API. It uses the installed package according to its real CSS behavior instead of reimplementing the icon animation.

## User-Facing Behavior

- In light mode, the button shows the sun.
- In dark mode, the button shows the moon.
- The button remains an accessible icon button named `切换明暗模式`.
- The icon sits centered in a fixed-size touch target.
- Clicking the button starts the reveal from the visual center of that same button.
- Reduced-motion users still get an immediate theme switch without page reveal animation.
- Repeated clicks during the reveal do not queue multiple conflicting transitions.

## Architecture

### Theme Synchronization

`App` remains responsible for syncing theme state to the document root. It will continue setting:

```ts
document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'
```

It will also toggle:

```ts
document.documentElement.classList.toggle('dark', darkMode)
```

No existing project styles use Tailwind `dark:` classes, so adding the root `.dark` class is scoped to consumers that explicitly expect it, including `@theme-toggles/react`.

### Transition Snapshot Synchronization

`useThemeViewTransition` currently sets `root.dataset.theme` inside the `startViewTransition` callback before flushing the store update. It must also toggle `root.classList` there. This keeps the View Transition old and new snapshots consistent with both the app CSS and the theme-toggle SVG CSS.

The hook keeps its existing ref lock. It should still return only:

```ts
{
  runTransition: () => Promise<void>
  triggerRef: React.RefObject<HTMLButtonElement | null>
}
```

The ref target changes from a wrapper `HTMLDivElement` to the actual button element.

### ThemeModeToggle Component

`ThemeModeToggle` keeps its public props:

```ts
type ThemeModeToggleProps = {
  className?: string
  variant?: 'header' | 'login'
  size?: 'small' | 'middle'
}
```

The wrapper remains for layout and login label text. The `Classic` button receives the hook ref directly. The component no longer relies on a hand-written `theme-toggle--toggled` class as the icon state source. The package CSS determines the sun or moon from the nearest `.dark` ancestor, which will be `<html>`.

The click path remains:

```text
Classic button click -> runTransition -> View Transition callback -> toggle theme store -> App effect confirms root theme classes
```

### Button Layout

The button gets a stable box:

- Header size: `40px` by `40px`.
- Small size: `36px` by `36px`.
- `display: inline-grid`.
- `place-items: center`.
- `line-height: 1`.
- SVG font size controlled by the size class.

This removes visual drift from inline SVG baseline behavior and from wrapper dimensions.

## Error Handling And Fallbacks

- If `document.startViewTransition` is unavailable, the hook toggles the theme immediately.
- If the trigger button ref is unavailable, the hook toggles the theme immediately.
- If `prefers-reduced-motion: reduce` matches, the hook toggles the theme immediately and does not run `root.animate`.
- If the reveal animation throws, the hook logs the existing warning, removes the active transition class, and releases the lock.

## Testing

Add or update focused tests for:

- `ThemeModeToggle` renders a named `button`, not an Ant Design `switch`.
- `ThemeModeToggle` passes the actual button as the transition trigger.
- The button is not loading or disabled during transition.
- Dark mode causes the root `.dark` class to exist and the toggle to receive the package's dark-state styling path.
- `useThemeViewTransition` computes the circle origin from the button rectangle.
- `useThemeViewTransition` toggles both `data-theme` and `.dark` inside the transition callback.
- Reduced-motion and unsupported-browser fallbacks do not call `root.animate`.

Run:

```bash
cd frontend && npm test -- src/components/ThemeModeToggle src/hooks/useThemeViewTransition
cd frontend && npm run build
```

Manual Chrome verification at `http://localhost:18643`:

- Light mode shows the sun.
- Dark mode shows the moon.
- The button icon is centered.
- The reveal starts from the button center in the header.
- Login-page variant still shows `浅色模式` or `深色模式` next to the button.

## Out Of Scope

- Replacing `@theme-toggles/react`.
- Replacing Zustand theme state.
- Changing Ant Design token configuration.
- Adding system-theme preference.
- Redesigning the header, login page, or app color palette.
- Changing crawler task UI.
