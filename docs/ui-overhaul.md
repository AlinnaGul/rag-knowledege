# UI Overhaul Brief

This document captures the current state of the admin and chat interfaces so a professional designer can craft a more polished layout.

## Current pages
- **Admin / Collections** – list and create collections; each card now uses the shared `AdminCard` component.
- **Admin / Collection** – manage documents within a collection.
- **Admin / Documents** – browse uploaded documents.
- **Admin / Users** – manage users.
- **Chat** – conversation view with message bubbles and citation drawer.

## Observed pain points
- Visual style of admin cards was inconsistent before `AdminCard`.
- Action buttons previously overlapped; now wrapped with `flex flex-wrap gap-2` but should follow a grid or toolbar pattern.

## Design goals
- Establish a cohesive design language across all admin pages.
- Provide responsive layouts that scale from mobile to desktop without overlapping controls.
- Reserve space for future filters and sorting controls on list pages.

## Component hierarchy
- `AdminCard` wraps each admin section with standard padding and optional footer.
- Action columns contain a `div.flex.flex-wrap.gap-2` hosting buttons.

## Styling guidelines
- Use TailwindCSS utilities for spacing; avoid manual `space-x`/`space-y` classes.
- Prefer `gap-*` utilities for flexible wrapping.

## Next steps for designer
- Provide high‑fidelity mockups for each page.
- Define a color palette and typography scale.
- Propose reusable components for tables, forms, and modals.
- Suggest transitions/animations for chat messages and drawer interactions.

