# Scraping subtask detail drawer

## Intent

The scraping task page lists each movie's final result but gives no way to see where a subtask is running or why it failed. Add a detail drawer with a step timeline and task logs, using the existing storage subtask detail as the interaction reference.

## Scope and constraints

- Open the drawer from a scraping task item's row; keep the user on the task detail page.
- Show the item's code, title, status, source, output folder, duration, and error, followed by a step timeline and chronological logs. Show clear empty and loading states.
- Record actual execution stages: prepare, locate folder, fetch metadata, write artwork, write NFO, and refresh status. Record relevant outcomes and failures without logging secrets or full response bodies.
- Persist per-item JSONL logs under the app data directory, following the storage task log pattern. Add the current `step` to the scraping item model and migrate existing installations. Existing items have no historical step events; the drawer still shows their available fields and an empty log state.
- Expose an authenticated, owner-scoped item detail/log API. Append owner-scoped realtime log events and item step updates so an open drawer refreshes during execution. Keep the existing task detail/list responses compatible.
- Failed or skipped items must have a terminal log explaining the reason, including early returns, unexpected exceptions, cancellation, and interrupted tasks. Retried jobs create new items and independent logs.
- Do not add a separate route or change scraping algorithms, source priority, or image selection.

## Approaches

1. **Chosen: persist actual steps and logs.** Model the current step and save JSONL records, then render them in a drawer with realtime updates. This supports historical diagnosis and matches storage task behavior; it needs a migration, API, and worker instrumentation.
2. **Use only the current item fields.** This is smaller but cannot show which stages ran or a useful log history, so it does not meet the requested detail.

## Behavior and data flow

The worker sets a step and appends a structured log at each stage. Logs contain a timestamp, level, message, optional step and context. The log writer persists the entry before publishing `scraping.item.log.appended`. Item updates include the current step. The drawer fetches item details and logs on open, filters realtime events to its item ID, and refreshes after a reconnect or resync. Log reading checks ownership through the parent task. The timeline groups messages by step and distinguishes waiting, active, complete, and failed stages. The full log list remains chronological.

## Verification

Add backend tests for persistence, ownership, failure/skip paths, and worker stages. Add frontend tests for opening the drawer, rendering steps/logs, filtering realtime events, and empty history. Run focused scraping tests, focused frontend tests, and a frontend build.
