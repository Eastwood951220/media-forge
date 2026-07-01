# Fix Theme Transition Text Visibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix text becoming invisible during light/dark mode switch by preventing the View Transition API's default cross-fade on `::view-transition-old(root)`.

**Architecture:** The View Transition API applies a default cross-fade (old view fades out, new view fades in). Our `clipPath: circle(0px)` on `::view-transition-new(root)` makes the new view start fully transparent. Combined, this creates a period where neither view is visible. The fix: add a global CSS rule `animation: none !important` on both `::view-transition-old(root)` and `::view-transition-new(root)` to prevent the browser's default cross-fade, then remove the now-redundant JavaScript `oldAnim`.

**Tech Stack:** CSS

---

### Task 1: Add CSS override for View Transition default animation

**Files:**
- Create: `frontend/src/styles/view-transition.css`
- Modify: `frontend/src/hooks/useThemeViewTransition/index.ts:71-75` (remove oldAnim)

**Interfaces:**
- Consumes: (none — fixed in `useThemeViewTransition` hook)
- Produces: `::view-transition-old(root)` stays at full opacity throughout transition; text always visible

- [ ] **Step 1: Write src/styles/view-transition.css**

```css
/*
 * Override the browser's default cross-fade for View Transition API.
 *
 * The UA default fades ::view-transition-old(root) from opacity 1 → 0
 * and ::view-transition-new(root) from opacity 0 → 1.
 *
 * We replace this with our own clipPath-based reveal (controlled from JS),
 * so we disable ALL default animations — the old view stays fully opaque
 * while the new view is gradually revealed on top.
 */

::view-transition-old(root),
::view-transition-new(root) {
  animation: none !important;
}
```

- [ ] **Step 2: Import the CSS**

Read `src/App.tsx`. Add the import after the existing CSS import:

```typescript
import './styles/app.css'
import './styles/view-transition.css'
```

- [ ] **Step 3: Remove the now-redundant JavaScript oldAnim**

Read `src/hooks/useThemeViewTransition/index.ts`. Delete lines 72-75 (the `oldAnim` declaration and related code):

Delete:
```typescript
      const oldAnim = root.animate(
        { opacity: [1, 1] },
        { duration, pseudoElement: '::view-transition-old(root)' },
      )
```

And delete line 88:
```typescript
      oldAnim.commitStyles()
```

The `oldAnim` variable and `commitStyles()` call are no longer needed — the CSS override handles keeping the old view visible.

- [ ] **Step 4: Verify**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npx eslint . 2>&1 | tail -1 && npm run build 2>&1 | tail -3 && ./node_modules/.bin/vitest run 2>&1 | tail -3
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/styles/view-transition.css src/App.tsx src/hooks/useThemeViewTransition/index.ts
git commit -m "fix: prevent text invisibility during theme transition"
```
