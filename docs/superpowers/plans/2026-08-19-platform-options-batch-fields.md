# Platform Options Page: Batch, Qualification & KAM-Visible Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add batch/qualification/verification fields to the customer wizard's "Platform options" step (Tentative Exhibit Batch, Tentative Approval, per-SKU Batch Size → pen count, Assembly Machine Qualification, Platform Design Verification Request, Sample Request), and surface the last two to the assigned KAM.

**Architecture:** 8 new nullable columns on `Request` (request-level) plus 1 new nullable column on `SkuRow` (`batch_size_l`, per SKU), exposed through the existing `RequestOut`/`RequestDetailOut`/`SkuRowOut` response schemas. A new `PUT /requests/{id}/platform-options` endpoint (customer-owned, draft-only — same gate as the existing step-1 PUT) persists all of it in one call. The KAM already fetches full `RequestDetail` for any request assigned to them, so no new notification plumbing is needed — the fields just appear.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js/React (frontend), pytest.

**Spec:** `docs/superpowers/specs/2026-08-19-platform-options-batch-fields-design.md`

## Global Constraints

- All 9 new columns are nullable — nothing here is required to submit a request; every field is optional metadata, matching how `comment`/`urgency` already work.
- Pen count is **computed on read** (`batch_size_l * 1000 / fill_ml`), never stored — it must never go stale relative to `fill_ml`.
- `tentative_approval_months` can be set by the customer (via the new endpoint) or later overwritten by the assigned KAM (via `kam-assessment`) — last write wins, no merge logic.
- The new endpoint follows this codebase's existing convention: reject an `sku_row_id` that doesn't belong to the request with `422`, not a silent skip (see `PUT /requests/{id}/services` in `app/routers/requests.py` for the precedent).
- Frontend field-disabling convention in this file is `onChange={isDraft ? handler : () => {}}` on `TextField`, and `disabled={!isDraft}` on native `<button>` pill toggles — **not** a `disabled` prop on `TextField` (it doesn't have one). Follow this exactly; do not add a `disabled` prop to `TextField`.
- No new notification/bell-icon entry for PDVR or Sample Request — visibility is "the KAM sees it when they open the request," nothing more.

---

### Task 1: Data model — `Request` and `SkuRow` columns + migration

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/0007_platform_options_batch_fields.py`

**Interfaces:**
- Produces: `Request.exhibit_batch_start`, `Request.exhibit_batch_end` (`dt.date | None`), `Request.tentative_approval_months` (`int | None`), `Request.assembly_machine_qualification` (`bool | None`), `Request.assembly_qualification_qty` (`int | None`), `Request.assembly_qualification_date` (`dt.date | None`), `Request.platform_design_verification_request` (`bool | None`), `Request.sample_request` (`bool | None`), `Request.sample_request_qty` (`int | None`); `SkuRow.batch_size_l` (`float | None`).

- [ ] **Step 1: Add the `Date` import**

In `backend/app/models.py`, change the sqlalchemy import line:

```python
from sqlalchemy import Date, ForeignKey, JSON, Numeric, String, Text
```

- [ ] **Step 2: Add the 9 columns to `Request`**

In `backend/app/models.py`, find the `Request` class. The last field before `created_at` is currently:

```python
    kam_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
```

Insert the new columns between them:

```python
    kam_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exhibit_batch_start: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    exhibit_batch_end: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    tentative_approval_months: Mapped[Optional[int]] = mapped_column(nullable=True)
    assembly_machine_qualification: Mapped[Optional[bool]] = mapped_column(nullable=True)
    assembly_qualification_qty: Mapped[Optional[int]] = mapped_column(nullable=True)
    assembly_qualification_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    platform_design_verification_request: Mapped[Optional[bool]] = mapped_column(nullable=True)
    sample_request: Mapped[Optional[bool]] = mapped_column(nullable=True)
    sample_request_qty: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
```

- [ ] **Step 3: Add the column to `SkuRow`**

In `backend/app/models.py`, find the `SkuRow` class:

```python
    strength: Mapped[str] = mapped_column(String(50), nullable=False)
    cartridge: Mapped[str] = mapped_column(String(50), nullable=False)
    fill_ml: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
```

Add `batch_size_l` after `fill_ml`:

```python
    strength: Mapped[str] = mapped_column(String(50), nullable=False)
    cartridge: Mapped[str] = mapped_column(String(50), nullable=False)
    fill_ml: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    batch_size_l: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
```

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/0007_platform_options_batch_fields.py`:

```python
"""requests + sku_rows: Platform Options batch/qualification/verification fields

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("exhibit_batch_start", sa.Date, nullable=True))
    op.add_column("requests", sa.Column("exhibit_batch_end", sa.Date, nullable=True))
    op.add_column("requests", sa.Column("tentative_approval_months", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("assembly_machine_qualification", sa.Boolean, nullable=True))
    op.add_column("requests", sa.Column("assembly_qualification_qty", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("assembly_qualification_date", sa.Date, nullable=True))
    op.add_column("requests", sa.Column("platform_design_verification_request", sa.Boolean, nullable=True))
    op.add_column("requests", sa.Column("sample_request", sa.Boolean, nullable=True))
    op.add_column("requests", sa.Column("sample_request_qty", sa.Integer, nullable=True))
    op.add_column("sku_rows", sa.Column("batch_size_l", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("sku_rows", "batch_size_l")
    op.drop_column("requests", "sample_request_qty")
    op.drop_column("requests", "sample_request")
    op.drop_column("requests", "platform_design_verification_request")
    op.drop_column("requests", "assembly_qualification_date")
    op.drop_column("requests", "assembly_qualification_qty")
    op.drop_column("requests", "assembly_machine_qualification")
    op.drop_column("requests", "tentative_approval_months")
    op.drop_column("requests", "exhibit_batch_end")
    op.drop_column("requests", "exhibit_batch_start")
```

- [ ] **Step 5: Run the full backend suite to confirm nothing broke**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest -q`
Expected: all existing tests still pass (SQLite tests build tables from `Base.metadata`, not migrations, so this only proves the model change itself didn't break anything; the migration is verified against real Postgres in Task 7).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/0007_platform_options_batch_fields.py
git commit -m "feat: add Platform Options batch/qualification/verification columns"
```

---

### Task 2: `PUT /requests/{id}/platform-options` endpoint

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/requests.py`
- Test: `backend/tests/test_requests.py`

**Interfaces:**
- Consumes: `Request`, `SkuRow`, `User` (`app.models`); `_owned_draft_or_404`, `_serialize_detail` (`app.routers.requests`, both already defined in this file).
- Produces: `PlatformOptionsUpdate`, `SkuBatchSizeIn` (Pydantic, `app.schemas`); `PUT /requests/{id}/platform-options` route returning `RequestDetailOut`; `RequestOut`/`SkuRowOut` gain the new fields (consumed by the frontend in Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_requests.py`:

```python
def test_update_platform_options_sets_fields_and_batch_sizes(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg", "2 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    sku_ids = {r["strength"]: r["id"] for r in created["sku_rows"]}

    resp = client.put(f"/requests/{created['id']}/platform-options", headers={"Authorization": f"Bearer {token}"},
                       json={
                           "exhibit_batch_start": "2026-09-01", "exhibit_batch_end": "2026-09-15",
                           "tentative_approval_months": 6,
                           "assembly_machine_qualification": True, "assembly_qualification_qty": 2,
                           "assembly_qualification_date": "2026-10-01",
                           "platform_design_verification_request": True,
                           "sample_request": True, "sample_request_qty": 50,
                           "sku_batch_sizes": [
                               {"sku_row_id": sku_ids["1 mg"], "batch_size_l": 10.0},
                               {"sku_row_id": sku_ids["2 mg"], "batch_size_l": 5.0},
                           ],
                       })
    assert resp.status_code == 200
    body = resp.json()
    assert body["exhibit_batch_start"] == "2026-09-01"
    assert body["exhibit_batch_end"] == "2026-09-15"
    assert body["tentative_approval_months"] == 6
    assert body["assembly_machine_qualification"] is True
    assert body["assembly_qualification_qty"] == 2
    assert body["assembly_qualification_date"] == "2026-10-01"
    assert body["platform_design_verification_request"] is True
    assert body["sample_request"] is True
    assert body["sample_request_qty"] == 50
    rows_by_strength = {r["strength"]: r for r in body["sku_rows"]}
    assert rows_by_strength["1 mg"]["batch_size_l"] == 10.0
    assert rows_by_strength["2 mg"]["batch_size_l"] == 5.0


def test_update_platform_options_rejects_unknown_sku_row_id(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()

    resp = client.put(f"/requests/{created['id']}/platform-options", headers={"Authorization": f"Bearer {token}"},
                       json={"sku_batch_sizes": [{"sku_row_id": 999999, "batch_size_l": 1.0}]})
    assert resp.status_code == 422


def test_update_platform_options_requires_ownership(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()

    other_token, _ = _login(client, "someone@othercorp.com")
    resp = client.put(f"/requests/{created['id']}/platform-options",
                       headers={"Authorization": f"Bearer {other_token}"}, json={})
    assert resp.status_code == 404


def test_update_platform_options_requires_draft(client, seed_reference_product, seed_service_pricing):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})

    resp = client.put(f"/requests/{created['id']}/platform-options",
                       headers={"Authorization": f"Bearer {token}"}, json={})
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_requests.py -k platform_options -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet) on all four.

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas.py`, the `RequestStep1Update` class currently ends at:

```python
class RequestStep1Update(BaseModel):
    brand: str
    market: str
    strengths: list[str]
    viscosity_val: Optional[float] = None
    device: Optional[str] = None
    differentiated: bool = False
    sku_rows: list[SkuRowIn]
```

Insert two new classes immediately after it:

```python
class SkuBatchSizeIn(BaseModel):
    sku_row_id: int
    batch_size_l: Optional[float] = None


class PlatformOptionsUpdate(BaseModel):
    exhibit_batch_start: Optional[dt.date] = None
    exhibit_batch_end: Optional[dt.date] = None
    tentative_approval_months: Optional[int] = None
    assembly_machine_qualification: Optional[bool] = None
    assembly_qualification_qty: Optional[int] = None
    assembly_qualification_date: Optional[dt.date] = None
    platform_design_verification_request: Optional[bool] = None
    sample_request: Optional[bool] = None
    sample_request_qty: Optional[int] = None
    sku_batch_sizes: list[SkuBatchSizeIn] = []
```

Then find `SkuRowOut`:

```python
class SkuRowOut(BaseModel):
    id: int
    strength: str
    cartridge: str
    fill_ml: float
```

Add the new field:

```python
class SkuRowOut(BaseModel):
    id: int
    strength: str
    cartridge: str
    fill_ml: float
    batch_size_l: Optional[float] = None
```

Then find `RequestOut` and add the 9 new fields at the end of it, right after `kam_notes`:

```python
class RequestOut(BaseModel):
    id: int
    org_id: int
    org_name: str
    submitted_by: int
    brand: str
    market: str
    device: Optional[str]
    status: str
    total: float
    assigned_kam_id: Optional[int] = None
    assigned_kam_name: Optional[str] = None
    suggested_kam_id: Optional[int] = None
    suggested_kam_name: Optional[str] = None
    viscosity_val: Optional[float] = None
    differentiated: bool = False
    chosen_option: Optional[int] = None
    severity: Optional[str] = None
    timeline_months: Optional[int] = None
    comment: Optional[str] = None
    urgency: Optional[str] = None
    kam_cost_usd: Optional[float] = None
    kam_timeline_months: Optional[int] = None
    kam_notes: Optional[str] = None
    exhibit_batch_start: Optional[dt.date] = None
    exhibit_batch_end: Optional[dt.date] = None
    tentative_approval_months: Optional[int] = None
    assembly_machine_qualification: Optional[bool] = None
    assembly_qualification_qty: Optional[int] = None
    assembly_qualification_date: Optional[dt.date] = None
    platform_design_verification_request: Optional[bool] = None
    sample_request: Optional[bool] = None
    sample_request_qty: Optional[int] = None
```

- [ ] **Step 4: Wire the new fields into `serialize_requests` and `_serialize_detail`**

In `backend/app/routers/requests.py`, find the `RequestOut(...)` construction inside `serialize_requests`:

```python
            kam_cost_usd=float(r.kam_cost_usd) if r.kam_cost_usd is not None else None,
            kam_timeline_months=r.kam_timeline_months,
            kam_notes=r.kam_notes,
        ))
```

Add the 9 new fields before the closing `))`:

```python
            kam_cost_usd=float(r.kam_cost_usd) if r.kam_cost_usd is not None else None,
            kam_timeline_months=r.kam_timeline_months,
            kam_notes=r.kam_notes,
            exhibit_batch_start=r.exhibit_batch_start,
            exhibit_batch_end=r.exhibit_batch_end,
            tentative_approval_months=r.tentative_approval_months,
            assembly_machine_qualification=r.assembly_machine_qualification,
            assembly_qualification_qty=r.assembly_qualification_qty,
            assembly_qualification_date=r.assembly_qualification_date,
            platform_design_verification_request=r.platform_design_verification_request,
            sample_request=r.sample_request,
            sample_request_qty=r.sample_request_qty,
        ))
```

Find `_serialize_detail`'s `SkuRowOut(...)` construction:

```python
        sku_rows=[SkuRowOut(id=r.id, strength=r.strength, cartridge=r.cartridge, fill_ml=float(r.fill_ml))
                  for r in req.sku_rows],
```

Add `batch_size_l`:

```python
        sku_rows=[SkuRowOut(id=r.id, strength=r.strength, cartridge=r.cartridge, fill_ml=float(r.fill_ml),
                             batch_size_l=float(r.batch_size_l) if r.batch_size_l is not None else None)
                  for r in req.sku_rows],
```

- [ ] **Step 5: Add the import and the endpoint**

In `backend/app/routers/requests.py`, update the schemas import to include the two new classes:

```python
from app.schemas import (BdReviewIn, KamAssessmentIn, MessageIn, MessageOut, PlatformOptionRow,
                          PlatformOptionsOut, PlatformOptionsUpdate, RequestCountOut, RequestCreate,
                          RequestDetailOut, RequestOut, RequestStep1Update, RespondToCustomerIn,
                          SelectOptionRequest, ServiceSelectionOut, ServicesUpdate, SkuBatchSizeIn, SkuRowOut)
```

Find `update_request_step1` (the `PUT /{request_id}` route) — it ends with:

```python
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


def _scoring_rld(db: Session, req: Request) -> dict | None:
```

Insert the new endpoint between them:

```python
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


@router.put("/{request_id}/platform-options", response_model=RequestDetailOut)
def update_platform_options(request_id: int, payload: PlatformOptionsUpdate, db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)

    sku_row_ids = {r.id for r in req.sku_rows}
    for entry in payload.sku_batch_sizes:
        if entry.sku_row_id not in sku_row_ids:
            raise HTTPException(422, f"sku_row_id {entry.sku_row_id} does not belong to this request")

    req.exhibit_batch_start = payload.exhibit_batch_start
    req.exhibit_batch_end = payload.exhibit_batch_end
    req.tentative_approval_months = payload.tentative_approval_months
    req.assembly_machine_qualification = payload.assembly_machine_qualification
    req.assembly_qualification_qty = payload.assembly_qualification_qty
    req.assembly_qualification_date = payload.assembly_qualification_date
    req.platform_design_verification_request = payload.platform_design_verification_request
    req.sample_request = payload.sample_request
    req.sample_request_qty = payload.sample_request_qty

    rows_by_id = {r.id: r for r in req.sku_rows}
    for entry in payload.sku_batch_sizes:
        rows_by_id[entry.sku_row_id].batch_size_l = entry.batch_size_l

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


def _scoring_rld(db: Session, req: Request) -> dict | None:
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_requests.py -k platform_options -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest -q`
Expected: PASS, all tests (existing + new)

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/requests.py backend/tests/test_requests.py
git commit -m "feat: PUT /requests/{id}/platform-options endpoint"
```

---

### Task 3: KAM can fill `tentative_approval_months` via the assessment endpoint

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/requests.py`
- Test: `backend/tests/test_review_workflow.py`

**Interfaces:**
- Consumes: `_assigned_request` helper (already defined in `backend/tests/test_review_workflow.py`).
- Produces: `KamAssessmentIn.tentative_approval_months: Optional[int]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_review_workflow.py`:

```python
def test_kam_assessment_can_set_tentative_approval_months(client, seed_reference_product, seed_service_pricing):
    request_id, _, kam_token, _, _ = _assigned_request(client, seed_reference_product, seed_service_pricing)

    resp = client.post(f"/requests/{request_id}/kam-assessment",
                        json={"kam_cost_usd": 125000, "kam_timeline_months": 6, "tentative_approval_months": 9},
                        headers=_auth(kam_token))
    assert resp.status_code == 200
    assert resp.json()["tentative_approval_months"] == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_review_workflow.py -k tentative_approval -v`
Expected: FAIL — `tentative_approval_months` stays `None` in the response (extra field is silently ignored by the current schema, not applied).

- [ ] **Step 3: Extend the schema and endpoint**

In `backend/app/schemas.py`, find:

```python
class KamAssessmentIn(BaseModel):
    kam_cost_usd: float = Field(gt=0)
    kam_timeline_months: int = Field(gt=0)
    kam_notes: Optional[str] = None
```

Add the new optional field:

```python
class KamAssessmentIn(BaseModel):
    kam_cost_usd: float = Field(gt=0)
    kam_timeline_months: int = Field(gt=0)
    kam_notes: Optional[str] = None
    tentative_approval_months: Optional[int] = None
```

In `backend/app/routers/requests.py`, find `submit_kam_assessment`:

```python
    req.kam_cost_usd = payload.kam_cost_usd
    req.kam_timeline_months = payload.kam_timeline_months
    req.kam_notes = payload.kam_notes
    req.status = "KAM Assessment Submitted"
```

Add the new line:

```python
    req.kam_cost_usd = payload.kam_cost_usd
    req.kam_timeline_months = payload.kam_timeline_months
    req.kam_notes = payload.kam_notes
    if payload.tentative_approval_months is not None:
        req.tentative_approval_months = payload.tentative_approval_months
    req.status = "KAM Assessment Submitted"
```

(Only overwrite when the KAM actually sent a value — an omitted field must not blank out a value the customer already set, unlike the other three fields on this endpoint which are always required inputs.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_review_workflow.py -k tentative_approval -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest -q`
Expected: PASS, all tests

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/requests.py backend/tests/test_review_workflow.py
git commit -m "feat: KAM can set tentative_approval_months in their assessment"
```

---

### Task 4: Frontend types and API client function

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `updatePlatformOptions(token, id, body): Promise<RequestDetail>`; `RequestRow`/`RequestDetail` and `SkuRow` gain the new fields (dates as ISO `string | null`, matching how the rest of this file represents dates — there is no separate `Date` type anywhere in this file).

- [ ] **Step 1: Extend `SkuRow` and `RequestRow`**

In `frontend/lib/api.ts`, find:

```typescript
export type SkuRow = { id: number; strength: string; cartridge: string; fill_ml: number };
```

Replace with:

```typescript
export type SkuRow = {
  id: number;
  strength: string;
  cartridge: string;
  fill_ml: number;
  batch_size_l: number | null;
};
```

Find `RequestRow`'s closing brace:

```typescript
  kam_cost_usd: number | null;
  kam_timeline_months: number | null;
  kam_notes: string | null;
};
```

Add the 9 new fields before the closing brace:

```typescript
  kam_cost_usd: number | null;
  kam_timeline_months: number | null;
  kam_notes: string | null;
  exhibit_batch_start: string | null;
  exhibit_batch_end: string | null;
  tentative_approval_months: number | null;
  assembly_machine_qualification: boolean | null;
  assembly_qualification_qty: number | null;
  assembly_qualification_date: string | null;
  platform_design_verification_request: boolean | null;
  sample_request: boolean | null;
  sample_request_qty: number | null;
};
```

- [ ] **Step 2: Add the API function**

Find `getPlatformOptions`:

```typescript
export async function getPlatformOptions(token: string, id: number): Promise<PlatformOptions> {
  const resp = await fetch(`/api/requests/${id}/platform-options`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load platform options — try again.");
  return resp.json();
}
```

Add the new function immediately after it:

```typescript
export async function updatePlatformOptions(
  token: string,
  id: number,
  body: {
    exhibit_batch_start: string | null;
    exhibit_batch_end: string | null;
    tentative_approval_months: number | null;
    assembly_machine_qualification: boolean | null;
    assembly_qualification_qty: number | null;
    assembly_qualification_date: string | null;
    platform_design_verification_request: boolean | null;
    sample_request: boolean | null;
    sample_request_qty: number | null;
    sku_batch_sizes: { sku_row_id: number; batch_size_l: number | null }[];
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/platform-options`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save those details — try again.");
  return resp.json();
}
```

- [ ] **Step 3: Verify the frontend still typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds (this will still fail to reference `updatePlatformOptions` anywhere yet, which is fine — an unused exported function is not a type error).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): types and API client for platform-options endpoint"
```

---

### Task 5: Wizard step 2 — Batch & qualification card

**Files:**
- Modify: `frontend/app/requests/[id]/page.tsx`

**Interfaces:**
- Consumes: `updatePlatformOptions` (Task 4); `RequestDetail`, `SkuRow` (Task 4); existing `isDraft`, `detail`, `token`, `requestId`, `TextField`, `Button`, `Banner` already in scope in this file.

- [ ] **Step 1: Import the new API function**

In `frontend/app/requests/[id]/page.tsx`, find the `@/lib/api` import block:

```typescript
import {
  ApiError,
  Message,
  PlatformOptions,
  ReferenceProduct,
  RequestDetail,
  getMessages,
  getPlatformOptions,
  getRequestDetail,
  listReferenceProducts,
  lookupStrengths,
  lookupViscosity,
  postMessage,
  selectOption,
  submitRequest,
  updateRequestStep1,
  updateServices,
} from "@/lib/api";
```

Add `updatePlatformOptions` (keep alphabetical, matching this file's existing ordering):

```typescript
import {
  ApiError,
  Message,
  PlatformOptions,
  ReferenceProduct,
  RequestDetail,
  getMessages,
  getPlatformOptions,
  getRequestDetail,
  listReferenceProducts,
  lookupStrengths,
  lookupViscosity,
  postMessage,
  selectOption,
  submitRequest,
  updatePlatformOptions,
  updateRequestStep1,
  updateServices,
} from "@/lib/api";
```

- [ ] **Step 2: Add state**

Find:

```typescript
  const [options, setOptions] = useState<PlatformOptions | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState("");
  const [selecting, setSelecting] = useState(false);
```

Add the new state right after it:

```typescript
  const [options, setOptions] = useState<PlatformOptions | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState("");
  const [selecting, setSelecting] = useState(false);

  const [exhibitBatchStart, setExhibitBatchStart] = useState("");
  const [exhibitBatchEnd, setExhibitBatchEnd] = useState("");
  const [tentativeApprovalMonths, setTentativeApprovalMonths] = useState<number | "">("");
  const [assemblyQualification, setAssemblyQualification] = useState<boolean | null>(null);
  const [assemblyQualificationQty, setAssemblyQualificationQty] = useState<number | "">("");
  const [assemblyQualificationDate, setAssemblyQualificationDate] = useState("");
  const [pdvr, setPdvr] = useState<boolean | null>(null);
  const [sampleRequest, setSampleRequest] = useState<boolean | null>(null);
  const [sampleRequestQty, setSampleRequestQty] = useState<number | "">("");
  const [batchSizes, setBatchSizes] = useState<Record<number, number | "">>({});
  const [savingPlatformOptions, setSavingPlatformOptions] = useState(false);
  const [platformOptionsError, setPlatformOptionsError] = useState("");
  const [platformOptionsSaved, setPlatformOptionsSaved] = useState(false);
```

- [ ] **Step 3: Seed state from the loaded request**

Find the load effect:

```typescript
        setViscosityVal(req.viscosity_val ?? "");
        setDifferentiated(req.differentiated);
        setDevice(req.device);
        if (req.chosen_option != null && req.status === "Draft") setStep("options");
```

Add the new seeding before the `if (req.chosen_option...)` line:

```typescript
        setViscosityVal(req.viscosity_val ?? "");
        setDifferentiated(req.differentiated);
        setDevice(req.device);
        setExhibitBatchStart(req.exhibit_batch_start ?? "");
        setExhibitBatchEnd(req.exhibit_batch_end ?? "");
        setTentativeApprovalMonths(req.tentative_approval_months ?? "");
        setAssemblyQualification(req.assembly_machine_qualification);
        setAssemblyQualificationQty(req.assembly_qualification_qty ?? "");
        setAssemblyQualificationDate(req.assembly_qualification_date ?? "");
        setPdvr(req.platform_design_verification_request);
        setSampleRequest(req.sample_request);
        setSampleRequestQty(req.sample_request_qty ?? "");
        setBatchSizes(Object.fromEntries(req.sku_rows.map((r) => [r.id, r.batch_size_l ?? ""])));
        if (req.chosen_option != null && req.status === "Draft") setStep("options");
```

- [ ] **Step 4: Add the save handler**

Find `handleSelectOption`:

```typescript
  async function handleSelectOption(n: 1 | 2 | 3) {
    if (!token) return;
    setSelecting(true);
    try {
      const updated = await selectOption(token, requestId, n);
      setDetail(updated);
      setStep("cost");
    } catch (err) {
      setOptionsError(err instanceof ApiError ? err.message : "We couldn't select that option — try again.");
    } finally {
      setSelecting(false);
    }
  }
```

Add the new handler immediately after it:

```typescript
  async function handleSavePlatformOptions() {
    if (!token) return;
    setSavingPlatformOptions(true);
    setPlatformOptionsError("");
    setPlatformOptionsSaved(false);
    try {
      const updated = await updatePlatformOptions(token, requestId, {
        exhibit_batch_start: exhibitBatchStart || null,
        exhibit_batch_end: exhibitBatchEnd || null,
        tentative_approval_months: tentativeApprovalMonths === "" ? null : Number(tentativeApprovalMonths),
        assembly_machine_qualification: assemblyQualification,
        assembly_qualification_qty: assemblyQualificationQty === "" ? null : Number(assemblyQualificationQty),
        assembly_qualification_date: assemblyQualificationDate || null,
        platform_design_verification_request: pdvr,
        sample_request: sampleRequest,
        sample_request_qty: sampleRequestQty === "" ? null : Number(sampleRequestQty),
        sku_batch_sizes: Object.entries(batchSizes).map(([id, v]) => ({
          sku_row_id: Number(id),
          batch_size_l: v === "" ? null : Number(v),
        })),
      });
      setDetail(updated);
      setPlatformOptionsSaved(true);
    } catch (err) {
      setPlatformOptionsError(
        err instanceof ApiError ? err.message : "We couldn't save those details — try again."
      );
    } finally {
      setSavingPlatformOptions(false);
    }
  }
```

- [ ] **Step 5: Add the card JSX**

Find where `StepOptions` is rendered:

```tsx
            {step === "options" && detail && (
              <StepOptions
                options={options}
                loading={optionsLoading}
                error={optionsError}
                onDismissError={() => setOptionsError("")}
                chosenOption={detail.chosen_option}
                isDraft={isDraft}
                selecting={selecting}
                onSelect={handleSelectOption}
              />
            )}
```

Replace with (wraps the existing `StepOptions` call in a fragment alongside the new card):

```tsx
            {step === "options" && detail && (
              <>
                <Card>
                  <h2 className="mb-4 font-display text-base font-semibold text-forest-900">
                    Batch & qualification
                  </h2>
                  <div className="flex flex-col gap-6">
                    <div>
                      <h3 className="mb-2 font-body text-sm font-medium text-ink-700">Batch size per SKU</h3>
                      <div className="flex flex-col gap-2">
                        {detail.sku_rows.map((row) => {
                          const val = batchSizes[row.id] ?? "";
                          const pens =
                            val !== "" && row.fill_ml > 0
                              ? Math.round((Number(val) * 1000) / row.fill_ml)
                              : null;
                          return (
                            <div key={row.id} className="flex flex-wrap items-end gap-3">
                              <span className="w-20 font-body text-sm text-ink-700">{row.strength}</span>
                              <div className="w-36">
                                <TextField
                                  label="Batch size (L)"
                                  name={`batch-size-${row.id}`}
                                  type="number"
                                  value={val === "" ? "" : String(val)}
                                  onChange={
                                    isDraft
                                      ? (v) => setBatchSizes((prev) => ({ ...prev, [row.id]: v === "" ? "" : Number(v) }))
                                      : () => {}
                                  }
                                />
                              </div>
                              <span className="font-body text-xs text-ink-700/70">
                                {pens != null ? `≈ ${pens} pens` : "—"}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                      <TextField
                        label="Tentative exhibit batch — start"
                        name="exhibit-batch-start"
                        type="date"
                        value={exhibitBatchStart}
                        onChange={isDraft ? setExhibitBatchStart : () => {}}
                      />
                      <TextField
                        label="Tentative exhibit batch — end"
                        name="exhibit-batch-end"
                        type="date"
                        value={exhibitBatchEnd}
                        onChange={isDraft ? setExhibitBatchEnd : () => {}}
                      />
                      <div>
                        <TextField
                          label="Tentative approval (months)"
                          name="tentative-approval-months"
                          type="number"
                          value={tentativeApprovalMonths === "" ? "" : String(tentativeApprovalMonths)}
                          onChange={
                            isDraft ? (v) => setTentativeApprovalMonths(v === "" ? "" : Number(v)) : () => {}
                          }
                        />
                        <p className="mt-1 font-body text-xs text-ink-700/60">
                          Leave blank — your KAM can fill this in later.
                        </p>
                      </div>
                    </div>

                    <div>
                      <h3 className="mb-2 font-body text-sm font-medium text-ink-700">
                        Assembly machine qualification
                      </h3>
                      <div className="flex gap-2">
                        {([["Yes", true], ["No", false]] as const).map(([label, val]) => (
                          <button
                            key={label}
                            type="button"
                            disabled={!isDraft}
                            onClick={() => isDraft && setAssemblyQualification(val)}
                            className={`rounded-full border px-4 py-2 font-body text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                              assemblyQualification === val
                                ? "border-forest-600 bg-forest-600/10 text-forest-900"
                                : "border-ink-700/15 text-ink-700/70 hover:border-forest-600/40"
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      {assemblyQualification && (
                        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
                          <TextField
                            label="Qty"
                            name="assembly-qualification-qty"
                            type="number"
                            value={assemblyQualificationQty === "" ? "" : String(assemblyQualificationQty)}
                            onChange={
                              isDraft
                                ? (v) => setAssemblyQualificationQty(v === "" ? "" : Number(v))
                                : () => {}
                            }
                          />
                          <TextField
                            label="Tentative date"
                            name="assembly-qualification-date"
                            type="date"
                            value={assemblyQualificationDate}
                            onChange={isDraft ? setAssemblyQualificationDate : () => {}}
                          />
                        </div>
                      )}
                    </div>

                    <div>
                      <h3 className="mb-2 font-body text-sm font-medium text-ink-700">
                        Platform Design Verification Request
                      </h3>
                      <div className="flex gap-2">
                        {([["Yes", true], ["No", false]] as const).map(([label, val]) => (
                          <button
                            key={label}
                            type="button"
                            disabled={!isDraft}
                            onClick={() => isDraft && setPdvr(val)}
                            className={`rounded-full border px-4 py-2 font-body text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                              pdvr === val
                                ? "border-forest-600 bg-forest-600/10 text-forest-900"
                                : "border-ink-700/15 text-ink-700/70 hover:border-forest-600/40"
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h3 className="mb-2 font-body text-sm font-medium text-ink-700">Sample request</h3>
                      <div className="flex gap-2">
                        {([["Yes", true], ["No", false]] as const).map(([label, val]) => (
                          <button
                            key={label}
                            type="button"
                            disabled={!isDraft}
                            onClick={() => isDraft && setSampleRequest(val)}
                            className={`rounded-full border px-4 py-2 font-body text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                              sampleRequest === val
                                ? "border-forest-600 bg-forest-600/10 text-forest-900"
                                : "border-ink-700/15 text-ink-700/70 hover:border-forest-600/40"
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      {sampleRequest && (
                        <div className="mt-3 w-40">
                          <TextField
                            label="Qty"
                            name="sample-request-qty"
                            type="number"
                            value={sampleRequestQty === "" ? "" : String(sampleRequestQty)}
                            onChange={isDraft ? (v) => setSampleRequestQty(v === "" ? "" : Number(v)) : () => {}}
                          />
                        </div>
                      )}
                    </div>

                    {platformOptionsError && (
                      <Banner message={platformOptionsError} onDismiss={() => setPlatformOptionsError("")} />
                    )}
                    {isDraft && (
                      <div>
                        <Button
                          variant="secondary"
                          loading={savingPlatformOptions}
                          onClick={handleSavePlatformOptions}
                        >
                          {platformOptionsSaved ? "Saved ✓" : "Save details"}
                        </Button>
                      </div>
                    )}
                  </div>
                </Card>

                <StepOptions
                  options={options}
                  loading={optionsLoading}
                  error={optionsError}
                  onDismissError={() => setOptionsError("")}
                  chosenOption={detail.chosen_option}
                  isDraft={isDraft}
                  selecting={selecting}
                  onSelect={handleSelectOption}
                />
              </>
            )}
```

- [ ] **Step 6: Verify the frontend build passes**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 7: Manual verification against the running stack**

Rebuild and restart the frontend container, then confirm in the browser (or via a puppeteer screenshot the way earlier work in this branch verified UI changes — see git history on this branch for the pattern):

```bash
docker-compose up -d --build frontend
```

Log in as a customer, open a draft request, go to step 2, fill in a batch size for a SKU and confirm the pen count updates live, set the Yes/No toggles, click "Save details", reload the page, and confirm every value round-trips.

- [ ] **Step 8: Commit**

```bash
git add "frontend/app/requests/[id]/page.tsx"
git commit -m "feat(frontend): Batch & qualification card on the Platform Options step"
```

---

### Task 6: KAM workspace — surface the new fields

**Files:**
- Modify: `frontend/app/dashboard/kam/page.tsx`

**Interfaces:**
- Consumes: `active` (`RequestRow`, already in scope), `activeDetail` (`RequestDetail`, already in scope) — both gain the new fields automatically via Task 4's type changes.

- [ ] **Step 1: Add the summary fields to the existing details `<dl>`**

In `frontend/app/dashboard/kam/page.tsx`, find:

```tsx
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Status</dt>
                  <dd><StatusChip status={active.status} /></dd>
                </div>
              </dl>
              {actionError && <Banner message={actionError} onDismiss={() => setActionError("")} />}
```

Replace with:

```tsx
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Status</dt>
                  <dd><StatusChip status={active.status} /></dd>
                </div>
                {active.platform_design_verification_request && (
                  <div>
                    <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                      Platform Design Verification
                    </dt>
                    <dd className="font-body text-sm font-medium text-forest-600">Requested</dd>
                  </div>
                )}
                {active.sample_request && (
                  <div>
                    <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Sample request</dt>
                    <dd className="font-body text-sm font-medium text-forest-600">
                      Requested{active.sample_request_qty != null ? ` · qty ${active.sample_request_qty}` : ""}
                    </dd>
                  </div>
                )}
                {active.exhibit_batch_start && active.exhibit_batch_end && (
                  <div>
                    <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                      Tentative exhibit batch
                    </dt>
                    <dd className="font-body text-sm text-ink-700">
                      {active.exhibit_batch_start} → {active.exhibit_batch_end}
                    </dd>
                  </div>
                )}
                {active.tentative_approval_months != null && (
                  <div>
                    <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                      Tentative approval
                    </dt>
                    <dd className="font-body text-sm text-ink-700">{active.tentative_approval_months} month(s)</dd>
                  </div>
                )}
                {active.assembly_machine_qualification && (
                  <div>
                    <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                      Assembly machine qualification
                    </dt>
                    <dd className="font-body text-sm text-ink-700">
                      Qty {active.assembly_qualification_qty ?? "—"}
                      {active.assembly_qualification_date ? ` · ${active.assembly_qualification_date}` : ""}
                    </dd>
                  </div>
                )}
              </dl>
              {activeDetail && activeDetail.sku_rows.some((r) => r.batch_size_l != null) && (
                <div className="mt-4 border-t border-ink-700/10 pt-4">
                  <h3 className="mb-2 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    Batch size / pens
                  </h3>
                  <ul className="flex flex-col gap-1">
                    {activeDetail.sku_rows
                      .filter((r) => r.batch_size_l != null)
                      .map((r) => (
                        <li key={r.id} className="font-body text-sm text-ink-700">
                          {r.strength}: {r.batch_size_l} L → ≈ {Math.round((r.batch_size_l! * 1000) / r.fill_ml)} pens
                        </li>
                      ))}
                  </ul>
                </div>
              )}
              {actionError && <Banner message={actionError} onDismiss={() => setActionError("")} />}
```

- [ ] **Step 2: Verify the frontend build passes**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/dashboard/kam/page.tsx"
git commit -m "feat(frontend): surface Platform Options fields in the KAM workspace"
```

---

### Task 7: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Apply the migration to the dev Postgres database**

```bash
docker-compose build backend
docker-compose run --rm backend alembic upgrade head
```

Expected output includes `Running upgrade 0006 -> 0007, requests + sku_rows: Platform Options batch/qualification/verification fields`.

- [ ] **Step 2: Rebuild and restart both containers**

```bash
docker-compose up -d --build backend frontend
```

- [ ] **Step 3: End-to-end manual check**

As a customer: create a request, add a SKU, reach step 2, fill in the Batch & qualification card (batch size, exhibit batch dates, tentative approval months, assembly qualification Yes + qty/date, PDVR Yes, sample request Yes + qty), click "Save details", reload the page, confirm every value persisted.

As a BD Manager: assign the request to a KAM (`org_kam_map` flow, same as any other request).

As that KAM: open the request in the KAM workspace and confirm "Platform Design Verification" and "Sample request" both show as Requested, the exhibit batch/approval/qualification summary appears, and the per-SKU batch size/pen count line appears.

- [ ] **Step 4: Run the full backend suite one more time**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest -q`
Expected: PASS, all tests

---

## Self-Review Notes

- **Spec coverage:** Data model (Task 1), `PUT /requests/{id}/platform-options` (Task 2), KAM-fillable `tentative_approval_months` (Task 3), frontend types/client (Task 4), wizard step-2 UI including per-SKU batch size → computed pen count, exhibit batch dates, approval months, assembly qualification, PDVR, sample request (Task 5), KAM-side surfacing of PDVR/sample-request/the rest (Task 6), and live migration + end-to-end check (Task 7) — every spec section has a task.
- **Type consistency:** `PlatformOptionsUpdate`/`SkuBatchSizeIn` (Task 2) field names match the frontend `updatePlatformOptions` body shape (Task 4) and the JSX call site (Task 5) exactly. `SkuRowOut.batch_size_l` (Task 2) matches frontend `SkuRow.batch_size_l` (Task 4) and its use in both Task 5 (pen-count calc) and Task 6 (KAM summary). `RequestOut`'s 9 new fields (Task 2) match `RequestRow`'s 9 new fields (Task 4) name-for-name, consumed identically in Task 5 (seeding) and Task 6 (display).
- **No placeholders:** every step has literal, complete code — no "add validation" or "similar to Task N" hand-waving.
- **Existing-pattern conformance:** unknown `sku_row_id` → `422` (matches `update_services`); `TextField` editability via `onChange={isDraft ? handler : () => {}}`, pill toggles via native `<button disabled={!isDraft}>` (matches the existing viscosity field and "Differentiated formulation" toggle) — no changes to shared components required.
