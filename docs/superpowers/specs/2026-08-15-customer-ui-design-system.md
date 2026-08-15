# Customer-Facing UI Design System — Design Spec

## Context

The frontend (`frontend/`) currently has two functional but entirely
unstyled screens — `app/login/page.tsx` and `app/requests/page.tsx` —
raw HTML with no CSS at all. There is no design system: no color
tokens, no typography choices, no shared components. This is a
customer-facing product (pharma/device-partnership BD teams submit
and track requests), so it needs to look and feel like a considered,
attractive product rather than an internal tool.

This spec covers building that design system and applying it to the
two screens that exist today, wired to the real backend exactly as
they are now. It deliberately does **not** cover the richer screens
described in the org-level-rebuild spec (platform match, cost &
service selection, BD dashboards) — those need their own data model
and backend work (Phase 2+) and will get their own spec/plan each,
sequenced after this one.

## Goals

- Establish a reusable visual identity (color, type, component
  patterns) that future screens inherit, rather than one-off styling.
- Restyle Login and Requests to be attractive, bold, and
  customer-friendly, without changing their functional behavior
  (same fields, same validation rules, same API calls).
- Add the baseline UX a customer-facing product needs: loading
  states, empty states, inline validation, responsive layout,
  visible keyboard focus, `prefers-reduced-motion` support.

## Non-goals

- No new backend endpoints, no new data model, no change to what
  `POST /auth/login` or `POST/GET /requests` accept or return.
- No navigation/multi-page shell — only the two screens that exist.
- No mockups of Phase 2+ screens (platform match, cost & service
  selection, dashboards) — explicitly deferred.

## Visual identity

### Color

Pulled from the real Shaily brand mark (`assets/shaily-logo.png`:
lime green, forest green, orange, teal-blue, gray), deliberately
avoiding the teal-blue swatch the old Streamlit prototype used as
primary (`#2F6E97`).

| Token | Hex | Role |
|---|---|---|
| `forest-900` | `#0F4C33` | Deep anchor — headings, primary text on light surfaces |
| `forest-600` | `#1B7A4D` | Primary interactive — buttons, links, focus rings |
| `lime-500` | `#8DC63F` | Gradient partner, success/healthy states |
| `orange-500` | `#F0883E` | Gradient partner, warning/attention states |
| `sand-50` | `#FAF8F3` | Page background |
| `ink-700` | `#2B2E2C` | Body text |

Signature gradient `forest-600 → lime-500 → orange-500`, used in
exactly two places: a thin accent band (header/page top) and primary
button fills. Never used as a full-page or full-card wash — everything
else stays quiet (sand background, white cards, ink text) so the
gradient reads as a deliberate accent.

### Type

- **Display/headings** — Space Grotesk (geometric, confident, fits a
  device-engineering audience). Used at restrained weights/sizes —
  this is a B2B console, not a marketing hero.
- **Body** — IBM Plex Sans (humanist but structured; precise without
  being cold — suits forms and dense data).
- **Data/utility** — IBM Plex Mono, for request IDs, status codes,
  timestamps — small doses of "lab console" character.

Fonts loaded via `next/font/google` (self-hosted at build time, no
runtime third-party font request).

### Signature element

The Shaily mark is a four-quadrant diagonal color block. That
geometry is echoed in a small **quadrant status chip** — a tiny 2×2
rounded-color-block icon — used next to request status instead of a
generic colored dot, and reused as the loading indicator. It's the
one place the brand's actual geometry appears beyond the logo itself.

## Architecture

- Add Tailwind CSS to `frontend/`. Palette and type tokens above go
  into `tailwind.config.ts` as named theme colors (`forest`, `lime`,
  `orange-accent`, `sand`, `ink`) and font families, so every
  component pulls from the same tokens rather than ad-hoc hex values.
- New `frontend/components/` directory for the shared component set
  (below), imported by both pages.
