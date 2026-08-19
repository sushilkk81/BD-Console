# Customer Engagement Tracking & BD Manager Notifications — Design

**Date:** 2026-08-17
**Status:** Approved for planning
**Author:** Claude Code, with Sushil Kurade

## 1. Background

Customers reach the app via a login link (the public-portal entry point —
icon/placement on Shaily's public site is a separate, deferred design
decision; nothing in this slice depends on it). Today a customer login
captures only name and email, and produces no signal for Shaily's BD
Managers about who is engaging or with what.

This slice adds:

- Two new fields at customer login — an official phone number and a
  "Role in the Organization" title (R&D Manager / BD Manager, i.e. the
  customer's own job title, not an app permission).
- A per-visit engagement log (`customer_visits`) capturing who logged in,
  when, and which pages they viewed that session — giving Shaily's BD
  Managers a read on customer-specific interest.
- An in-app notification to every current BD Manager the first time a
  given customer logs in, so a KAM can be assigned promptly. (KAM
  assignment itself — `org_kam_map`, reassignable at any time by a BD
  Manager — already exists and needs no changes; this slice only adds the
  signal that triggers a BD Manager to use it.)

## 2. Non-goals (this slice)

- SMS or email delivery of notifications. BD Managers and KAMs travel and
  may not always be at a laptop, so SMS/email fan-out is a known future
  need, but it requires SES/SMS provider setup not yet provisioned (see
  `org-level-rebuild-design.md` §7, §8 step 4/6) and is deferred to that
  later phase. This slice is in-app only.
- The public-portal entry icon/link design on Shaily's marketing site —
  deferred, tracked separately; this slice only changes what happens once
  a customer reaches the existing `/login` page.
- Any change to KAM assignment itself, or to who can see/edit
  `org_kam_map` — unchanged.
- Full clickstream (per-page timestamps). "Pages visited" is a distinct
  list per session, not an event-by-event log — sufficient for "what did
  this customer look at," cheaper to write and query.

## 3. Data model

### `users` — new columns

- `phone` (nullable `VARCHAR(30)`) — official phone number. Required at
  login for customer-domain users; unused for `@shaily.com` logins in
  this slice.
- `title` (nullable `VARCHAR(50)`) — "Role in the Organization" from the
  login dropdown (`R&D Manager` | `BD Manager`). Metadata only — it does
  not affect `role` (which stays `"Customer"`) or any permission check.
  Required at login for customer-domain users.

### `customer_visits` — new table

One row per customer login (every login, not just the first).

| column | type | notes |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → `users.id` | |
| `org_id` | FK → `organizations.id` | |
| `session_id` | `VARCHAR(36)` (uuid), unique, indexed | returned to the frontend at login; correlates pageview beacons to this visit |
| `contact_name` | `VARCHAR(100)` | snapshot of `users.name` at visit time |
| `contact_email` | `VARCHAR(255)` | snapshot of `users.email` |
| `contact_phone` | `VARCHAR(30)` | snapshot of `users.phone` |
| `contact_title` | `VARCHAR(50)` | snapshot of `users.title` |
| `org_name` | `VARCHAR(200)` | snapshot of `organizations.name` |
| `pages_visited` | `JSON` (list of strings) | distinct page labels, appended to via the pageview endpoint; starts as `[]` |
| `started_at` | `DATETIME`, indexed | this visit's login time — the log's "Access Date" |

Snapshotting contact fields (rather than joining live) follows the
existing `AuditLog.detail` convention in this codebase: the log should
reflect what was true at the time, not drift if the user later edits
their profile.

### `notifications` — new table

| column | type | notes |
|---|---|---|
| `id` | PK | |
| `recipient_user_id` | FK → `users.id`, indexed | a specific BD Manager |
| `org_id` | FK → `organizations.id` | |
| `customer_visit_id` | FK → `customer_visits.id` | |
| `message` | `VARCHAR(300)` | e.g. `"{name} ({org}) logged in for the first time"` |
| `link_path` | `VARCHAR(200)` | e.g. `/dashboard/manager/customers?visit=<id>` |
| `is_read` | `BOOLEAN`, default `false` | |
| `created_at` | `DATETIME`, indexed | |

Rows are created by fan-out: at the moment a customer's **first-ever**
login is detected (no prior `customer_visits` row for that `user_id`),
one `notifications` row is inserted per user currently holding role `BD
Manager`. A BD Manager added after that moment won't see past
notifications — acceptable, since these are real-time engagement signals,
not a durable audit trail (that's what `customer_visits` is for).

Subsequent logins by the same customer still create a `customer_visits`
row (so the engagement log keeps growing) but do **not** fan out another
notification — this was a deliberate choice to avoid notification noise
on repeat visits; ongoing interest is visible in the engagement log page
instead.

## 4. Backend

### `POST /auth/login` (extended)

- For non-`@shaily.com` domains: `title` and `phone` become required
  fields (422 if missing), validated the same way `role` already is for
  `@shaily.com` domains.
- After resolving/creating the `user` row (existing logic unchanged),
  for customer logins only:
  1. Check whether any `customer_visits` row already exists for this
     `user_id`.
  2. Insert a new `customer_visits` row (snapshotting current
     name/email/phone/title/org, a fresh `session_id`, `started_at` =
     now).
  3. If step 1 found none (first-ever login), fetch all users with
     `role = "BD Manager"` and insert one `notifications` row per user.
- Response gains `session_id` (only present for customer logins; `null`
  otherwise) alongside the existing token/user payload.

### `POST /activity/pageview`

- Body: `{session_id, page}`. Customer-role only (`require_role`).
- Looks up the `customer_visits` row by `session_id`, confirms it
  belongs to `current_user`, appends `page` to `pages_visited` if not
  already present (dedup, preserve insertion order). 404 if the
  `session_id` doesn't match a visit owned by the caller.
- Fire-and-forget from the frontend; a failure here must never block
  navigation or surface as a user-facing error.

### `GET /notifications`

- BD Manager only. Returns the caller's own `notifications`, most
  recent first, with an `unread_count`-style summary or per-row
  `is_read` (frontend can derive the count).

### `POST /notifications/{id}/read`

- BD Manager only, must own the row (404 otherwise). Sets `is_read =
  true`.

### `GET /customer-visits`

- BD Manager only. Returns all `customer_visits` rows joined to
  organization, most recent `started_at` first — powers the new
  engagement-log page. No pagination in this slice (matches the existing
  dashboard endpoints' unpaginated style); revisit if row volume becomes
  a real concern.

All four new/changed endpoints follow the existing `require_role`
dependency pattern in `deps.py` — no new auth machinery.

## 5. Frontend

- **Login page** (`app/login/page.tsx`): mirrors the existing
  internal-role conditional block — when the email is not
  `@shaily.com`, show a "Your role" `SelectField` (R&D Manager / BD
  Manager) and a "Phone number" `TextField`, both required, using the
  same animated-reveal pattern already used for the internal role
  field.
- **Session storage**: on a successful customer login, store
  `session_id` in `localStorage` alongside the existing token/user
  (`lib/session.ts`).
- **Pageview beacon**: a small client component mounted once near the
  root (e.g. in the customer-facing layout), using `usePathname()` to
  detect route changes and `POST /activity/pageview` with the raw
  pathname as `page` (e.g. `/requests/12`). No human-label mapping in
  this slice — the engagement-log page renders pathnames as-is; a
  prettier label mapping can be layered on later without a schema
  change. Only active when `session_id` is present.
- **`components/Header.tsx`**: for BD Manager sessions, a bell icon
  with an unread-count badge. Polls `GET /notifications` on an
  interval (e.g. 30s) and on focus. A dropdown lists recent
  notifications; clicking one calls `POST /notifications/{id}/read`
  and navigates to `link_path`.
- **New page `/dashboard/manager/customers`**: BD Manager only (via
  `useRoleGuard`), table of Name, Org, Email, Phone, Access Date, Pages
  Visited (rendered as a comma-separated list or small chips), sourced
  from `GET /customer-visits`. Add a nav entry in `Header.tsx`'s `NAV`
  map for BD Manager.

## 6. Error handling & testing

- Backend (pytest, following the existing per-router test-file
  convention):
  - Customer login without `title`/`phone` → 422.
  - First-ever customer login fans out one notification per BD
    Manager; second login by the same user does not.
  - Pageview beacon dedups repeated pages within a session and rejects
    a `session_id` that doesn't belong to the caller.
  - Role scoping: Customer cannot call `/notifications` or
    `/customer-visits`; BD Manager cannot call `/activity/pageview`.
  - Full backend suite still green.
- Frontend: `npm run build` (typecheck) plus manual smoke test — log in
  as a new customer, confirm a BD Manager sees the bell badge, click
  through to the engagement log, confirm the row and its pages-visited
  list, log in as the same customer again and confirm no second
  notification.

## 7. Open items deferred to a later phase

- SMS/email delivery of notifications (needs SES/SMS provider
  groundwork — see non-goals above).
- Any UI for the public-portal entry point itself (icon, placement).
