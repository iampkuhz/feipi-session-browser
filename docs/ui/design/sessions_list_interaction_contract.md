# Sessions List Interaction Contract

## Current observed failure pattern

The HIFI structure is close, but interaction wiring is incomplete.

Observed from saved MHTML:
- Sort controls are rendered as header label text plus a separate icon-only button. The label is not part of the clickable control.
- Table sort form submits only `sort=<key>` and loses active filter state.
- Pagination buttons submit only `page=prev|next` and lose active filters/sort state.
- `ui_primitives.js` was not loaded in the captured page, so button behavior cannot depend on that script.
- Filter chips exist visually, but remove behavior needs deterministic links or submit actions.
- Clear All is hidden even when state should be explicit.
- Topbar Refresh was absent/empty in the captured page.

## Required policy

Prefer server-rendered GET links for sort, pagination, and filter chip removal. They work without JavaScript and are easier to test.

Allowed implementation:
1. Link-based controls:
   - sort headers use `<a class="sessions-th__sort-btn" href="...">`
   - pagination uses `<a class="ui-btn ...">`
   - chip removal uses `<a href="...">×</a>`

2. Form-based controls:
   - controls may use `<button type="submit">`
   - but every secondary form must include hidden inputs for current state:
     `q/session_id`, `agent`, `model`, `project`, `date`, `sort`, `dir`, and page reset rules.

Disallowed:
- icon-only sort buttons
- sort/pagination forms that lose filters
- controls that rely on JS not loaded by the page
- nested forms
- duplicated query state logic in templates
