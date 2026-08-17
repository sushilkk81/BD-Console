# Request Review Workflow — KAM Assessment, BD Manager Review, Customer Query Thread (Design Spec)

Date: 2026-08-17
Status: Approved for planning

## 1. Background

Steps 1–3 of the build sequence in
[`2026-08-15-org-level-rebuild-design.md`](2026-08-15-org-level-rebuild-design.md)
are done: foundation slice, core customer flow (request → platform options →
cost & deal), and BD dashboards (command centre, KAM roster/assignment, KAM
workspace) are all merged. Today the request lifecycle stops the moment a
BD Manager assigns a KAM — `status` becomes `"Assigned to {kam.name}"` and
nothing else happens. There is no KAM assessment step, no BD Manager
re-review, no handoff back to the customer, and no way for the customer to
ask a question once a request has moved past their own submission.

This spec adds the rest of the lifecycle the business actually runs:
KAM reviews an assigned request in detail and submits a cost/timeline
assessment → BD Manager reviews that assessment (approve, or send back for
revision with a note) → once approved, KAM adds their own comments and
responds to the customer → the customer can ask further questions, which
only the KAM (not the BD Manager) answers, in an ongoing back-and-forth.
The BD Manager can see the customer-facing query thread but never posts to
it.

This is scoped as its own slice — decomposed out of the org-rebuild spec's
step 4 ("scoped additions"), which bundled it with user/role management and
file/email infrastructure that don't share a data model or UI surface with
this workflow. Those remain separate, later slices.

## 2. Goals

- KAM can submit a cost/timeline assessment (separate from the customer's
  own auto-computed `total`/`timeline_months` from the cost & deal step) on
  a request assigned to them.
- BD Manager can review a submitted assessment and either approve it or
  send it back to the KAM with a revision note — an internal exchange the
  customer never sees.
- Once approved, the KAM sends a final response to the customer (their own
  comments plus the assessment).
- The customer can ask further questions on a responded request; only the
  KAM answers. The BD Manager can read this exchange but not post to it.
- Every handoff is visible in each role's existing request list via
  `status`, matching the existing one-state-per-handoff pattern (e.g.
  `"Assigned to {kam.name}"`).

## 3. Non-goals

- No PDF "scope note" export. The business wants one eventually, but its
  template is still under discussion — deferred to a later slice. This
  design keeps the door open for it (see §8) without building it now.
