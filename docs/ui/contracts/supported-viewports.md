# Supported Viewports

## Supported

| Device | Viewport Width | Notes |
|---|---|---|
| MacBook Pro 13/14 inch built-in | 1440px -- 1512px | Primary target |
| 2560x1440 external monitor | 2560px | Wide desktop |

## Not Supported

- Mobile (phones)
- Tablet (iPad, Android tablets)
- Narrow windows (< 1024px) -- use horizontal scroll if needed
- Windowed browsers below 1400px width

## CSS Breakpoints

| Breakpoint | Purpose |
|---|---|
| `min-width: 1400px` | Desktop-wide adjustments (MBP 13/14 baseline) |
| `min-width: 1440px` | Full desktop layout |
| `min-width: 1512px` | MBP 14 / larger displays |
| `min-width: 2560px` | 2K external monitors |

### Forbidden

No `max-width` breakpoints below 1400px are supported. The following
are explicitly removed:

- `max-width: 480px` -- mobile phone
- `max-width: 600px` -- small phone
- `max-width: 767px` / `768px` -- mobile
- `max-width: 820px` -- tablet narrow
- `max-width: 900px` -- tablet
- `max-width: 1023px` / `1024px` -- tablet
- `max-width: 1180px` -- medium tablet
- `max-width: 1260px` -- tablet reduction
- `max-width: 1320px` -- tablet modal adjustment

### Kept

- `max-width: 1360px` -- MBP 13 detail view adjustment
- `max-width: 1400px` -- MBP 13/14 filter bar / hero stacking
