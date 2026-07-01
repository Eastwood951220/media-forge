# Media Forge Login Page Redesign — Design Spec

> **Date:** 2026-07-01 | **Status:** Approved | **Source:** ui-ux-pro-max + user requirements

## Visual Direction

Enterprise SaaS glassmorphism login. Left-right split layout. Left: brand identity + subtle animated orbs. Right: frosted glass login card. Professional, modern, restrained — not flashy.

**Style:** Glassmorphism (ui-ux-pro-max verified). **Pattern:** Enterprise Gateway.

## Color System

### Primary Color
```
rgb(0, 106, 255) — user-specified
Hex: #006AFF
```

### Light Mode Palette
| Role | Value | Usage |
|------|-------|-------|
| Primary | `#006AFF` | Buttons, focus rings, icons, links |
| Primary Hover | `#0056CC` | Button hover |
| Primary Active | `#004299` | Button active |
| Card BG | `rgba(255,255,255,0.64)` | Login card |
| Card Border | `rgba(255,255,255,0.48)` | Card edge |
| Page BG | `#F5F7FA` | Right panel background |
| Brand BG | `#F0F4FF` | Left panel light base |
| Text Primary | `#1E293B` | Headings, labels |
| Text Secondary | `#64748B` | Subtitles, helper |
| Text Muted | `#94A3B8` | Placeholders |
| Input BG | `rgba(255,255,255,0.80)` | Input fields |
| Input Border | `rgba(0,0,0,0.12)` | Input border default |
| Danger | `#EF4444` | Error messages |

### Dark Mode Palette
| Role | Value | Usage |
|------|-------|-------|
| Primary | `#3399FF` | Brighter for dark bg |
| Card BG | `rgba(20,28,45,0.72)` | Login card |
| Card Border | `rgba(255,255,255,0.08)` | Card edge |
| Page BG | `#0F172A` | Right panel background |
| Brand BG | `#0A1628` | Left panel dark base |
| Text Primary | `#F1F5F9` | Headings, labels |
| Text Secondary | `#94A3B8` | Subtitles |
| Text Muted | `#64748B` | Placeholders |
| Input BG | `rgba(255,255,255,0.06)` | Input fields |
| Input Border | `rgba(255,255,255,0.10)` | Input border default |

## Glassmorphism Parameters

```css
/* Card */
background: rgba(255, 255, 255, 0.64);
backdrop-filter: blur(20px) saturate(130%);
-webkit-backdrop-filter: blur(20px) saturate(130%);
border: 1px solid rgba(255, 255, 255, 0.48);
border-radius: 22px;
box-shadow:
  0 24px 60px rgba(15, 23, 42, 0.12),
  0 4px 12px rgba(15, 23, 42, 0.06),
  inset 0 1px 0 rgba(255, 255, 255, 0.45);

/* Dark mode */
[data-theme="dark"] & {
  background: rgba(20, 28, 45, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    0 24px 60px rgba(0, 0, 0, 0.35),
    0 4px 12px rgba(0, 0, 0, 0.20),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

/* Fallback */
@supports not (backdrop-filter: blur(1px)) {
  background: rgba(255, 255, 255, 0.92);
  [data-theme="dark"] & {
    background: rgba(20, 28, 45, 0.92);
  }
}
```

## Typography

Use Ant Design's default font stack (system fonts). No custom Google Font import needed.

| Element | Size | Weight | Line Height |
|---------|------|--------|-------------|
| System title | 28px | 700 | 1.3 |
| Tagline | 14px | 400 | 1.5 |
| Feature bullets | 14px | 500 | 1.5 |
| Form labels | 14px | 500 | 1.4 |
| Input text | 16px | 400 | 1.5 |
| Button text | 16px | 500 | 1.5 |
| Forgot link | 14px | 400 | 1.5 |

## Layout Grid

### Desktop (≥1024px)
```
┌──────────────────────────────────────────────────┐
│ Left 55%              │ Right 45%                │
│                        │                          │
│  [Orb 1]               │    ┌─────────────┐      │
│         [Orb 2]        │    │  Glass Card  │      │
│    [Orb 3]             │    │  400-430px   │      │
│                        │    │              │      │
│  Logo + Name          │    │  Login Form  │      │
│  Tagline              │    │              │      │
│  • Feature 1          │    └─────────────┘      │
│  • Feature 2          │                          │
│  • Feature 3          │    [Theme Toggle]        │
│                        │                          │
│  Grid texture          │                          │
└──────────────────────────────────────────────────┘
```

### Tablet (768-1023px)
Left panel narrows to ~45%. Card width adjusts. Orbs reduced to 2.

### Mobile (<768px)
Left panel hidden (display:none). Right panel takes full width. Card: margin 20px, max-width 100%. No horizontal scroll.

## Background Decorations (Orbs)

3 blurred colored orbs using CSS-only animation:

