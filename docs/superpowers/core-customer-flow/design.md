# Core Customer Flow — Request → Platform Options → Cost & Deal (Design Spec)

Date: 2026-08-16
Status: Approved for planning

## 1. Background

This is step 2 of the build sequence in
[`2026-08-15-org-level-rebuild-design.md`](2026-08-15-org-level-rebuild-design.md):
"Port core customer flow — request form → platform options → cost & deal,
backed by real API calls and DB rows. Mechanism-ranking and pricing logic
from `data.py` moves into a FastAPI service module." Step 1 (foundation
slice) and a stub of step 2 are already done: a customer can log in and
submit a bare request (brand + market only, no SKUs, no platform matching,
no cost calculation) and see their own org's requests. Step 3 (BD
dashboards) is already built and currently reads/displays only that bare
shape (`brand`, `market`, `device`, `status`, `total`).

The legacy Streamlit app (`app.py` / `data.py`) has a working, three-screen
reference implementation of this flow:

1. **Request form** (`screen_form`) — reference-product brand + target
   market select, strength(s)/SKU multiselect, viscosity (with a
   literature-value auto-fill), device type (auto from the reference
   product, or a "differentiated formulation" override), and an editable
   cartridge/fill-mL table (one row per SKU).
2. **Platform options** (`screen_options`) — each SKU is ranked against
   Shaily's platform sheet by mechanism closeness to the reference
   device (a weighted archetype/drive/dose similarity score, viscosity-aware),
   producing three ranked option sets; the customer picks one.
3. **Cost & deal** (`screen_cost`) — per-SKU service selection (Standard
   DV always on; Threshold / IFU / Human Factor optional), a computed DV
   package price (governed by change severity — minor/moderate/major —
   and SKU count), a tentative total, a comment field, an urgency pick,
   and a final "Submit to Shaily BD" action.

This spec ports that flow's *behavior* faithfully — same ranking algorithm,
same pricing formulas, same screens — onto the real backend/DB, with one
addition beyond the legacy app: **draft persistence**. The legacy app keeps
all of this in Streamlit session state until the final submit; a customer
who navigates away mid-form loses everything. This rebuild persists a draft
from step 1 onward, so a request can be resumed later or from another
session.

## 2. Goals

- A customer can start a request, move through all three screens, and
  either finish (submit to the Shaily BD desk) or leave and resume later
  — the in-progress request is a real, durable row from the first screen
  on.
- Platform-option ranking and pricing are computed by a backend service
  using the exact algorithm and formulas from `data.py`, operating over
  reference/platform data now seeded in Postgres rather than Python
  constants.
- The existing `/requests` list (and the BD Manager/KAM views built in the
  dashboards work) continue to work unmodified in shape — this spec adds
  fields and child data, it does not change how `requests.list` visibility
  is scoped by role.
- Feature parity with the legacy app's three screens, including the
  viscosity auto-fill, the differentiated-device override, and the
  editable per-SKU cartridge/fill table.

## 3. Non-goals

- **No `sub_fy`/`sub_q`/`dossier_fy` (submission FY/quarter, dossier FY).**
  These exist in the legacy app only as hardcoded session-state defaults
  (`"FY26"`, `"Q3"`, `"FY27"`) — no screen anywhere lets a customer set
  them; every request silently gets the same values. There is nothing
  working to port. Confirmed with the user: left out entirely rather than
  inventing a UI that never existed, matching how region-based KAM routing
  was handled in the previous slice.
- **No deliverable/drawing schedule, no cost negotiation UI.** Those are
  the KAM-workspace "tier B" features explicitly deferred in the BD
  Manager & KAM dashboards spec (§3), pending this slice landing first.
  This spec produces the request data those features will eventually read
  and mutate, but doesn't build them.
- **No file uploads.** The legacy app's `st.file_uploader` widgets for
  component drawings discard their contents; that's the parent spec's
  "scoped addition" for a later phase (S3 + `uploaded_files`), not this
  one.
- **No change to the ranking/pricing math.** This is a straight port of
  `mechanism_similarity`, `rank_platforms_for_sku`, and the DV/threshold/
  IFU/human-factor cost formulas — no new business logic, no algorithm
  tuning.
- **No multi-draft limit.** A customer may have any number of draft
  requests in progress at once — each is its own row, ordinary REST
  resource semantics, no artificial "only one draft" constraint (simpler
  than special-casing it, and the legacy app's single-in-memory-form
  behavior was an artifact of Streamlit session state, not a deliberate
  product rule).

## 4. Data model

New Alembic migration, additive only.

**`requests` gains:**
- `viscosity_val` — nullable numeric, the customer-entered or
  auto-filled viscosity (cP).
- `differentiated` — boolean, default `false`. Whether the customer
  overrode the auto-selected device type.
- `chosen_option` — nullable integer (1–3). Which ranked option set the
  customer picked in step 2.
