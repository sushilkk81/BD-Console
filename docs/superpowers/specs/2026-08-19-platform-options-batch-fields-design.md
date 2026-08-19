# Platform Options Page: Batch, Qualification & KAM-Visible Requests — Design

**Status:** Approved for planning
**Source:** `Revision 1/New Changes.docx`, Platform Option Page items (2 of 2)

## 1. Problem

The customer wizard's "Platform options" step (step 2 of the request flow) only
lets a customer pick one of three ranked platform option sets. It has no way
to capture a set of logistics/planning details the BD team needs early in the
process:

- **Tentative Exhibit Batch** — a date range for the batch used in exhibit/registration filings.
- **Tentative Approval** — how many months the customer expects approval to take; if the
  customer doesn't know yet, the assigned KAM should be able to fill it in later.
- **Batch Size** — the customer's planned batch size in litres, per SKU (since each SKU can
  have a different fill volume), with the number of pens/cartridges required auto-computed
  (`batch_size_mL / fill_mL`).
- **Assembly Machine Qualification** — whether the customer needs assembly-machine
  qualification runs; if yes, a quantity and a tentative date.
- **Platform Design Verification Request** — a yes/no flag the customer can raise.
- **Sample Request** — a yes/no flag, with a quantity if yes.

The last two flags need to be visible to the assigned KAM once set, the same way the
KAM already sees everything else about a request.

## 2. Data model

### `requests` table — 7 new nullable columns, all request-level

| Column | Type | Notes |
|---|---|---|
| `exhibit_batch_start` | `Date` | nullable |
| `exhibit_batch_end` | `Date` | nullable |
| `tentative_approval_months` | `Integer` | nullable; customer-fillable, KAM-fillable later if still blank |
| `assembly_machine_qualification` | `Boolean` | nullable = not yet answered |
| `assembly_qualification_qty` | `Integer` | nullable; only meaningful when the flag above is true |
| `assembly_qualification_date` | `Date` | nullable; a single tentative date |
| `platform_design_verification_request` | `Boolean` | nullable = not yet answered |
| `sample_request` | `Boolean` | nullable = not yet answered |
| `sample_request_qty` | `Integer` | nullable; only meaningful when `sample_request` is true |

### `sku_rows` table — 1 new nullable column

| Column | Type | Notes |
|---|---|---|
| `batch_size_l` | `Numeric(10, 2)` | nullable; litres, customer-entered per SKU |

Pen count is **not stored** — it's `round(batch_size_l * 1000 / fill_ml)`, computed wherever
it's displayed (frontend), so it can never drift out of sync with `fill_ml` if that later
changes on step 1.

Migration `0007` adds all 8 columns.

## 3. Backend API

### `PUT /requests/{id}/platform-options` (new)

Customer-only, same ownership/draft gate as the existing `PUT /requests/{id}` (step 1):
`_owned_draft_or_404`.

Request body (`PlatformOptionsUpdate`):

```python
class SkuBatchSizeIn(BaseModel):
    sku_row_id: int
    batch_size_l: Optional[float] = None

class PlatformOptionsUpdate(BaseModel):
    exhibit_batch_start: Optional[date] = None
    exhibit_batch_end: Optional[date] = None
    tentative_approval_months: Optional[int] = None
    assembly_machine_qualification: Optional[bool] = None
    assembly_qualification_qty: Optional[int] = None
    assembly_qualification_date: Optional[date] = None
    platform_design_verification_request: Optional[bool] = None
    sample_request: Optional[bool] = None
    sample_request_qty: Optional[int] = None
    sku_batch_sizes: list[SkuBatchSizeIn] = []
```

Behavior: sets all 9 `Request` fields verbatim (last write wins — no merge semantics), then
for each entry in `sku_batch_sizes` updates the matching `SkuRow.batch_size_l` where
`SkuRow.id == sku_row_id and SkuRow.request_id == req.id` (silently skips ids that don't
belong to this request rather than erroring, matching this codebase's other lenient-upsert
helpers). Returns `RequestDetailOut` like every other request-mutation endpoint.

### `POST /requests/{id}/kam-assessment` (existing, extended)

`KamAssessmentIn` gains `tentative_approval_months: Optional[int] = None`. When present, it
overwrites `Request.tentative_approval_months` regardless of the current value — the doc's
"filled in by KAM at a later stage" is read as the KAM having the final say once they engage,
not a blocked-if-already-set merge rule.

### Read paths

`RequestOut` (and therefore `RequestDetailOut`, which extends it) gains all 9 new `Request`
fields. `SkuRowOut` gains `batch_size_l`. No endpoint-level `include_routing`-style gating is
needed — none of these fields are BD-routing-internal, so they're visible to whichever role
can already see the request (Customer/BD Manager/assigned KAM), same as `comment`/`urgency`
today.

## 4. Frontend

### Wizard step 2 (`StepOptions`, `frontend/app/requests/[id]/page.tsx`)

A new card, **"Batch & qualification"**, rendered above the three existing platform-option
cards (visible whenever `options` has loaded, editable only while `isDraft`):

- One row per SKU: strength label, a `Batch Size (L)` number input, and a read-only computed
  "≈ N pens" value that recalculates on every keystroke from that row's `fill_ml`.
- **Tentative Exhibit Batch**: two `<input type="date">` fields (start/end), matching the
  doc's "auto populated calendar" via the browser's native date picker (no new date-picker
  dependency — consistent with the rest of the app using plain HTML form controls).
- **Tentative Approval (months)**: a number input; placeholder text notes it can be left
  blank for the KAM to fill in.
- **Assembly Machine Qualification**: a Yes/No pill toggle (reusing the same pattern as the
  existing "Differentiated formulation" toggle); selecting Yes reveals a qty number input and
  a tentative date input.
- **Platform Design Verification Request**: a Yes/No pill toggle.
- **Sample Request**: a Yes/No pill toggle; selecting Yes reveals a qty number input.
- A **"Save details"** button calls the new endpoint and shows a small saved/error banner,
  independent of the "Select Option N" buttons below it — these fields aren't tied to any one
  option.

All fields are disabled (read-only display) once the request leaves `Draft`, consistent with
every other step-1/step-2 field in this wizard.

### KAM workspace (`frontend/app/dashboard/kam/page.tsx`)

The request-detail panel the KAM already opens gets a small read-only summary block listing
the new fields, with **Platform Design Verification Request** and **Sample Request**
highlighted (e.g. a small badge) when set to Yes, since those two are explicitly the ones the
doc calls out as needing KAM visibility. No new notification is added — the KAM already sees
this the moment they open a request assigned to them, matching how `comment`/`urgency` work
today.

### Types (`frontend/lib/api.ts`)

`RequestDetail`/`RequestRow` and `SkuRowOut`'s frontend mirror types gain the corresponding
new fields.

## 5. Out of scope

- No new notification/bell-icon entry for PDVR or Sample Request (see §4 — visible on open
  instead, per the design decision made during brainstorming).
- No validation tying `tentative_approval_months` to any downstream severity/timeline
  calculation — it's informational, like `comment`/`urgency`.
- No change to the platform-matching/ranking engine — none of these fields feed it.

## 6. Testing

- Backend: new tests for `PUT /requests/{id}/platform-options` (happy path, draft-only gate,
  ownership gate, unknown `sku_row_id` is ignored not errored) and for the extended
  `kam-assessment` payload. Full existing suite must keep passing.
- Frontend: `npm run build` must pass (typecheck). Manual verification via the same
  puppeteer-screenshot approach used earlier in this branch's work, confirming the new card
  renders, saves, and reloads correctly, and that the KAM view shows the two flagged fields.
