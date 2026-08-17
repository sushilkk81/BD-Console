# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two apps in this repo — know which one you're touching

- **`backend/` + `frontend/`** — the active rebuild. FastAPI (Python) API + Next.js (React) frontend, Postgres-backed, multi-tenant. This is where new feature work happens.
- **`app.py`, `data.py`, `_verify*.py`, `.streamlit/`, `requirements.txt` at the repo root** — the original Streamlit prototype ("Shaily DDCP Console"). It has no real backend, no database, and no real auth (an in-process dict behind `st.cache_resource`, wiped on every restart). It is being **replaced**, not maintained — see `docs/superpowers/specs/2026-08-15-org-level-rebuild-design.md` for the full rationale. Business logic here (mechanism/platform ranking, KAM routing, cost/pricing) is the reference to port from, not a place to add features.

Don't add features to the Streamlit app. Don't assume `backend`/`frontend` code ports 1:1 from `app.py`/`data.py` without checking the design docs first — several past decisions deliberately dropped or reshaped pieces of the original (e.g. region-based KAM routing was intentionally *not* ported; it was dead code in the original).

## Commands

### Backend (`backend/`)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run the full test suite (SQLite in-memory, no Postgres needed)
PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test \
  CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest -v

# Single test
PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test \
  CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_kams.py::test_assign_kam_updates_request_status -v

# New Alembic migration
.venv/bin/alembic revision -m "description"
```

All backend tests override `get_db` with an in-memory SQLite session (see any `tests/test_*.py` for the fixture pattern) — no live Postgres required for the suite. SQLite does not enforce `VARCHAR` length limits the way Postgres does; be explicit about truncating user-derived strings before writing them into length-limited columns (`Request.status` is 50 chars, `AuditLog.detail` is 500) since the test suite can't catch an overflow there.

### Frontend (`frontend/`)

```bash
npm install
npm run dev      # local dev server, needs API_URL env var pointing at the backend
npm run build     # also runs typecheck — this is the standard "did I break anything" check; no test framework is configured
```

There is **no frontend test framework** (no jest/vitest, no `*.test.*` files) — this is deliberate, not a gap to silently fill in. Frontend correctness is verified via `npm run build` (TypeScript) plus manual/curl smoke testing.

### Full stack (Docker)

```bash
docker-compose up -d --build              # postgres + backend (runs `alembic upgrade head` on boot) + frontend
docker-compose run --rm backend alembic upgrade head   # apply migrations manually if needed
```

`frontend`'s container gets `API_URL=http://backend:8000`; the Next.js API proxy (`frontend/app/api/[...path]/route.ts`) needs this server-side env var to reach the backend — if it's unset, every `/api/*` call 500s with `"API_URL is not configured"` before reaching the backend at all. Locally outside Docker, set `API_URL` in the frontend's environment when running `next dev`/`next start`.

## Architecture

### Multi-tenancy and roles

Every customer company is its own `Organization` (`kind = "customer"`); Shaily staff belong to a single hardcoded internal org (`kind = "internal"`, `domain = "shaily.com"`). A user's role comes from email domain at login (`backend/app/routers/auth.py`): `@shaily.com` → the user picks `BD Manager` or `Key Account Manager`; anything else → `Customer`. Auth today is a **mock login** — name + email only, no ownership verification, real magic-link auth is a later phase (see the org-level-rebuild spec). `get_current_user` (`backend/app/deps.py`) decodes a JWT issued at login; `require_role(*roles)` wraps it to 403 when the caller's role isn't in the allowed set.

**Key Account Managers are not a separate roster** — they're `users` rows with `role = "Key Account Manager"`, self-provisioned by logging in. There is deliberately no add/remove-KAM admin action.