- `severity`, `timeline_months` — set once step 3 is saved (`"minor"` /
  `"moderate"` / `"major"`, and the corresponding month count) —
  denormalized onto the row so the KAM/Manager views don't need to
  recompute them from `service_selections` every time.
- `comment`, `urgency` — nullable text / string, captured on step 3.
- `status` gains `"Draft"` as the initial value (currently defaults to
  `"Awaiting assignment"`, which becomes the value `submit` transitions
  into — see §5).

**New tables:**
- `sku_rows` — `id`, `request_id` (FK), `strength` (string), `cartridge`
  (string), `fill_ml` (numeric). One row per SKU on the request, editable
  while the request is a draft.
- `service_selections` — `id`, `sku_row_id` (FK), `standard_dv`,
  `threshold`, `ifu`, `human_factor` (all boolean). One row per SKU,
  written on step 3.

**Reference data (seeded via migration, matching the `dashboard_metrics`
precedent — real relational tables where the data is genuinely queried by
the ranking algorithm, one JSON blob where it's just read whole):**
- `reference_products` — one row per legacy `REFERENCE_PRODUCTS` entry
  (`brand` PK, `molecule`, `device`, `dose`, `visc`, `visc_val`,
  `cartridge`, `strengths` JSON array, `visc_ref`, `mech_drive`,
  `mech_dose`, `mech_label`, `ob_ref`, `ob_claims` JSON array).
- `reference_product_markets` — one row per legacy `MARKET_VARIANTS`
  entry (`brand` FK, `market`, override columns nullable — only present
  where the legacy data actually overrides the base profile — `market_note`
  , `presentations` JSON keyed by strength, `pres_ref`). Today only
  `(Wegovy, EU)`, `(Wegovy, Canada)`, `(Mounjaro, EU)`,
  `(Mounjaro, Canada)` have rows; everything else falls back to the base
  `reference_products` row, exactly matching `variants_for()`'s merge
  behavior.
- `platform_sheet` — one row per legacy `PLATFORM_SHEET` entry (`variant`
  PK, `family`, `cls`, `sub`, `resolution`, `lockout`, `carts` JSON array,
  `mech`, `color`, `moderate` boolean).
- `service_pricing` — one seeded JSON blob (same shape as
  `dashboard_metrics`: `key` PK, `payload` JSON), holding `PKG`
  (governing-DV cost by severity), `ADD_DV`, `TIMELINE`,
  `SEV_LABEL`/`SEV_LOGIC`, `SERVICES` (threshold/IFU/human-factor unit
  costs), and `STD_CONDITION_TESTS` — a handful of scalar constants read
  as a whole, not queried relationally, so one blob rather than six narrow
  tables.

## 5. Backend

New service module `app/services/platform_matching.py` — a direct port of
`mechanism_similarity`, `platform_max_visc`, and
`rank_platforms_for_sku` from `data.py`, operating on `PlatformSheet`/
`ReferenceProduct` ORM rows instead of dicts. Same weights (`W_ARCH=0.5,
W_DRIVE=0.3, W_DOSE=0.2`), same band thresholds (`BAND_CLOSE=0.80,
BAND_SIMILAR=0.50`), same drive-adjacency table, same viscosity soft-penalty
(`×0.5` when a platform's max viscosity capability is exceeded).

`app/routers/requests.py` gains, all requiring `get_current_user` and an
ownership check (`submitted_by == current_user.id`, not just
org-scoping — a request stays private to the customer who started it until
it's submitted and visible to BD Manager/KAM per the existing role-scoping):

- `POST /requests` (extended) — body now includes `strengths` (list, used
  to create `sku_rows` with cartridge/fill defaulted from
  `reference_product_markets`/`reference_products`), `viscosity_val`,
  `device`, `differentiated`. Creates the row with `status = "Draft"`.
- `PUT /requests/{id}` — edits step-1 fields on an existing draft. 404 if
  not found or not owned by the caller; 409 if `status != "Draft"`. Body
  carries the full step-1 shape (`brand`, `market`, `strengths`,
  `viscosity_val`, `device`, `differentiated`, and a `sku_rows` list of
  `{strength, cartridge, fill_ml}`); the endpoint replaces the draft's
  entire `sku_rows` set with the submitted list rather than diffing it —
  the frontend always sends the full current table, matching how the
  legacy app's editable `data_editor` re-derives all rows from
  `ss.strengths` on every change. Changing `brand`/`market`/`strengths`
  additionally cascades: `chosen_option`, `severity`, `timeline_months`
  are cleared and any existing `service_selections` rows are deleted —
  mirroring the legacy app's `_reset_for_rld`, since a changed reference
  product invalidates everything downstream.
- `GET /requests/{id}/platform-options` — stateless compute: reads the
  draft's `sku_rows`, calls `platform_matching.rank_platforms_for_sku`
  per row against the seeded `platform_sheet`, returns the three ranked
  option tables. Nothing persisted here.
- `POST /requests/{id}/select-option` — body `{chosen_option: 1|2|3}`.
  409 if `status != "Draft"`.
- `PUT /requests/{id}/services` — body: per-SKU
  `{sku_row_id, standard_dv, threshold, ifu, human_factor}[]`, plus
  `comment`, `urgency`. Computes `severity` (moderate if any selected
  platform is flagged `moderate` in `platform_sheet`, or if the chosen
  option includes a fallback/divergent-band platform; minor otherwise —
  same logic as the legacy app), looks up `service_pricing`, computes
  `dv_usd`/`thr`/`ifu`/`hf`/`total` and `timeline_months`, writes
  `service_selections` rows and the computed fields onto `requests`. 409
  if `status != "Draft"` or `chosen_option` is unset.
- `POST /requests/{id}/submit` — 422 if `chosen_option` is unset or no
  `service_selections` exist; otherwise flips `status` from `"Draft"` to
  `"Awaiting assignment"`. From this point, `PUT`/`select-option`/
  `services` all 409 — the draft is locked, matching "cost editing and
  negotiation are handled by your assigned Shaily KAM" from the legacy
  copy.
- `GET /requests/{id}` — full detail (all fields + `sku_rows` +
  `service_selections`), for resuming a draft or reviewing a submitted
  request. Same ownership/role rules as `list_requests`.
- `list_requests` (existing) — unchanged scoping logic; response shape
  gains the new top-level fields (`viscosity_val`, `differentiated`,
  `chosen_option`, `severity`, `timeline_months`, `comment`, `urgency`)
  but is otherwise untouched. `create_request`'s existing customers-only
  path continues to default `total = 0` until step 3 computes a real
  value.

## 6. Frontend

- `/requests` — becomes the list of both drafts and submitted requests for
  the logged-in customer (reusing the existing role-scoped `list_requests`
  call, `StatusChip`, `EmptyState`). A draft row gets a "Continue" action
  routing to `/requests/{id}`; a submitted row is read-only (links to the
  same page in a locked view). The inline "New request" form currently on
  this page is replaced by a "New request" button that `POST /requests`
  with just `brand`+`market` (minimal step-1 shell) and redirects to
  `/requests/{id}`.
- `/requests/[id]` — the three-step wizard, gated by `useRoleGuard
  ("Customer")` plus an ownership check (redirect to `/requests` if the
  draft isn't the logged-in user's). Segmented nav across the three
  steps mirrors the legacy app's (`PHARMA_STEPS`), reusing `Card`,
  `TextField`, `SelectField`, `Banner`:
  - **Step 1 — Request form**: reference-product/market selects
    (populated from `GET /reference-products` — a small new read-only
    endpoint listing seeded brands, used to drive the frontend's select
    options and per-brand/market defaults), strength multiselect, editable
    cartridge/fill table (one row per SKU), viscosity field with a "Need
    assistance" auto-fill button, device type with the differentiated
    override toggle. Saves via `PUT /requests/{id}`.
  - **Step 2 — Platform options**: fetches `GET
    /requests/{id}/platform-options`, renders the three ranked option
    tables (SKU × platform, band, fallback flag), "Select Option N"
    buttons call `POST /requests/{id}/select-option` and advance to step
    3.
  - **Step 3 — Cost & deal**: per-SKU service checkboxes (Standard DV
    locked on, Threshold/IFU/Human Factor optional), a live-computed
    total (recomputed client-side for immediate feedback, authoritative
    total comes from the `PUT /requests/{id}/services` response),
    comment textarea, urgency picker, "Submit request to Shaily BD"
    button calling `POST /requests/{id}/submit` and redirecting to
    `/requests` with a success banner.
- A submitted (non-Draft) request opens `/requests/[id]` in a read-only
  rendering of all three steps' data (no editable controls, no step nav) —
  reuses the same page/data-fetch, branches on `status !== "Draft"`.

## 7. Error handling & testing

- Backend: 409 on any mutation attempted against a non-Draft or
  not-owned request; 404 vs 403 follows the existing pattern (`get_current
  _user` 401, ownership mismatch 404 — not 403, to avoid confirming a
  request id exists to a non-owner, consistent with not leaking
  cross-tenant existence). pytest coverage per new endpoint: the
  happy-path wizard flow end-to-end (create → edit → options → select →
  services → submit), the cascade-reset on step-1 edit, the lock-after-
  submit 409s, and ownership 404s. `platform_matching` gets direct unit
  tests against known (RLD, platform) pairs with expected scores/bands,
  ported from the legacy algorithm's own logic (not re-derived).
- Frontend: no test framework in this repo (unchanged constraint) —
  verification is `npm run build` plus a manual/curl smoke walkthrough of
  the full wizard, the same pattern used for the dashboards slice.

## 8. Open items for the implementation plan

- Exact `GET /reference-products` response shape (brand list + per-brand
  metadata needed to drive step-1 selects) — implementation detail.
- Whether the cartridge/fill table on step 1 needs inline validation
  beyond "cartridge must be one of `CART_SIZES`" (matching the legacy
  `SelectboxColumn`) — deferred to planning.
