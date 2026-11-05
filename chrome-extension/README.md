
### UI components

The popup and configuration page enhance existing controls with React + Ant Design.
The page-action task selector uses Ant Design Select with name search (case insensitive),
clear selection and empty-result feedback. Component styles and dropdowns are mounted
inside the page-action Shadow DOM. The dropdown is outside the scrolling dialog to
avoid clipping. Closing the dialog unmounts the selector and removes its popup container.

`pnpm build` builds popup/background entries first, then bundles `content.js` as a
self-contained IIFE: manifest content scripts cannot import shared React chunks.

All displayed timestamps (configuration status, popup status and diagnostic entries)
use local device time in `YYYY-MM-DD HH:mm:ss` format. Missing or invalid times
show `-`. Stored timestamps and copied diagnostic JSON retain their ISO format.

Password/Token fields in the extension configuration use a visibility toggle and a
copy button. Saved values remain available when switching visibility; clipboard
failures select the field for manual copying.