Row-level isolation is enforced per-endpoint, not centrally: `backend/app/routers/requests.py`'s `list_requests` branches on `current_user.role` — `Customer` stays filtered to their own `org_id`; `BD Manager` sees every customer org (`org_id != <the Shaily org's own id>`); `Key Account Manager` sees only `assigned_kam_id == self`. `serialize_requests` (same file) has an `include_routing` flag that must be `False` on any customer-facing response path — it gates `suggested_kam_id`/`suggested_kam_name` (internal KAM-routing metadata) out of what customers can see. When adding a new request-scoped endpoint, follow this pattern rather than trusting a single shared query.

KAM assignment is **org→KAM only** — routed via the `org_kam_map` table (`org_id` → `kam_user_id`), set by a BD Manager. Region-based routing was in the original Streamlit app but was dead code there (region was never actually collected) and was deliberately not ported.

### Request review workflow

Past `assign-kam`, a request moves through a second state machine — still one
literal `status` string per handoff, same convention as `"Assigned to
{kam.name}"`: `KAM Assessment Submitted` → (BD Manager) `Approved — Awaiting
KAM Response` or `Revision Requested` (loops back for a new KAM assessment) →
`Responded to Customer` ⇄ `Customer Query` (customer asks, KAM answers, any
number of rounds). The KAM's `kam_cost_usd`/`kam_timeline_months`/`kam_notes`
on `Request` are additive to the customer's own auto-computed
`total`/`timeline_months`/`severity` from the cost & deal step — never a
replacement.

`request_messages` backs two logical threads via its `channel` column:
`"internal"` (BD Manager ↔ KAM revision notes, invisible to the customer) and
`"customer"` (KAM ↔ Customer, readable but not postable by the BD Manager).
`POST /requests/{id}/messages` branches on `current_user.role` to enforce
who can post where; `GET /requests/{id}/messages` reuses `_visible_or_404`
(the same role-scoped read as `GET /requests/{id}`) and then filters the
`internal` channel out for a Customer caller.

No PDF "scope note" export yet — deferred pending an agreed template (see
`docs/superpowers/specs/2026-08-17-request-review-workflow-design.md` §8);
every field it would need already lives in a structured column.

### Backend layout (`backend/app/`)

- `models.py` — SQLAlchemy models. `organizations`, `users`, `requests` (core); `org_kam_map`, `audit_log`, `dashboard_metrics` (KAM routing + dashboards, added in migration `0002`).
- `routers/auth.py`, `routers/requests.py`, `routers/kams.py`, `routers/dashboard.py` — one router per resource, all mounted in `main.py`.
- `deps.py` — `get_current_user`, `require_role`.
- `schemas.py` — all Pydantic request/response models in one file.
- `dashboard_metrics` is seeded reference data (illustrative business-metric figures, e.g. quarterly targets, per-rep numbers) ported verbatim from the Streamlit app's `data.py` — it is not computed from real deals. `GET /dashboard/metrics` merges these seeded payloads with a live count computed from the real `requests` table.

### Frontend layout (`frontend/`)

Next.js App Router. `app/api/[...path]/route.ts` is a catch-all proxy forwarding every `/api/*` call to the backend's `API_URL` — the frontend's own API routes never talk to Postgres directly.

Role-based landing and route protection is client-side, via `useRoleGuard(role)` (`lib/session.ts`), matching the mock-auth trust model (role trusted from `localStorage`, no server session): each dashboard page calls `useRoleGuard("BD Manager" | "Key Account Manager" | "Customer")`, which redirects to the correct role's landing page (`LANDING` map, same file) if the stored user's role doesn't match. Post-login redirect in `app/login/page.tsx` uses the same `LANDING` map. `components/Header.tsx` renders role-specific nav links from its own `NAV` map — kept in sync with `lib/session.ts`'s `Role` type by hand, not by a shared import.

Shared UI primitives live in `components/` (`Card`, `Button`, `TextField`, `SelectField`, `Banner`, `StatusChip`, `EmptyState`, `Skeleton`, `Heatmap`) — reuse these rather than building new ad hoc markup; the visual design system (Tailwind v4 tokens: `forest`/`lime`/`orange`/`ink`/`sand` colors, `font-display`/`font-body`/`font-mono`) is defined in `app/globals.css`.

### Docs

`docs/superpowers/specs/` and `docs/superpowers/plans/` hold the design specs and implementation plans this rebuild has been built from, in date order. `2026-08-15-org-level-rebuild-design.md` is the top-level spec (goals, data model, auth strategy, and the phased build sequence the whole rebuild follows); the dated files after it are specs/plans for individual slices. Check these before assuming a feature is unbuilt or out of scope — they record what was deliberately deferred and why.

### Infra

`infra/terraform/` defines ECR/RDS/ECS Fargate/ALB for an AWS deployment, but as of this writing it has never been applied (no state, no CI/CD pipeline) — nothing described there is actually running in AWS yet.
