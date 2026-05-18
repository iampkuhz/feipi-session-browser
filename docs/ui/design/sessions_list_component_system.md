# Sessions List Component System

## Objective

Sessions List should be assembled from stable UI primitives rather than one-off HTML.

## Component layers

1. `ui_primitives.html`
   - Generic Jinja macros: buttons, select controls, stat pills, sortable headers, token cell.

2. `sessions_list_components.html`
   - Page-specific composition: page title, active filters, table header, footer.

3. `ui-primitives.css`
   - Generic primitive styles.

4. `sessions-list.css`
   - Page-scoped layout and table styles under `.sessions-page`.

5. `ui_primitives.js`
   - Small generic behavior, primarily sort-button form integration.

## Button contract

Use `ui.btn(label, variant, size)` or equivalent `.ui-btn` classes.

Allowed variants:
- `primary`
- `secondary`

Allowed sizes:
- `sm`
- `md`

Avoid one-off button classes on Sessions List unless a new primitive is first defined.
