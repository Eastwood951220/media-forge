
### UI components

The popup and configuration page enhance existing controls with React + Ant Design.
The page-action task selector uses Ant Design Select with name search (case insensitive),
clear selection and empty-result feedback. Component styles and dropdowns are mounted
inside the page-action Shadow DOM. The dropdown is outside the scrolling dialog to
avoid clipping. Closing the dialog unmounts the selector and removes its popup container.

`pnpm build` builds popup/background entries first, then bundles `content.js` as a
self-contained IIFE: manifest content scripts cannot import shared React chunks.
