# BD Console — Organization-Level Rebuild (Design Spec)

Date: 2026-08-15
Status: Approved for planning

## 1. Background

The current BD Console (`app.py` + `data.py`) is a single-file Streamlit
prototype. It has no real backend, no database, and no real authentication:
the "gate" screen accepts any typed name/email/phone with a domain-string
check (`"@shaily." in email.lower()`) and never verifies ownership of that
email. All application data — customer requests, KAM roster, org/region
routing, audit log — lives in an in-process dict behind `st.cache_resource`,
which is shared across every user of the deployed instance and is wiped on
every redeploy or reboot. There is no tenant isolation: every visitor to the
app instance reads and writes the same shared store.

This spec covers rebuilding the console as a durable, multi-organization
(multi-tenant) application hosted on AWS, with a FastAPI backend and a
Next.js (React) frontend, replacing the Streamlit UI entirely.

## 2. Goals

- Real data durability: organization/user/request/KAM data survives
  restarts and deploys, stored in Postgres (AWS RDS).
- Tenant isolation: each customer company is its own organization; its
  users see only their own organization's data. Shaily staff (BD Manager,
  Key Account Managers) belong to one internal Shaily organization with
  cross-org visibility, matching today's KAM/org/region routing logic.
- Real authentication (deferred to the final implementation phase): email
  magic-link login, `@shaily.com` domain recognized as internal (role
  choices: BD Manager / Key Account Manager); any other domain treated as
  a customer.
- Full separation of concerns: FastAPI serves a JSON API; Next.js renders
  the UI and talks to the API over HTTPS.
- Hosted on AWS: ECS Fargate (containers) behind an ALB, RDS Postgres, S3
  for uploaded files, SES for outbound email (magic links + notifications).
- Feature parity with the current app's flows (request → platform options
  → cost & deal for customers; command centre, KAM & assignments, KAM
  workspace for Shaily staff), plus three explicitly scoped additions:
  user/role management UI, persisted file uploads, and email notifications.
- UI refined to an "organization-level" (enterprise SaaS) visual standard,
  once functionality is ported and stable.

## 3. Non-goals

- No support for multiple internal Shaily business units or fully generic
  multi-org-on-both-sides tenancy — Shaily is a single hardcoded internal
  org for this phase.
- No billing/payment processing.
- No mobile-native app — the Next.js frontend is responsive web only.
- No change to the underlying mechanism-ranking / platform-matching
  business logic beyond moving it from in-memory Python calls into a
  FastAPI service layer.

## 4. Architecture

```
┌─────────────────┐      HTTPS/JSON       ┌──────────────────┐      SQL      ┌─────────────┐
│  Next.js (React) │ ───────────────────▶ │  FastAPI backend  │ ────────────▶ │  Postgres    │
│  frontend         │ ◀─────────────────── │  (Python)          │ ◀──────────── │  (AWS RDS)   │
└─────────────────┘                       └──────────────────┘               └─────────────┘
        │                                          │
        │ static hosting (ECS Fargate)             │ SES (magic-link emails, notifications)
        ▼                                          │ S3 (uploaded drawings/packages)
   AWS ALB                                          ▼
                                             AWS Cognito or custom
                                             magic-link auth (final phase)
```

- **Frontend**: Next.js (React), containerized, deployed to ECS Fargate.
  Calls the FastAPI backend over HTTPS/JSON. Holds no business logic beyond
  presentation and client-side validation.
- **Backend**: FastAPI, containerized, deployed to ECS Fargate. Owns all
  business logic: mechanism/platform ranking (ported from `data.py`),
  request/cost calculation, KAM routing/assignment, audit logging, org
  scoping.
- **Database**: PostgreSQL on AWS RDS. Single database, tables scoped by
  `org_id` for isolation.
- **File storage**: S3, for uploaded drawings/packages (currently
  `st.file_uploader` widgets that discard their contents).
- **Email**: AWS SES, for magic-link login emails (final phase) and
  notifications (request submitted, KAM assigned, schedule/drawings
  pushed).
- **Hosting**: ECS Fargate for both frontend and backend containers, behind
  an Application Load Balancer, in one VPC alongside the RDS instance.

## 5. Data model

All tables that hold customer-facing data carry an `org_id` foreign key to
`organizations`.

- `organizations` — id, name, kind (`internal` | `customer`), domain (for
  email-domain-based routing).
- `users` — id, org_id, email, name, role, phone, created_at.
- `kams` — id, name, login_email, active. (Shaily-internal; not org-scoped
  the same way — visible to the internal org only.)
- `region_kam_map`, `org_kam_map` — routing tables, replacing
  `ss.region_map` / `ss.org_map`.
- `requests` — id, org_id (customer org), submitted_by (user id), brand,
  market, device, submission fy/quarter, chosen_option, budget totals,
  status, assigned_kam_id, created_at. Replaces the shared-store `dict`.
