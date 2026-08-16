# BD Manager & KAM Dashboards (Design Spec)

Date: 2026-08-16
Status: Approved for planning

## 1. Background

This is step 3 of the build sequence in
[`2026-08-15-org-level-rebuild-design.md`](2026-08-15-org-level-rebuild-design.md):
"Port BD dashboards — Manager command centre, KAM & assignments admin, KAM
workspace." Steps 1 (foundation slice) and the start of step 2 (core
customer flow) are done: a customer can log in, submit a bare request
(brand/market/device/total), and see their own org's requests. BD Manager
and Key Account Manager (KAM) users can already select their role at login
(the `/login` page and `/auth/login` endpoint support this), but after
login every role lands on the same customer-facing `/requests` page — there
is no Manager or KAM landing page, and the `requests` API only ever filters
by the logged-in user's own `org_id`, so internal roles can't see anything
but the (empty) Shaily org's own requests.

The legacy Streamlit app (`app.py` / `data.py`) has a working reference
implementation of both dashboards (`dash_manager`, `manager_kam_admin`,
`kam_workspace`) backed by an in-process shared dict. This spec ports the
*routing and visibility* behavior of that reference into the real
multi-tenant backend, deliberately leaving out the pieces that depend on
request data not yet ported (SKU rows, budget breakdown, deliverable
schedule — that's the rest of step 2, still pending).

## 2. Goals

- BD Manager and KAM, after login, land on a role-specific dashboard
  instead of the customer `/requests` page.
- BD Manager gets a command centre (KPIs + charts) and a KAM & assignments
  admin screen: see the KAM roster, link a customer organization to a KAM,
  and assign incoming customer requests to a KAM.
- KAM gets a workspace showing only the requests assigned to them, with a
  read-only detail view.
- Cross-org visibility is enforced server-side: BD Manager sees requests
  across all customer orgs; KAM sees only requests assigned to them;
  Customer visibility is unchanged (own org only).
- An audit trail records KAM assignment and org→KAM linking actions.

## 3. Non-goals

- No SKU rows, budget/service-selection breakdown, cost negotiation, or
  deliverable/drawing schedule in the KAM workspace — those depend on the
  fuller request data model that hasn't been ported from Streamlit yet
  (tracked as a follow-on once that lands).
- No region-based KAM routing. The legacy app's `region_map` is dead code
  in practice — region is hardcoded to `"—"` at login and never actually
  drives assignment; only the org→KAM override ever fires. Routing here is
  **org→KAM only**, tracked explicitly by the BD Manager assigning each
  customer organization (and each incoming request) to a KAM — confirmed
  with the user as the intended model, not a gap.
- No add/remove-KAM admin action. KAMs are real users now (`role = "Key
  Account Manager"`, Shaily org) who self-provision by logging in — the
  roster is a query, not a managed list. Deactivating a user is explicitly
  a later "scoped addition" per the parent spec (§7).
- No real chart-worthy business metrics. The command centre's numbers are
  the same illustrative demo figures the Streamlit app used
  (`data.py`'s `QUARTER_TARGET`, `REP_QUARTERLY`, etc.), seeded into
  Postgres as reference data so the dashboard is real end-to-end, not
  hardcoded in the frontend. They are not derived from real deals.
- No new real-auth work — role-based landing/guarding uses the existing
  mock-login trust model (role trusted from the JWT/localStorage, no
  ownership verification), matching every other screen today.

## 4. Data model

New Alembic migration, additive only (no changes to existing tables beyond
one new column):

- `requests.assigned_kam_id` — nullable FK to `users.id`. Set when the BD
  Manager assigns a request to a KAM.
- `org_kam_map` — `org_id` (FK to `organizations`, unique), `kam_user_id`
  (FK to `users`). One row per customer org that's been linked to a KAM.
  Absence of a row = unassigned/unrouted.
- `audit_log` — `id`, `org_id` (nullable FK to `organizations` — both
  current actions, `kam_assigned` and `org_kam_linked`, are org-scoped and
  populate it; nullable is reserved for future non-org actions, e.g.
  roster changes), `actor_user_id` (FK to `users`), `action` (string, e.g.
  `"kam_assigned"`, `"org_kam_linked"`), `detail` (string), `created_at`.
- `dashboard_metrics` — `key` (string, primary key), `payload` (JSONB).
  Seeded via the migration's data-migration step with the ported `data.py`
  figures. One row per chart dataset:
  - `quarterly_target` → `{"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}`
  - `rep_quarterly` → per-rep quarterly $, plus each rep's region
  - `new_customers_qtr`, `platform_production`, `rep_platform_matrix`,
    `rep_customer_matrix` — same shape as their `data.py` source dicts

Row-level isolation for `requests`: the existing `org_id`-filtered query
stays the default; a new backend dependency decides which filter (or none)
applies based on role (§5).

## 5. Backend

- `deps.require_role(*roles)` — FastAPI dependency, 403s (`"Not permitted
  for this role"`) if `current_user.role` isn't in the allowed set. Reused
  across the new routers.
- `routers/kams.py`:
  - `GET /kams` (BD Manager only) — roster = Shaily-org users with role
    `Key Account Manager`.
  - `GET /org-kam-map` (BD Manager only) — all org→KAM links, joined with
    org name and KAM name.
  - `PUT /org-kam-map/{org_id}` (BD Manager only) — body `{kam_user_id}`,
    upserts the link, writes an `org_kam_linked` audit row.
  - `POST /requests/{id}/assign-kam` (BD Manager only) — body
    `{kam_user_id}`, sets `assigned_kam_id`, writes a `kam_assigned` audit
    row. Rejects (404) if the request doesn't exist.
- `routers/dashboard.py`:
  - `GET /dashboard/metrics` (BD Manager only) — returns all
    `dashboard_metrics` rows as one keyed payload, plus a `live` block
    computed from the real `requests` table (counts by status) so the
    screen isn't 100% static.
  - `GET /dashboard/audit-log` (BD Manager only) — recent audit rows.
- `routers/requests.py` — `list_requests` gains role-based scoping instead
  of always filtering by `current_user.org_id`:
  - `Customer` → unchanged, own `org_id` only.
  - `BD Manager` → no org filter, all customer-org requests (excludes the
    internal Shaily org itself, which never submits requests), each row
    includes the org name and the org's suggested KAM (from
    `org_kam_map`) for the assignment UI.
  - `Key Account Manager` → filtered by `assigned_kam_id ==
    current_user.id`.

## 6. Frontend

- `login/page.tsx` — the post-login redirect becomes role-aware:
  `BD Manager` → `/dashboard/manager`, `Key Account Manager` →
  `/dashboard/kam`, `Customer` → `/requests` (unchanged).
- `components/RoleGuard.tsx` — client-side wrapper reading
  `bdconsole_user` from localStorage; redirects to the correct landing
  page (or `/login` if no session) when the current route doesn't match
  the user's role. Matches the existing mock-auth trust model — no new
  server-side session mechanism introduced here.
- `/dashboard/manager` — command centre: KPI tiles (annual target,
  expected pipeline, target coverage %, new customers) + charts (target vs
  expected by quarter, new customers by quarter, production by platform,
  two heatmaps: rep×platform and rep×customer, a per-rep table) via
  Recharts, styled with the existing design-system components
  (`Card`, etc.) — chart palette/accessibility per the `dataviz` skill.
- `/dashboard/manager/kams` — KAM roster table, org→KAM assignment table
  (editable), an "incoming requests" list with an assign-to-KAM control,
  and a recent audit trail. Reuses `Card`, `SelectField`, `StatusChip`,
  `EmptyState` from the existing component library.
- `/dashboard/kam` — KPI tiles (assigned count, orgs covered) + a table of
  the KAM's assigned requests; row click opens a read-only detail panel
  showing the fields that exist today (brand, market, device, total,
  status) — explicitly not the full negotiation/deliverable view, which is
  out of scope (§3).
- Nav (`Header` component) gains role-aware links so BD Manager/KAM can
  move between their dashboard sub-pages.

## 7. Error handling & testing

- Backend: role checks return a consistent `{detail}` 403 envelope
  matching the existing error shape; pytest coverage per new router
  (403 for wrong role, org-scope/cross-org visibility for `requests`
  listing, assignment round-trip, audit row written).
- Frontend: `RoleGuard` redirect behavior covered by a component test per
  role; existing manual smoke-test pattern (`docker-compose up`, log in as
  each role, confirm landing page) before considering the slice done.

## 8. Open items for the implementation plan

- Exact Recharts theming/token mapping to the Tailwind design system —
  implementation detail, not a design decision.
- Whether `/dashboard/manager` needs pagination/date-range controls on the
  charts — deferred; today's data is a fixed illustrative year, matching
  the legacy app.