- `frontend/app/globals.css` for Tailwind directives + any small
  global resets (focus-visible styling, reduced-motion query).
- No change to `lib/api.ts` or the `/api/*` proxy — this pass is
  presentation and UX state only.

## Components

| Component | Purpose |
|---|---|
| `Button` | Primary (gradient fill), secondary (outline), disabled + loading (spinner) states |
| `TextField` / `SelectField` | Labeled inputs with an inline validation message slot |
| `Card` | White surface on the sand background — login card, requests table container |
| `StatusChip` | The quadrant-mark signature element; one color mapping per request status string |
| `EmptyState` | Icon + message + optional action — "No requests yet" |
| `Skeleton` | Loading placeholder rows (requests table) and button-pending spinner |
| `Header` | Logo mark + product name; no nav yet (only two screens exist) |

## Page designs

### Login (`app/login/page.tsx`)

- Centered card on the sand background, thin gradient accent band at
  the top of the page.
- Fields: Name, Email, and Role — Role only rendered for emails
  ending `@shaily.com`, exactly as today. The field animates in/out
  (height/opacity transition) rather than appearing/disappearing
  abruptly; instant under `prefers-reduced-motion`.
- Submit button shows a spinner + "Signing in…" while in flight and
  is disabled to prevent double-submit.
- Empty name/email caught inline before submit. A failed login shows
  a dismissible banner ("We couldn't sign you in — check your name
  and email and try again") replacing the current generic error text
  — no change to what's actually validated.

### Requests (`app/requests/page.tsx`)

- `Header` at top (mark + "BD Console" + signed-in user name), thin
  gradient accent band beneath it.
- "New request" card: Brand text field, Market select (US/EU/Canada,
  unchanged), submit button.
- "Your requests" card: table with ID (IBM Plex Mono), Brand, Market,
  Status (`StatusChip`).
- While the initial `listRequests` call is in flight: `Skeleton` rows.
  On resolve: real rows, or `EmptyState` ("No requests yet — submit
  your first one above") if the list is empty.
- A newly submitted request appears in the list with a brief
  highlight/fade-in (instant under reduced-motion).
- `StatusChip` color mapping: green quadrant lit for
  healthy/in-progress states, orange for states needing attention,
  gray for closed/inactive — mapped from whatever status strings the
  backend returns today (no backend change).

## UX baseline

- Responsive: single-column, full-width layout under ~640px; the
  requests table becomes a stacked card-per-request on mobile instead
  of horizontal scroll.
- Visible keyboard focus ring on every interactive element.
- `prefers-reduced-motion` respected — all transitions collapse to
  instant state changes.

## Error handling

- Field-level messages where the backend gives a 422 validation
  error, mapped to the relevant field.
- A dismissible banner for network/5xx failures, written in the
  interface's voice — states what happened, not an apology, no
  internal error jargon.

## Testing

- `npm run build` for type/build correctness (Tailwind + font
  additions, TypeScript).
- Manual `docker-compose up` smoke pass against the real backend:
  login via both the customer path and an `@shaily.com` path, submit
  a request, confirm it appears, confirm the empty state on a fresh
  account, confirm loading states are visible, resize to a mobile
  width and confirm the responsive layout.

## Self-Review Notes

- **Placeholder scan**: none — every section specifies exact tokens,
  file locations, and behavior.
- **Internal consistency**: component list matches what the two page
  designs reference; color tokens match what's used in Login/Requests
  and `StatusChip`; non-goals explicitly exclude the Phase 2+ screens
  so scope doesn't silently expand during implementation.
- **Scope check**: focused enough for a single implementation plan —
  one design system, two screens, no backend change.
- **Ambiguity check**: `StatusChip` color mapping says "whatever
  status strings the backend returns today" rather than enumerating
  them, since the exact set lives in `backend/app/models.py` — the
  implementation plan should read that directly rather than have this
  spec guess and drift from it.