```css
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
}

/* Orb 1 — primary blue, large */
.orb-1 {
  width: 480px;
  height: 480px;
  background: radial-gradient(circle, rgba(0,106,255,0.25), transparent 70%);
  top: -15%;
  left: -10%;
  animation: orb-drift 16s ease-in-out infinite alternate;
}

/* Orb 2 — warm accent, medium */
.orb-2 {
  width: 320px;
  height: 320px;
  background: radial-gradient(circle, rgba(99,102,241,0.18), transparent 70%);
  bottom: -12%;
  right: 15%;
  animation: orb-drift 13s ease-in-out infinite alternate-reverse;
}

/* Orb 3 — subtle cyan, small */
.orb-3 {
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, rgba(14,165,233,0.15), transparent 70%);
  top: 45%;
  left: 35%;
  animation: orb-drift 18s ease-in-out infinite alternate;
}

@keyframes orb-drift {
  0% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(20px, -15px) scale(1.08); }
  100% { transform: translate(-10px, 25px) scale(0.95); }
}

/* Dark mode — dim orbs */
[data-theme="dark"] .orb {
  opacity: 0.18;
}
```

## Animations

### Page Enter
- Card: `opacity 0→1, translateY(24px→0)`, 600ms, ease-out
- Brand content: staggered — logo 0ms delay, text 100ms, features 200ms delay
- Orbs: fade in over 800ms opacity

### Input Focus
- Border: `rgba(0,0,0,0.12)` → `#006AFF`, 200ms
- Box-shadow: none → `0 0 0 3px rgba(0,106,255,0.15)`

### Button
- Hover: `translateY(-1px)`, box-shadow increase, 200ms
- Active: `translateY(0)`, scale(0.985), 100ms
- Loading: opacity 0.7 + spinner

### Theme Switch
- All color transitions: `transition: background-color 300ms, border-color 300ms, color 300ms`

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  .orb { animation: none; }
  .login-card { animation: none; opacity: 1; transform: none; }
  * { transition-duration: 0ms !important; }
}
```

## Input/Button State Specs

### Input (Username / Password)
| State | Border | Shadow | BG |
|-------|--------|--------|-----|
| Default | `rgba(0,0,0,0.12)` | none | `rgba(255,255,255,0.80)` |
| Hover | `rgba(0,0,0,0.20)` | none | `rgba(255,255,255,0.85)` |
| Focus | `#006AFF` | `0 0 0 3px rgba(0,106,255,0.15)` | `rgba(255,255,255,0.95)` |
| Error | `#EF4444` | `0 0 0 3px rgba(239,68,68,0.12)` | `rgba(255,240,240,0.80)` |
| Disabled | `rgba(0,0,0,0.06)` | none | `rgba(0,0,0,0.04)` |
| Autofill | — | — | `rgb(232,240,254)` (browser default) |

### Button
| State | BG | Text | Transform | Shadow |
|-------|-----|------|-----------|--------|
| Default | `#006AFF` | white | none | `0 2px 8px rgba(0,106,255,0.25)` |
| Hover | `#0056CC` | white | `translateY(-1px)` | `0 4px 16px rgba(0,106,255,0.35)` |
| Active | `#004299` | white | `translateY(0) scale(0.985)` | `0 1px 4px rgba(0,106,255,0.20)` |
| Loading | `#006AFF` (70% opacity) | white | none | none |
| Disabled | `rgba(0,0,0,0.06)` | `rgba(0,0,0,0.25)` | none | none |

## Component Structure

```
src/pages/login/
├── index.tsx                    # Page layout (L+R split)
├── index.module.less            # Page-level layout, orbs, responsive
├── components/
│   ├── LoginBrandPanel.tsx      # Left panel: logo, name, features
│   ├── LoginBrandPanel.module.less
│   ├── LoginForm.tsx            # Right panel: glass card + form logic
│   ├── LoginForm.module.less    # Glassmorphism card, input overrides
│   ├── LoginBackground.tsx      # Orb decorations (CSS-only)
│   └── LoginBackground.module.less
```

**Reused:**
- `src/components/ThemeModeToggle/` — theme toggle (unchanged)
- `src/stores/useThemeStore.ts` — theme state (primaryColor updated to `#006AFF`)
- `src/stores/useAuthStore.ts` — auth state (unchanged)
- `src/api/login/` — login API (unchanged)

## What Must NOT Change
- Login API, auth flow, token storage, redirect logic
- Route definitions in `src/routes/index.tsx`
- ThemeModeToggle component
- Any auto-generated file
- No `any`, `@ts-ignore`, or `@ts-nocheck`
- No new npm dependencies

## Verification Checklist
- [ ] tsc -b: zero errors
- [ ] eslint .: zero errors
- [ ] npm run build: succeeds
- [ ] npm test: all tests pass
- [ ] Login form submits correctly
- [ ] Login failure shows error
- [ ] Login success redirects
- [ ] Enter key submits
- [ ] Loading prevents double submit
- [ ] Password show/hide works
- [ ] Remember me preserved
- [ ] Theme toggle works
- [ ] Light mode correct
- [ ] Dark mode correct
- [ ] 375px mobile: no horizontal scroll
- [ ] 768px tablet: layout correct
- [ ] 1440px desktop: full layout
- [ ] prefers-reduced-motion: animations disabled
- [ ] No backdrop-filter: solid card fallback
- [ ] No console warnings
