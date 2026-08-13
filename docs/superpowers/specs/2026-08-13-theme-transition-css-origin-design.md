# Theme Transition CSS Origin Design

## Context

The current theme transition can calculate the correct `x` and `y` origin from the theme toggle area, but the visible transition still appears to begin from the top center of the page. This happens after a page refresh and can also be observed on later toggles depending on how the browser schedules the View Transition first frame.

The current implementation starts `document.startViewTransition()`, waits for `transition.ready`, and then calls `root.animate(..., { pseudoElement: '::view-transition-new(root)' })`. That means the browser may create and display the root transition pseudo-elements before the custom `clip-path` animation is attached. The measured coordinates can be correct while the first visible frame still comes from the browser's default root transition behavior.

## Goal

Make every theme switch visibly expand from the theme toggle area in the upper-right corner from the first rendered transition frame, including the first switch after a full page refresh.

## Non-Goals

- Do not redesign the login page or application shell.
- Do not change the persisted theme store model.
- Do not replace `@theme-toggles/react`.
- Do not change crawler task behavior.

## Recommended Approach

Use CSS-driven View Transition animation for the root pseudo-element instead of attaching a Web Animations API animation after `transition.ready`.

Before calling `document.startViewTransition()`, the hook should:

1. Resolve the transition origin from the theme toggle trigger when available.
2. Fall back to a fixed upper-right point near the toggle area when no trigger element is available.
3. Calculate the radius needed to cover the viewport.
4. Write `--theme-transition-x`, `--theme-transition-y`, `--theme-transition-radius`, `--theme-transition-duration`, and `--theme-transition-easing` to `document.documentElement`.
5. Add `theme-transition-active` to `document.documentElement`.

CSS should own the animation:

- Disable the browser's default root View Transition animation on `::view-transition`, `::view-transition-group(root)`, `::view-transition-image-pair(root)`, and `::view-transition-old(root)`.
- Apply `theme-root-reveal` directly to `::view-transition-new(root)` while the CSS variables are present.
- Use linear timing and `both` fill mode so the reveal advances consistently and holds its final frame until the browser transition completes.

The hook should wait for `transition.finished` when available, otherwise wait for the configured duration, then remove the active class and CSS variables.

## Component Flow

`ThemeModeToggle` remains the only UI trigger.

On click:

1. Pass `event.currentTarget` into `runTransition`.
2. `useThemeViewTransition` prepares CSS variables before `startViewTransition`.
3. `startViewTransition` callback toggles `data-theme`, the `dark` class, and Zustand theme state synchronously.
4. Browser creates `::view-transition-new(root)` with the CSS animation already available.
5. Cleanup runs after completion.

## Origin Rules

When the button element is available, the origin is the button center from `getBoundingClientRect()`.

When the button element is unavailable, the origin falls back to an upper-right visible point:

- `x = max(window.innerWidth - 44, 0)`
- `y = 44`

This fallback avoids placing the origin exactly outside the visible viewport, which can make the first visible arc appear to come from the top center.

## Error Handling

If View Transition API is unavailable or reduced motion is requested, the hook should toggle the theme immediately without animation.

If View Transition setup throws, log the existing warning, clean up the active class and CSS variables, unlock the transition, and leave the theme state consistent with the attempted toggle.

## Testing

Focused frontend tests should cover:

- CSS variables and `theme-transition-active` are prepared before the `startViewTransition` callback runs.
- The trigger button center is used when an element is supplied.
- The upper-right fallback is used when no trigger element is supplied.
- `document.documentElement.animate` is not used for root reveal.
- Reduced motion and missing View Transition API still toggle immediately without animation.

Manual Chrome verification should cover:

- Full refresh, first light-to-dark toggle starts from the upper-right toggle area.
- Second dark-to-light toggle starts from the same area.
- `document.getAnimations({ subtree: true })` reports a root `clipPath` animation whose first keyframe uses the expected `x` and `y`.
- No visible pause or jump occurs near the end of the transition.