- No notification/email delivery for status changes or new messages (SES
  integration is its own deferred slice per the org-rebuild spec's step 4).
- No editing or deleting messages once posted — the thread is append-only,
  matching the `AuditLog` pattern already used elsewhere in this app.
- No re-opening a request after the customer stops asking questions —
  there's no explicit "close" action; `Responded to Customer` /
  `Customer Query` is the terminal pair of states this slice reaches.
- No changes to the existing cost & deal step's own `total` /
  `timeline_months` / `severity` fields — those stay exactly as the
  customer's own auto-computed figures; the KAM's assessment is additive,
  not a replacement.

## 4. Data model

Three new columns on `requests`, and one new table.

**`requests` — new columns:**
- `kam_cost_usd` — `Numeric(12, 2)`, nullable. KAM's assessed cost.
- `kam_timeline_months` — `Integer`, nullable. KAM's assessed timeline.
- `kam_notes` — `Text`, nullable. KAM's assessment rationale, shown to the
  BD Manager during review (and, distinct from `request_messages`, not
  itself a message — it's the assessment's own free-text field, editable
  each time the KAM (re)submits an assessment).

These are set together by the assessment-submit endpoint and are editable
only while `status` is `"Assigned to {kam.name}"` or `"Revision Requested"`.

**`request_messages` — new table:**

| column | type | notes |
|---|---|---|
| `id` | Integer PK | |
| `request_id` | Integer FK → `requests.id` | |
| `channel` | `String(20)` | `"internal"` or `"customer"` |
| `sender_user_id` | Integer FK → `users.id` | |
| `body` | `String(2000)` | matches `requests.comment`'s existing width |
| `created_at` | DateTime | default `utcnow` |

Two logical threads share this one table, distinguished by `channel`:
- **`internal`** — BD Manager ↔ KAM. Carries the BD Manager's revision
  notes and any KAM reply. The customer never sees this channel.
- **`customer`** — KAM ↔ Customer. Carries the KAM's final response, the
  customer's queries, and the KAM's answers. The BD Manager can read this
  channel but has no write access to it.

Append-only — no update/delete endpoint, same convention as `AuditLog`.

## 5. Status state machine

One literal status string per handoff, continuing the existing pattern
(`"Draft"`, `"Awaiting assignment"`, `"Assigned to {kam.name}"`):

```
Draft
  → Awaiting assignment                    (existing: POST /requests/{id}/submit)
  → Assigned to {kam.name}                 (existing: POST /requests/{id}/assign-kam)
  → KAM Assessment Submitted               (new: POST /requests/{id}/kam-assessment)
  → [BD Manager decision]
      → Revision Requested                 (new: POST /requests/{id}/bd-review, decision="revise")
          → KAM Assessment Submitted       (KAM resubmits: POST /requests/{id}/kam-assessment)
      → Approved — Awaiting KAM Response   (new: POST /requests/{id}/bd-review, decision="approve")
          → Responded to Customer          (new: POST /requests/{id}/respond-to-customer)
              ⇄ Customer Query             (new: POST /requests/{id}/messages, channel="customer")
                (customer posts → Customer Query; KAM posts → Responded to Customer)
```

`Revision Requested` → `KAM Assessment Submitted` is the one loop; the
customer query/answer pair (`Responded to Customer` ⇄ `Customer Query`) is
the other, and can repeat indefinitely.

## 6. API

All new endpoints live in `backend/app/routers/requests.py`, following the
existing ownership/role patterns (404 — not 403 — on a mismatch, to avoid
confirming a request id exists to the wrong caller; 409 on a status-gated
mutation attempted from the wrong state).

- **`POST /requests/{id}/kam-assessment`** — role: Key Account Manager,
  must be the request's `assigned_kam_id` (404 otherwise). Requires
  `status` in `{"Assigned to {kam.name}", "Revision Requested"}` (409
  otherwise). Body: `{kam_cost_usd, kam_timeline_months, kam_notes}`. Sets
  those three fields, `status` → `"KAM Assessment Submitted"`.

- **`POST /requests/{id}/bd-review`** — role: BD Manager. Requires
  `status == "KAM Assessment Submitted"` (409 otherwise). Body:
  `{decision: "approve" | "revise", note: Optional[str]}` — `note` required
  when `decision == "revise"` (422 otherwise). On `"approve"`: `status` →
  `"Approved — Awaiting KAM Response"`. On `"revise"`: inserts `note` into
  `request_messages` (`channel="internal"`, `sender_user_id=current_user.id`),
  `status` → `"Revision Requested"`.

- **`POST /requests/{id}/respond-to-customer`** — role: Key Account
  Manager, must be `assigned_kam_id`. Requires
  `status == "Approved — Awaiting KAM Response"` (409 otherwise). Body:
  `{message: str}`. Inserts into `request_messages`
  (`channel="customer"`), `status` → `"Responded to Customer"`.

- **`POST /requests/{id}/messages`** — body: `{channel: "internal" |
  "customer", body: str}`.
  - Customer (must be `submitted_by`): may only post `channel="customer"`,
    only when `status` in `{"Responded to Customer", "Customer Query"}`
    (409 otherwise). Sets `status` → `"Customer Query"`.
  - Key Account Manager (must be `assigned_kam_id`): may post to either
    channel. Posting `channel="customer"` while `status ==
    "Customer Query"` sets `status` → `"Responded to Customer"`; posting
    `channel="internal"` doesn't change `status`.
  - BD Manager: 403 — read-only, no write access to either channel via
    this endpoint.

- **`GET /requests/{id}/messages`** — role-scoped read, same ownership
  rule as `GET /requests/{id}` (spec for core customer flow, §5): Customer
  sees `channel="customer"` only; Key Account Manager and BD Manager see
  both channels.

`RequestOut`/`RequestDetailOut` gain `kam_cost_usd`, `kam_timeline_months`,
`kam_notes` (nullable, always present in the response — no separate
`include_routing`-style gating, since none of the three reveal internal
KAM-routing metadata the way `suggested_kam_id` does).

## 7. Frontend

- **KAM workspace** (`/kam` or wherever the existing assigned-requests
  list lives): each assigned request's detail view gains an assessment
  form (cost, timeline, notes) when status allows submission, and — once
  `Revision Requested` — displays the BD Manager's internal note inline.
  After approval, a "Respond to customer" composer appears.
- **BD Manager**: the KAM & assignments admin screen (or a new review
  queue filtered to `KAM Assessment Submitted`) gains an approve /
  send-back-with-note action, plus a read-only view of both message
  channels on any request they can already see.
- **Customer** (`/requests/[id]`): once `status` is `Responded to
  Customer` or `Customer Query`, the page shows the KAM's response and a
  query composer, plus the running `customer`-channel thread.

No new frontend test framework — verification stays `npm run build` +
manual/curl smoke testing, per this repo's existing convention.

## 8. Deferred: PDF scope-note export

The business wants a "scope note" document (cost, timeline, assessment
details) exportable as a PDF once a request reaches some later stage of
this workflow. Its template is still under discussion, so it's out of
scope for this slice — but the data model here is written so it slots in
later without rework: every field a scope note would need
(`kam_cost_usd`, `kam_timeline_months`, `kam_notes`, the `customer`-channel
message history, plus the existing SKU rows / chosen platform / severity /
timeline from the core customer flow) already lives in structured columns
on `requests` / `sku_rows` / `request_messages` — nothing free-text or
computed-client-side. A future `GET /requests/{id}/scope-note.pdf` endpoint
can read this data directly once a template is agreed; no schema change
anticipated.

## 9. Error handling & testing

- Same error envelope and 404-not-403 / 409-on-bad-status conventions as
  the rest of `requests.py` (see core customer flow spec §5, org-rebuild
  spec §9).
- Backend: pytest per new endpoint — status-gating (right status required,
  409 otherwise), ownership (404 for a KAM who isn't `assigned_kam_id`, a
  customer who isn't `submitted_by`), and channel-visibility (BD Manager
  can't post; customer can't see `internal` channel; each role's `GET
  /requests/{id}/messages` returns only what they're allowed to see).
- Frontend: `npm run build` (typecheck) + manual/curl smoke testing of the
  full status loop, matching existing convention — no new test framework.

## 10. Open items for the implementation plan

- Exact wording/casing of the two new literal status strings beyond what's
  fixed here (`"KAM Assessment Submitted"`, `"Revision Requested"`,
  `"Approved — Awaiting KAM Response"`, `"Responded to Customer"`,
  `"Customer Query"`) — confirm they fit the existing `status`
  column width (`String(50)`); `"Approved — Awaiting KAM Response"` is the
  longest at 33 chars, comfortably under the limit.
- Whether `CLAUDE.md` needs a new paragraph documenting this workflow
  (message channels, status machine) once built — planning should include
  this as a documentation task at the end, following the pattern of
  `ae051e5` ("docs: add CLAUDE.md for repo orientation").
