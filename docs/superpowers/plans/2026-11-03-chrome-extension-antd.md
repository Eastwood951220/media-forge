# Chrome Extension Ant Design Implementation Plan

Goal: implement the approved searchable task selector and unified extension styling.
Architecture: React UI islands preserve existing controller and storage messaging; Ant Design Select uses Shadow DOM style and popup containers. Popup/options use React-rendered Ant Design controls with existing event handlers.
Spec: ../specs/2026-11-03-chrome-extension-antd-design.md

- [x] Add a failing search interaction regression test.
- [x] Add React, Ant Design and local build support; implement isolated searchable task selector and lifecycle cleanup.
- [x] Render popup/config controls with React and Ant Design; unify spacing, colors and focus styles.
- [x] Verify typecheck, tests, build and extension validation; inspect changes and commit intended files only.

Constraints: no worktrees; preserve existing backend changes; all resources bundled locally.

Verification: typecheck, 46 tests, production build and extension verifier passed. Review fixes: remove unresolved Node environment references from content bundle; guard destroyed roots; handle Escape for menu/dialog separately. Real Chrome visual acceptance remains pending.