- `sku_rows` — request_id, strength, cartridge, fill_ml.
- `service_selections` — request_id, sku_row_id, standard_dv, threshold,
  ifu, human_factor.
- `deliverables` / `schedule_items` — request_id, item, fy_quarter,
  responsibility, status, component revisions, change-control ref.
  Replaces today's ephemeral per-widget `st.session_state` keys (`dl_{i}_*`).
- `uploaded_files` — id, request_id or deliverable_id, s3_key, filename,
  uploaded_by, uploaded_at.
- `audit_log` — id, org_id, actor, action, detail, created_at.
- Reference data (seeded from `data.py`, no longer Python constants):
  `reference_products`, `product_variants` (per-market RLD data),
  `platform_sheet`, `service_pricing`, `deliverable_templates`.

Row-level isolation: every query issued on behalf of a customer-org user is
filtered by that user's `org_id`. Shaily-side users (BD Manager, KAM) query
across customer orgs per the existing region/org → KAM routing logic,
enforced in the backend service layer, not left to the frontend.

## 6. Authentication

- **Dev-stage (all phases prior to the final cutover)**: a mock login
  endpoint reproducing today's gate UX — user enters name + email; domain
  is checked against `@shaily.com` to decide role options (internal vs.
  customer). No real ownership verification. Issues a real session
  token (JWT or opaque session id) so the rest of the stack — API auth
  middleware, React auth state, protected routes — is built against the
  real token-based mechanism from day one rather than against a stub that
  gets thrown away.
- **Final stage**: swap the mock endpoint's implementation for real
  **magic-link email login via SES**. User enters their email; if it ends
  `@shaily.com`, they're offered the BD Manager / Key Account Manager role
  choice as today; otherwise they're routed as a customer. A single-use,
  expiring link is emailed via SES; clicking it verifies ownership and
  issues the same session token used throughout development. This is a
  backend-only swap — no frontend rework, since the frontend already
  consumes a token issued by a login endpoint.

## 7. Scoped additions (the "few more modifications")

- **User/role management UI**: admin screens (for the BD Manager role and,
  within a customer org, presumably an org admin) to invite, edit role,
  and deactivate users — beyond today's KAM-only add/remove.
- **File upload persistence**: today's `file_uploader` widgets for
  component drawings and deliverable packages don't persist anywhere;
  wire them to S3 with metadata rows in `uploaded_files`.
- **Email notifications** (via SES): on request submission, KAM
  assignment, and schedule/drawing pushes — replacing today's in-app-only
  `st.success` messages, which no one sees unless they're looking at the
  screen at that moment.

## 8. Build sequence (thin vertical slice first)

Chosen over "layer by subsystem" specifically to surface AWS
deploy/integration problems (CORS, auth token wiring, container
networking, CI/CD) early, rather than after every feature is built on an
unproven foundation.

1. **Foundation slice** — FastAPI skeleton (health check + mock login) +
   Postgres schema (core tables only) + Next.js skeleton (login page +
   one form) → submit a request → confirm it lands in Postgres → deploy
   the whole pipeline to AWS (ECS Fargate + RDS) end-to-end. Nothing else
   proceeds until this slice runs in AWS, not just locally.
2. **Port core customer flow** — request form → platform options → cost &
   deal, backed by real API calls and DB rows. Mechanism-ranking and
   pricing logic from `data.py` moves into a FastAPI service module.
3. **Port BD dashboards** — Manager command centre (KPIs/charts), KAM &
   assignments admin, KAM workspace — all org-scoped and DB-backed,
   replacing `shared_store()`.
4. **Scoped additions** — user/role management UI, S3 file upload
   persistence, SES email notifications.
5. **UI refinement pass** — organization-level visual polish across all
   ported screens, once functionality is stable and stops moving.
6. **Real auth cutover** — magic-link + SES, final end-to-end testing
   against the real flow, `@shaily.com` domain gating confirmed live.

## 9. Error handling & testing

- FastAPI: Pydantic request/response models throughout; a consistent
  error envelope (status, code, message) for all failures; org-scope
  enforcement centralized in a shared FastAPI dependency injected into
  every data-access route, not re-implemented per route.
- Backend testing: pytest coverage per router, exercising org-isolation
  (a user from org A must never be able to read/write org B's rows).
- Frontend testing: component/integration tests for the core flows
  (login, request submission, dashboard rendering).
- CI smoke tests: the intent of today's `_verify.py` / `_verify_kam.py` /
  `_verify_mechanism.py` (headless functional checks) carries forward as
  API-level smoke tests run in CI before each deploy.

## 10. Open items for the implementation plan

- Exact session/token mechanism (JWT vs. opaque token + server-side
  session store) — to be decided in planning, doesn't change this design.
- Whether customer-org "admin" is a distinct role or the first user of an
  org by default — to be decided when building user/role management
  (§7).
- AWS account/VPC/networking specifics (existing account? new one?
  subnet layout) — infra details for the planning phase, not a design
  decision.
