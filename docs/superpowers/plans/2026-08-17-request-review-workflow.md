# Request Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the request lifecycle past "Assigned to {KAM}" with a KAM cost/timeline assessment, a BD Manager approve/revise gate, a KAM → Customer response, and an ongoing customer query thread the KAM answers and the BD Manager can read but not post to.

**Architecture:** A new Alembic migration adds three assessment columns to `requests` (`kam_cost_usd`, `kam_timeline_months`, `kam_notes`) and a `request_messages` table backing two logical threads distinguished by a `channel` column (`"internal"` = BD Manager ↔ KAM, `"customer"` = KAM ↔ Customer, BD-Manager-readable). Five new endpoints on the existing `requests.py` router drive one literal-status-per-handoff state machine. The frontend adds a shared `MessageThread` component used from the KAM workspace, the BD Manager admin page, and the customer wizard.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest (backend); Next.js App Router, React, Tailwind (frontend). No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-08-17-request-review-workflow-design.md`](../specs/2026-08-17-request-review-workflow-design.md)

## Global Constraints

- No PDF "scope note" export — deferred, template undecided (spec §8). This plan keeps every field a future export would need in structured columns; no schema hedge beyond that.
- No SES/email notifications for status changes or new messages (spec §3).
- Messages are append-only — no edit/delete endpoint (spec §3, matches the existing `AuditLog` convention).
- No re-open action once a request leaves the review loop — `Responded to Customer` ⇄ `Customer Query` is the terminal pair (spec §3).
- The KAM's `kam_cost_usd`/`kam_timeline_months`/`kam_notes` are additive fields, never a replacement for the customer's own `total`/`timeline_months`/`severity` from the cost & deal step (spec §3, §4).
- Every request-mutation endpoint requires `get_current_user` plus an ownership check (`submitted_by == current_user.id` for the customer, `assigned_kam_id == current_user.id` for the KAM) — 404 (not 403) on mismatch. `GET /requests/{id}/messages` instead uses the same role-scoped visibility as `GET /requests/{id}` (spec §6). 409 on any mutation attempted from the wrong `status`.
- Literal status strings, exactly: `"KAM Assessment Submitted"`, `"Revision Requested"`, `"Approved — Awaiting KAM Response"`, `"Responded to Customer"`, `"Customer Query"` (spec §5, §10 — longest is 33 chars, well under the `status` column's `String(50)`).
- SQLite (test suite) doesn't enforce `VARCHAR` lengths — truncate any user-derived string written into a length-limited column (`request_messages.body` is `String(2000)`, matching `requests.comment`'s existing width).
- Frontend: no test framework — verification is `npm run build` plus manual/curl smoke testing.

---

## Backend

### Task 1: Migration 0004 — assessment columns + `request_messages` table

**Files:**
- Create: `backend/alembic/versions/0004_request_review_workflow.py`

**Interfaces:**
- Produces: `requests.kam_cost_usd` (Numeric(12,2), nullable), `requests.kam_timeline_months` (Integer, nullable), `requests.kam_notes` (Text, nullable); table `request_messages` (`id`, `request_id` FK, `channel` String(20), `sender_user_id` FK, `body` String(2000), `created_at`).

- [ ] **Step 1: Write the migration**

```python
"""KAM assessment fields and request_messages thread table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("kam_cost_usd", sa.Numeric(12, 2), nullable=True))
    op.add_column("requests", sa.Column("kam_timeline_months", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("kam_notes", sa.Text, nullable=True))

    op.create_table(
        "request_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("sender_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("request_messages")
    op.drop_column("requests", "kam_notes")
    op.drop_column("requests", "kam_timeline_months")
    op.drop_column("requests", "kam_cost_usd")
```

- [ ] **Step 2: Verify the migration applies cleanly against SQLite in a throwaway script**

Run:
```bash
PYTHONPATH=backend python3 -c "
from alembic.config import Config
from alembic import command
cfg = Config('backend/alembic.ini')
cfg.set_main_option('sqlalchemy.url', 'sqlite:///./_migration_check.db')
command.upgrade(cfg, 'head')
command.downgrade(cfg, 'base')
"
rm -f _migration_check.db
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/0004_request_review_workflow.py
git commit -m "feat(backend): migration for KAM assessment fields and request_messages table"
```

---

### Task 2: ORM models — `RequestMessage`, `Request` assessment columns

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: table from Task 1.
- Produces: `RequestMessage` model class; `Request` gains `kam_cost_usd: Optional[float]`, `kam_timeline_months: Optional[int]`, `kam_notes: Optional[str]`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_models.py`:

```python
from app.models import RequestMessage


def test_request_kam_assessment_fields_and_message_thread_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    org = Organization(name="Pfizer", kind="customer", domain="pfizer.com")
    db.add(org)
    db.flush()
    customer = User(org_id=org.id, email="a@pfizer.com", name="Alice", role="Customer")
    db.add(customer)
    db.flush()
    req = Request(org_id=org.id, submitted_by=customer.id, brand="Ozempic", market="US",
                   status="KAM Assessment Submitted", kam_cost_usd=125000, kam_timeline_months=6,
                   kam_notes="Needs a new tool for the 2 mg cartridge.")
    db.add(req)
    db.flush()
    db.add(RequestMessage(request_id=req.id, channel="internal", sender_user_id=customer.id,
                           body="Please confirm the tool cost."))
    db.commit()

    fetched = db.query(Request).one()
    assert fetched.kam_cost_usd == 125000
    assert fetched.kam_timeline_months == 6
    assert "2 mg" in fetched.kam_notes

    msg = db.query(RequestMessage).one()
    assert msg.channel == "internal"
    assert msg.body == "Please confirm the tool cost."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_models.py::test_request_kam_assessment_fields_and_message_thread_roundtrip -v`
Expected: FAIL — `ImportError: cannot import name 'RequestMessage'`.

- [ ] **Step 3: Add the columns and model**

In `backend/app/models.py`, add `Text` to the sqlalchemy import:

```python
from sqlalchemy import ForeignKey, JSON, Numeric, String, Text
```

Add three columns to `Request`, right after `urgency`:

```python
    kam_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    kam_timeline_months: Mapped[Optional[int]] = mapped_column(nullable=True)
    kam_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

Append the new class after `ServicePricing`:

```python
class RequestMessage(Base):
    __tablename__ = "request_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # "internal" | "customer"
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_models.py -v`
Expected: PASS (all tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat(backend): ORM model for RequestMessage, KAM assessment columns on Request"
```

---

### Task 3: Schemas — assessment, review, response, and message payloads

**Files:**
- Modify: `backend/app/schemas.py`

**Interfaces:**
- Produces: `KamAssessmentIn`, `BdReviewIn`, `RespondToCustomerIn`, `MessageIn`, `MessageOut`; extends `RequestOut` with `kam_cost_usd`, `kam_timeline_months`, `kam_notes`.

- [ ] **Step 1: Add the schemas**

In `backend/app/schemas.py`, change the top-of-file import to add `Literal` and `model_validator`:

```python
import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
```

Add the three assessment/review fields to `RequestOut` (after `urgency`):

```python
    kam_cost_usd: Optional[float] = None
    kam_timeline_months: Optional[int] = None
    kam_notes: Optional[str] = None
```

Add these new classes after `RequestDetailOut`, before `KamOut`:

```python
class KamAssessmentIn(BaseModel):
    kam_cost_usd: float = Field(gt=0)
    kam_timeline_months: int = Field(gt=0)
    kam_notes: Optional[str] = None


class BdReviewIn(BaseModel):
    decision: Literal["approve", "revise"]
    note: Optional[str] = None

    @model_validator(mode="after")
    def note_required_for_revise(self):
        if self.decision == "revise" and not self.note:
            raise ValueError("note is required when decision is 'revise'")
        return self


class RespondToCustomerIn(BaseModel):
    message: str = Field(min_length=1)


class MessageIn(BaseModel):
    channel: Literal["internal", "customer"]
    body: str = Field(min_length=1)


class MessageOut(BaseModel):
    id: int
    request_id: int
    channel: str
    sender_user_id: int
    sender_name: str
    body: str
    created_at: dt.datetime
```

- [ ] **Step 2: Sanity-check schema import**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/python3 -c "from app.schemas import KamAssessmentIn, BdReviewIn, RespondToCustomerIn, MessageIn, MessageOut; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(backend): request-review-workflow Pydantic schemas"
```

---

### Task 4: `POST /requests/{id}/kam-assessment`

**Files:**
- Modify: `backend/app/routers/requests.py`
- Create: `backend/tests/test_review_workflow.py`

**Interfaces:**
- Consumes: `KamAssessmentIn` (Task 3), `Request.assigned_kam_id`/`kam_cost_usd`/`kam_timeline_months`/`kam_notes` (Task 2).
- Produces: `_assigned_kam_or_404(db, request_id, user) -> Request` (reused by Tasks 6, 7); `STATUS_MAX_LEN = 50`, `MESSAGE_MAX_LEN = 2000` constants in `requests.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_review_workflow.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seed_reference_product(client):
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["1 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"1 mg": ["3 mL", 3.0]}, presentations_ref="pref",
    ))
    db.commit()
    db.close()


@pytest.fixture
def seed_service_pricing(client):
    from app.models import ServicePricing
    db = next(app.dependency_overrides[get_db]())
    db.add(ServicePricing(key="PKG", payload={"minor": 200, "moderate": 250, "major": 350}))
    db.add(ServicePricing(key="ADD_DV", payload={"value": 50}))
    db.add(ServicePricing(key="TIMELINE", payload={"minor": 3, "moderate": 6, "major": 9}))
    db.add(ServicePricing(key="SERVICES",
                           payload={"standard_dv": 200, "threshold": 2110, "ifu": 1110, "human_factor": 400000}))
    db.commit()
    db.close()


def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _assigned_request(client, seed_reference_product, seed_service_pricing):
    """Create, complete, and submit a customer request, then assign it to a KAM.

    Returns (request_id, customer_token, kam_token, kam_user, mgr_token).
    """
    customer_token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers=_auth(customer_token)).json()
    request_id = created["id"]
    client.post(f"/requests/{request_id}/select-option", json={"chosen_option": 1}, headers=_auth(customer_token))
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{request_id}/services", headers=_auth(customer_token),
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    client.post(f"/requests/{request_id}/submit", headers=_auth(customer_token))

    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    client.post(f"/requests/{request_id}/assign-kam", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token))

    return request_id, customer_token, kam_token, kam_user, mgr_token


def test_kam_assessment_requires_assigned_kam(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, _ = _assigned_request(client, seed_reference_product, seed_service_pricing)
    other_kam_token, _ = _login(client, "other@shaily.com", name="Other KAM", role="Key Account Manager")

    resp = client.post(f"/requests/{request_id}/kam-assessment",
                        json={"kam_cost_usd": 125000, "kam_timeline_months": 6}, headers=_auth(other_kam_token))
    assert resp.status_code == 404


def test_kam_assessment_sets_fields_and_advances_status(client, seed_reference_product, seed_service_pricing):
    request_id, _, kam_token, _, _ = _assigned_request(client, seed_reference_product, seed_service_pricing)

    resp = client.post(f"/requests/{request_id}/kam-assessment",
                        json={"kam_cost_usd": 125000, "kam_timeline_months": 6, "kam_notes": "New tool required."},
                        headers=_auth(kam_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "KAM Assessment Submitted"
    assert body["kam_cost_usd"] == 125000
    assert body["kam_timeline_months"] == 6
    assert body["kam_notes"] == "New tool required."


def test_kam_assessment_409_before_kam_assigned(client, seed_reference_product, seed_service_pricing):
    customer_token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers=_auth(customer_token)).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1}, headers=_auth(customer_token))
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers=_auth(customer_token),
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    client.post(f"/requests/{created['id']}/submit", headers=_auth(customer_token))

    kam_token, kam_user = _login(client, "mah@shaily.com", role="Key Account Manager")
    resp = client.post(f"/requests/{created['id']}/kam-assessment",
                        json={"kam_cost_usd": 100, "kam_timeline_months": 3}, headers=_auth(kam_token))
    assert resp.status_code == 404  # not assigned to this KAM yet
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_review_workflow.py -v`
Expected: FAIL — `404 Not Found` for `/requests/{id}/kam-assessment` (route doesn't exist yet — FastAPI 404s, so `test_kam_assessment_requires_assigned_kam` and `test_kam_assessment_409_before_kam_assigned` pass by accident but `test_kam_assessment_sets_fields_and_advances_status` fails on `assert resp.status_code == 200`).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routers/requests.py`, add to the imports:

```python
from app.deps import get_current_user, require_role
from app.models import (Organization, OrgKamMap, PlatformSheet, Request, RequestMessage, ServicePricing,
                         ServiceSelection, SkuRow, User)
from app.schemas import (BdReviewIn, KamAssessmentIn, MessageIn, MessageOut, PlatformOptionRow, PlatformOptionsOut,
                          RequestCreate, RequestDetailOut, RequestOut, RequestStep1Update, RespondToCustomerIn,
                          SelectOptionRequest, ServiceSelectionOut, ServicesUpdate, SkuRowOut)
```

Add the two new constants near the top (after `URGENCY_MAX_LEN`):

```python
STATUS_MAX_LEN = 50  # matches Request.status column width (models.py)
MESSAGE_MAX_LEN = 2000  # matches RequestMessage.body column width (models.py)
```

Add `kam_cost_usd`/`kam_timeline_months`/`kam_notes` to `serialize_requests`'s `RequestOut(...)` construction (after `urgency=r.urgency,`):

```python
            kam_cost_usd=float(r.kam_cost_usd) if r.kam_cost_usd is not None else None,
            kam_timeline_months=r.kam_timeline_months,
            kam_notes=r.kam_notes,
```

Add this helper after `_owned_draft_or_404`:

```python
def _assigned_kam_or_404(db: Session, request_id: int, user: User) -> Request:
    req = db.get(Request, request_id)
    if req is None or req.assigned_kam_id != user.id:
        raise HTTPException(404, "Request not found")
    return req
```

Add the endpoint after `submit_request`:

```python
@router.post("/{request_id}/kam-assessment", response_model=RequestDetailOut)
def submit_kam_assessment(request_id: int, payload: KamAssessmentIn, db: Session = Depends(get_db),
                           current_user: User = Depends(require_role("Key Account Manager"))):
    req = _assigned_kam_or_404(db, request_id, current_user)
    expected = f"Assigned to {current_user.name}"[:STATUS_MAX_LEN]
    if req.status not in (expected, "Revision Requested"):
        raise HTTPException(409, "This request isn't awaiting a KAM assessment")

    req.kam_cost_usd = payload.kam_cost_usd
    req.kam_timeline_months = payload.kam_timeline_months
    req.kam_notes = payload.kam_notes
    req.status = "KAM Assessment Submitted"
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req, include_routing=True)
```

Note: `require_role("Key Account Manager")` returns 403 for a non-KAM caller (e.g. a customer or BD Manager) before `_assigned_kam_or_404` ever runs — consistent with how `require_role("BD Manager")` gates `kams.py`'s endpoints.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_review_workflow.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full backend suite to check nothing else broke**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest -v`
Expected: PASS (every existing test still passes — `RequestOut`'s three new optional fields default to `None` and don't disturb any existing assertion).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_review_workflow.py
git commit -m "feat(backend): POST /requests/{id}/kam-assessment"
```

---

### Task 5: `POST /requests/{id}/bd-review`

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/tests/test_review_workflow.py`

**Interfaces:**
- Consumes: `BdReviewIn` (Task 3), `_assigned_request` helper (Task 4).
- Produces: `POST /requests/{id}/bd-review`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_review_workflow.py`:

```python
def _assessed_request(client, seed_reference_product, seed_service_pricing):
    """Extend _assigned_request through a submitted KAM assessment."""
    request_id, customer_token, kam_token, kam_user, mgr_token = _assigned_request(
        client, seed_reference_product, seed_service_pricing)
    client.post(f"/requests/{request_id}/kam-assessment",
                json={"kam_cost_usd": 125000, "kam_timeline_months": 6, "kam_notes": "New tool required."},
                headers=_auth(kam_token))
    return request_id, customer_token, kam_token, kam_user, mgr_token


def test_bd_review_requires_bd_manager_role(client, seed_reference_product, seed_service_pricing):
    request_id, _, kam_token, _, _ = _assessed_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(kam_token))
    assert resp.status_code == 403


def test_bd_review_approve_advances_status(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, mgr_token = _assessed_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(mgr_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "Approved — Awaiting KAM Response"


def test_bd_review_revise_requires_note_and_posts_internal_message(
    client, seed_reference_product, seed_service_pricing,
):
    request_id, _, kam_token, _, mgr_token = _assessed_request(client, seed_reference_product, seed_service_pricing)

    missing_note = client.post(f"/requests/{request_id}/bd-review", json={"decision": "revise"},
                                headers=_auth(mgr_token))
    assert missing_note.status_code == 422

    resp = client.post(f"/requests/{request_id}/bd-review",
                        json={"decision": "revise", "note": "Please re-check the tool cost."},
                        headers=_auth(mgr_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "Revision Requested"

    messages = client.get(f"/requests/{request_id}/messages", headers=_auth(kam_token)).json()
    internal = [m for m in messages if m["channel"] == "internal"]
    assert len(internal) == 1
    assert internal[0]["body"] == "Please re-check the tool cost."


def test_bd_review_409_before_assessment_submitted(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, mgr_token = _assigned_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(mgr_token))
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_review_workflow.py -v`
Expected: FAIL — the four new tests 404 (route doesn't exist) or error on the `GET /requests/{id}/messages` call (also not built yet).

- [ ] **Step 3: Implement the endpoint**

Add to `backend/app/routers/requests.py`, after `submit_kam_assessment`:

```python
@router.post("/{request_id}/bd-review", response_model=RequestDetailOut)
def bd_review(request_id: int, payload: BdReviewIn, db: Session = Depends(get_db),
              current_user: User = Depends(require_role("BD Manager"))):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    if req.status != "KAM Assessment Submitted":
        raise HTTPException(409, "This request isn't awaiting BD Manager review")

    if payload.decision == "approve":
        req.status = "Approved — Awaiting KAM Response"
    else:
        db.add(RequestMessage(request_id=req.id, channel="internal", sender_user_id=current_user.id,
                               body=payload.note[:MESSAGE_MAX_LEN]))
        req.status = "Revision Requested"

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req, include_routing=True)
```

This endpoint alone doesn't make `GET /requests/{id}/messages` exist yet — Step 4 will still fail on that call. That's expected; Task 7 builds it. Run only the tests this task added to confirm `bd-review` itself works:

- [ ] **Step 4: Run the bd-review tests in isolation to verify the endpoint itself passes**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_review_workflow.py -k "bd_review and not internal_message" -v`
Expected: PASS (`test_bd_review_requires_bd_manager_role`, `test_bd_review_approve_advances_status`, `test_bd_review_409_before_assessment_submitted`). `test_bd_review_revise_requires_note_and_posts_internal_message` still fails — its final assertion needs Task 7's `GET /requests/{id}/messages`, built next.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_review_workflow.py
git commit -m "feat(backend): POST /requests/{id}/bd-review — approve or revise-with-note"
```

---

### Task 6: `POST /requests/{id}/respond-to-customer`

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/tests/test_review_workflow.py`

**Interfaces:**
- Consumes: `RespondToCustomerIn` (Task 3), `_assigned_kam_or_404` (Task 4).
- Produces: `POST /requests/{id}/respond-to-customer`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_review_workflow.py`:

```python
def _approved_request(client, seed_reference_product, seed_service_pricing):
    """Extend _assessed_request through BD Manager approval."""
    request_id, customer_token, kam_token, kam_user, mgr_token = _assessed_request(
        client, seed_reference_product, seed_service_pricing)
    client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(mgr_token))
    return request_id, customer_token, kam_token, kam_user, mgr_token


def test_respond_to_customer_requires_assigned_kam(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, _ = _approved_request(client, seed_reference_product, seed_service_pricing)
    other_kam_token, _ = _login(client, "other@shaily.com", name="Other KAM", role="Key Account Manager")
    resp = client.post(f"/requests/{request_id}/respond-to-customer", json={"message": "All set."},
                        headers=_auth(other_kam_token))
    assert resp.status_code == 404


def test_respond_to_customer_posts_message_and_advances_status(client, seed_reference_product, seed_service_pricing):
    request_id, customer_token, kam_token, _, _ = _approved_request(
        client, seed_reference_product, seed_service_pricing)

    resp = client.post(f"/requests/{request_id}/respond-to-customer",
                        json={"message": "Approved — cost and timeline attached."}, headers=_auth(kam_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "Responded to Customer"

    messages = client.get(f"/requests/{request_id}/messages", headers=_auth(customer_token)).json()
    assert [m["body"] for m in messages] == ["Approved — cost and timeline attached."]
    assert all(m["channel"] == "customer" for m in messages)


def test_respond_to_customer_409_before_approved(client, seed_reference_product, seed_service_pricing):
    request_id, _, kam_token, _, _ = _assessed_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/respond-to-customer", json={"message": "hi"},
                        headers=_auth(kam_token))
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_review_workflow.py -k respond_to_customer -v`
Expected: FAIL — route doesn't exist (`test_respond_to_customer_posts_message_and_advances_status` also needs `GET /requests/{id}/messages`, still not built).

- [ ] **Step 3: Implement the endpoint**

Add to `backend/app/routers/requests.py`, after `bd_review`:

```python
@router.post("/{request_id}/respond-to-customer", response_model=RequestDetailOut)
def respond_to_customer(request_id: int, payload: RespondToCustomerIn, db: Session = Depends(get_db),
                         current_user: User = Depends(require_role("Key Account Manager"))):
    req = _assigned_kam_or_404(db, request_id, current_user)
    if req.status != "Approved — Awaiting KAM Response":
        raise HTTPException(409, "This request isn't ready to respond to the customer")

    db.add(RequestMessage(request_id=req.id, channel="customer", sender_user_id=current_user.id,
                           body=payload.message[:MESSAGE_MAX_LEN]))
    req.status = "Responded to Customer"
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req, include_routing=True)
```

- [ ] **Step 4: Run the respond-to-customer tests that don't depend on Task 7**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest "backend/tests/test_review_workflow.py::test_respond_to_customer_requires_assigned_kam" "backend/tests/test_review_workflow.py::test_respond_to_customer_409_before_approved" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_review_workflow.py
git commit -m "feat(backend): POST /requests/{id}/respond-to-customer"
```

---

### Task 7: `POST` and `GET /requests/{id}/messages`

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/tests/test_review_workflow.py`

**Interfaces:**
- Consumes: `MessageIn`/`MessageOut` (Task 3), `RequestMessage` (Task 2), `_visible_or_404` (existing, from core customer flow).
- Produces: `POST /requests/{id}/messages`, `GET /requests/{id}/messages`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_review_workflow.py`:

```python
def _responded_request(client, seed_reference_product, seed_service_pricing):
    """Extend _approved_request through the KAM's response to the customer."""
    request_id, customer_token, kam_token, kam_user, mgr_token = _approved_request(
        client, seed_reference_product, seed_service_pricing)
    client.post(f"/requests/{request_id}/respond-to-customer",
                json={"message": "Approved — cost and timeline attached."}, headers=_auth(kam_token))
    return request_id, customer_token, kam_token, kam_user, mgr_token


def test_bd_manager_cannot_post_messages(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, mgr_token = _responded_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/messages", json={"channel": "customer", "body": "hi"},
                        headers=_auth(mgr_token))
    assert resp.status_code == 403


def test_customer_can_only_post_customer_channel(client, seed_reference_product, seed_service_pricing):
    request_id, customer_token, _, _, _ = _responded_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/messages", json={"channel": "internal", "body": "hi"},
                        headers=_auth(customer_token))
    assert resp.status_code == 422


def test_customer_query_sets_status_and_kam_answer_reverts_it(client, seed_reference_product, seed_service_pricing):
    request_id, customer_token, kam_token, _, _ = _responded_request(
        client, seed_reference_product, seed_service_pricing)

    query = client.post(f"/requests/{request_id}/messages",
                         json={"channel": "customer", "body": "What's the tool lead time?"},
                         headers=_auth(customer_token))
    assert query.status_code == 201

    detail = client.get(f"/requests/{request_id}", headers=_auth(customer_token)).json()
    assert detail["status"] == "Customer Query"

    answer = client.post(f"/requests/{request_id}/messages",
                          json={"channel": "customer", "body": "4 weeks."}, headers=_auth(kam_token))
    assert answer.status_code == 201

    detail = client.get(f"/requests/{request_id}", headers=_auth(customer_token)).json()
    assert detail["status"] == "Responded to Customer"

    messages = client.get(f"/requests/{request_id}/messages", headers=_auth(customer_token)).json()
    assert [m["body"] for m in messages] == [
        "Approved — cost and timeline attached.", "What's the tool lead time?", "4 weeks.",
    ]


def test_customer_cannot_post_before_responded_to(client, seed_reference_product, seed_service_pricing):
    request_id, customer_token, _, _, _ = _approved_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/messages", json={"channel": "customer", "body": "hi"},
                        headers=_auth(customer_token))
    assert resp.status_code == 409


def test_get_messages_hides_internal_channel_from_customer(client, seed_reference_product, seed_service_pricing):
    request_id, customer_token, kam_token, _, mgr_token = _assessed_request(
        client, seed_reference_product, seed_service_pricing)
    client.post(f"/requests/{request_id}/bd-review",
                json={"decision": "revise", "note": "internal-only note"}, headers=_auth(mgr_token))

    kam_view = client.get(f"/requests/{request_id}/messages", headers=_auth(kam_token)).json()
    assert any(m["channel"] == "internal" for m in kam_view)

    customer_view = client.get(f"/requests/{request_id}/messages", headers=_auth(customer_token)).json()
    assert all(m["channel"] == "customer" for m in customer_view)
    assert customer_view == []


def test_get_messages_404_for_non_owner_customer(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, _ = _responded_request(client, seed_reference_product, seed_service_pricing)
    other_token, _ = _login(client, "someone@othercompany.com")
    resp = client.get(f"/requests/{request_id}/messages", headers=_auth(other_token))
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_review_workflow.py -v`
Expected: FAIL — every `messages` test 404s (route doesn't exist); the two carried-over tests from Tasks 5 and 6 that depend on `GET /requests/{id}/messages` also still fail.

- [ ] **Step 3: Implement the endpoints**

Add to `backend/app/routers/requests.py`, after `respond_to_customer`:

```python
@router.post("/{request_id}/messages", response_model=MessageOut, status_code=201)
def post_message(request_id: int, payload: MessageIn, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")

    if current_user.role == "BD Manager":
        raise HTTPException(403, "BD Manager can view messages but not post them")
    elif current_user.role == "Key Account Manager":
        if req.assigned_kam_id != current_user.id:
            raise HTTPException(404, "Request not found")
        if payload.channel == "customer" and req.status == "Customer Query":
            req.status = "Responded to Customer"
    else:
        if req.submitted_by != current_user.id:
            raise HTTPException(404, "Request not found")
        if payload.channel != "customer":
            raise HTTPException(422, "Customers may only post to the customer channel")
        if req.status not in ("Responded to Customer", "Customer Query"):
            raise HTTPException(409, "This request isn't open for customer messages yet")
        req.status = "Customer Query"

    msg = RequestMessage(request_id=req.id, channel=payload.channel, sender_user_id=current_user.id,
                          body=payload.body[:MESSAGE_MAX_LEN])
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return MessageOut(id=msg.id, request_id=msg.request_id, channel=msg.channel,
                       sender_user_id=msg.sender_user_id, sender_name=current_user.name,
                       body=msg.body, created_at=msg.created_at)


@router.get("/{request_id}/messages", response_model=list[MessageOut])
def list_messages(request_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    req, _ = _visible_or_404(db, request_id, current_user)
    q = db.query(RequestMessage).filter(RequestMessage.request_id == req.id)
    if current_user.role not in ("BD Manager", "Key Account Manager"):
        q = q.filter(RequestMessage.channel == "customer")
    msgs = q.order_by(RequestMessage.created_at).all()

    sender_ids = {m.sender_user_id for m in msgs}
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_(sender_ids))} if sender_ids else {}
    return [
        MessageOut(id=m.id, request_id=m.request_id, channel=m.channel, sender_user_id=m.sender_user_id,
                   sender_name=names.get(m.sender_user_id, ""), body=m.body, created_at=m.created_at)
        for m in msgs
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_review_workflow.py -v`
Expected: PASS (all tests in the file, including the ones carried over from Tasks 5 and 6).

- [ ] **Step 5: Run the full backend suite**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest -v`
Expected: PASS (every test in the backend suite).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_review_workflow.py
git commit -m "feat(backend): POST and GET /requests/{id}/messages — internal and customer threads"
```

---

## Frontend

### Task 8: `api.ts` — types and calls for the review workflow

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `Message` type; extends `RequestRow`/`RequestDetail` with `kam_cost_usd`, `kam_timeline_months`, `kam_notes`; `submitKamAssessment`, `bdReview`, `respondToCustomer`, `postMessage`, `getMessages` functions.

- [ ] **Step 1: Add the fields and functions**

In `frontend/lib/api.ts`, add three fields to `RequestRow` (after `urgency: string | null;`):

```ts
  kam_cost_usd: number | null;
  kam_timeline_months: number | null;
  kam_notes: string | null;
```

Add near the bottom, after `getAuditLog`:

```ts
export type Message = {
  id: number;
  request_id: number;
  channel: "internal" | "customer";
  sender_user_id: number;
  sender_name: string;
  body: string;
  created_at: string;
};

export async function submitKamAssessment(
  token: string,
  id: number,
  body: { kam_cost_usd: number; kam_timeline_months: number; kam_notes?: string }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/kam-assessment`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save that assessment — try again.");
  return resp.json();
}

export async function bdReview(
  token: string,
  id: number,
  body: { decision: "approve" | "revise"; note?: string }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/bd-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't record that review — try again.");
  return resp.json();
}

export async function respondToCustomer(token: string, id: number, message: string): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/respond-to-customer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ message }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't send that response — try again.");
  return resp.json();
}

export async function postMessage(
  token: string,
  id: number,
  channel: "internal" | "customer",
  body: string
): Promise<Message> {
  const resp = await fetch(`/api/requests/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ channel, body }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't send that message — try again.");
  return resp.json();
}

export async function getMessages(token: string, id: number): Promise<Message[]> {
  const resp = await fetch(`/api/requests/${id}/messages`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load messages — try again.");
  return resp.json();
}
```

- [ ] **Step 2: Verify the frontend still typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds (no other file references these new exports yet, so this only confirms `api.ts` itself is well-typed).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): API client types and calls for the request review workflow"
```

---

### Task 9: `MessageThread` — shared component for both channels

**Files:**
- Create: `frontend/components/MessageThread.tsx`

**Interfaces:**
- Consumes: `Message` type (Task 8).
- Produces: `<MessageThread messages={Message[]} emptyLabel={string} onPost={(body: string) => Promise<void>}? posting={boolean}? />` — used read-only (KAM/BD Manager on the internal channel is handled by the caller passing `undefined` for `onPost`) or with a composer.

- [ ] **Step 1: Write the component**

```tsx
"use client";
import { useState } from "react";

import { Message } from "@/lib/api";

export function MessageThread({
  messages,
  emptyLabel,
  onPost,
  posting = false,
  placeholder = "Write a message…",
}: {
  messages: Message[];
  emptyLabel: string;
  onPost?: (body: string) => Promise<void>;
  posting?: boolean;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  async function handleSend() {
    if (!onPost || !draft.trim()) return;
    await onPost(draft.trim());
    setDraft("");
  }

  return (
    <div className="flex flex-col gap-3">
      {messages.length === 0 ? (
        <p className="font-body text-sm text-ink-700/50">{emptyLabel}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {messages.map((m) => (
            <li key={m.id} className="rounded-lg border border-ink-700/10 bg-sand-50 px-3.5 py-2.5">
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <span className="font-body text-xs font-medium text-ink-700">{m.sender_name}</span>
                <span className="font-mono text-xs text-ink-700/50">{new Date(m.created_at).toLocaleString()}</span>
              </div>
              <p className="font-body text-sm text-ink-700">{m.body}</p>
            </li>
          ))}
        </ul>
      )}

      {onPost && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={placeholder}
            rows={2}
            className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={posting || !draft.trim()}
            className="rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend still typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds (component isn't imported anywhere yet, so this only confirms it's well-typed on its own).

- [ ] **Step 3: Commit**

```bash
git add frontend/components/MessageThread.tsx
git commit -m "feat(frontend): shared MessageThread component for internal/customer channels"
```

---

### Task 10: KAM workspace — assessment form, respond-to-customer, internal thread

**Files:**
- Modify: `frontend/app/dashboard/kam/page.tsx`

**Interfaces:**
- Consumes: `getRequestDetail`, `submitKamAssessment`, `respondToCustomer`, `getMessages`, `postMessage` (Task 8), `MessageThread` (Task 9).

- [ ] **Step 1: Extend the page**

In `frontend/app/dashboard/kam/page.tsx`, update the import block:

```tsx
"use client";
import { useEffect, useState } from "react";
import {
  ApiError, Message, RequestDetail, RequestRow,
  getMessages, getRequestDetail, listRequests, postMessage, respondToCustomer, submitKamAssessment,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";
import { MessageThread } from "@/components/MessageThread";
```

Add state (after `const [activeId, setActiveId] = useState<number | null>(null);`):

```tsx
  const [activeDetail, setActiveDetail] = useState<RequestDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [costInput, setCostInput] = useState("");
  const [timelineInput, setTimelineInput] = useState("");
  const [notesInput, setNotesInput] = useState("");
  const [actionError, setActionError] = useState("");
  const [submitting, setSubmitting] = useState(false);
```

Add a loader that fires whenever `activeId` changes, right after the existing `listRequests` effect:

```tsx
  useEffect(() => {
    if (!token || activeId == null) {
      setActiveDetail(null);
      setMessages([]);
      return;
    }
    getRequestDetail(token, activeId).then(setActiveDetail).catch(() => setActiveDetail(null));
    getMessages(token, activeId).then(setMessages).catch(() => setMessages([]));
  }, [token, activeId]);
```

Add handlers, near the other functions in the component body:

```tsx
  async function handleSubmitAssessment() {
    if (!token || !activeId) return;
    const cost = Number(costInput);
    const timeline = Number(timelineInput);
    if (!cost || !timeline) {
      setActionError("Enter a cost and a timeline before submitting the assessment.");
      return;
    }
    setSubmitting(true);
    setActionError("");
    try {
      const updated = await submitKamAssessment(token, activeId, {
        kam_cost_usd: cost, kam_timeline_months: timeline, kam_notes: notesInput || undefined,
      });
      setActiveDetail(updated);
      setRequests((prev) => prev.map((r) => (r.id === updated.id ? { ...r, status: updated.status } : r)));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "We couldn't save that assessment.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRespondToCustomer(message: string) {
    if (!token || !activeId) return;
    const updated = await respondToCustomer(token, activeId, message);
    setActiveDetail(updated);
    setRequests((prev) => prev.map((r) => (r.id === updated.id ? { ...r, status: updated.status } : r)));
  }

  async function handlePostInternal(body: string) {
    if (!token || !activeId) return;
    const msg = await postMessage(token, activeId, "internal", body);
    setMessages((prev) => [...prev, msg]);
  }

  async function handlePostCustomerFollowUp(body: string) {
    if (!token || !activeId) return;
    const msg = await postMessage(token, activeId, "customer", body);
    setMessages((prev) => [...prev, msg]);
    getRequestDetail(token, activeId).then(setActiveDetail).catch(() => {});
  }
```

Replace the closing paragraph of the `{active && (...)}` detail section — the `<p className="mt-4 ...">Full SKU, budget, and deliverable-schedule detail isn't ported yet.</p>` line — with the review-workflow UI:

```tsx
              {actionError && <Banner message={actionError} onDismiss={() => setActionError("")} />}

              {activeDetail && (active.status === `Assigned to ${user.name}` || active.status === "Revision Requested") && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Submit your assessment</h3>
                  {active.status === "Revision Requested" && (
                    <p className="font-body text-xs text-orange-700">
                      The BD Manager sent this back for revision — see the internal notes below.
                    </p>
                  )}
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <input
                      type="number" placeholder="Cost (USD)" value={costInput}
                      onChange={(e) => setCostInput(e.target.value)}
                      className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700 sm:w-40"
                    />
                    <input
                      type="number" placeholder="Timeline (months)" value={timelineInput}
                      onChange={(e) => setTimelineInput(e.target.value)}
                      className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700 sm:w-40"
                    />
                  </div>
                  <textarea
                    placeholder="Notes for the BD Manager" value={notesInput} rows={2}
                    onChange={(e) => setNotesInput(e.target.value)}
                    className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700"
                  />
                  <button
                    type="button" onClick={handleSubmitAssessment} disabled={submitting}
                    className="self-start rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Submit assessment
                  </button>
                </div>
              )}

              {activeDetail && active.status === "Approved — Awaiting KAM Response" && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Respond to the customer</h3>
                  <MessageThread
                    messages={[]}
                    emptyLabel="Approved — send your response to the customer."
                    onPost={handleRespondToCustomer}
                    placeholder="Cost, timeline, and any notes for the customer…"
                  />
                </div>
              )}

              {activeDetail && (active.status === "Responded to Customer" || active.status === "Customer Query") && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Customer conversation</h3>
                  <MessageThread
                    messages={messages.filter((m) => m.channel === "customer")}
                    emptyLabel="No messages yet."
                    onPost={handlePostCustomerFollowUp}
                  />
                </div>
              )}

              {activeDetail && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Internal notes (BD Manager)</h3>
                  <MessageThread
                    messages={messages.filter((m) => m.channel === "internal")}
                    emptyLabel="No internal notes yet."
                    onPost={handlePostInternal}
                  />
                </div>
              )}
```

- [ ] **Step 2: Verify the frontend typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke test**

Run the full stack (`docker-compose up -d --build` or `npm run dev` + backend locally), log in as a KAM with an assigned request in `Assigned to {name}` status, submit an assessment, confirm the request moves to `KAM Assessment Submitted` in the list.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/kam/page.tsx
git commit -m "feat(frontend): KAM workspace — assessment form, customer response, internal notes"
```

---

### Task 11: BD Manager review queue — approve or revise-with-note

**Files:**
- Modify: `frontend/app/dashboard/manager/kams/page.tsx`

**Interfaces:**
- Consumes: `bdReview`, `getMessages` (Task 8), `MessageThread` (Task 9, read-only — no `onPost`).

- [ ] **Step 1: Extend the page**

In `frontend/app/dashboard/manager/kams/page.tsx`, update the import block:

```tsx
"use client";
import { useEffect, useState } from "react";
import {
  ApiError, AuditEntry, Kam, Message, OrgKamLink, RequestRow,
  assignKam, bdReview, getAuditLog, getMessages, listKams, listOrgKamMap, listRequests, updateOrgKamMap,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { SelectField } from "@/components/SelectField";
import { EmptyState } from "@/components/EmptyState";
import { MessageThread } from "@/components/MessageThread";
```

Add state (after `const [assignPick, setAssignPick] = useState<Record<number, string>>({});`):

```tsx
  const [reviewNote, setReviewNote] = useState<Record<number, string>>({});
  const [reviewError, setReviewError] = useState("");
  const [threadOpenFor, setThreadOpenFor] = useState<number | null>(null);
  const [thread, setThread] = useState<Message[]>([]);
```

Add handlers, near `handleAssign`:

```tsx
  async function handleReview(requestId: number, decision: "approve" | "revise") {
    if (!token) return;
    const note = reviewNote[requestId];
    if (decision === "revise" && !note) {
      setReviewError("Add a note explaining what needs revision.");
      return;
    }
    try {
      await bdReview(token, requestId, { decision, note: decision === "revise" ? note : undefined });
      setReviewNote((prev) => ({ ...prev, [requestId]: "" }));
      loadAll(token);
    } catch (err) {
      setReviewError(err instanceof ApiError ? err.message : "We couldn't record that review.");
    }
  }

  async function toggleThread(requestId: number) {
    if (threadOpenFor === requestId) {
      setThreadOpenFor(null);
      return;
    }
    setThreadOpenFor(requestId);
    if (token) getMessages(token, requestId).then(setThread).catch(() => setThread([]));
  }
```

Add a new section, after the "Incoming customer requests — assign a KAM" `</section>` and before "Audit trail":

```tsx
        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Requests awaiting your review</h2>
          {reviewError && <Banner message={reviewError} onDismiss={() => setReviewError("")} />}
          <Card padding="p-0">
            {loading ? (
              <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
            ) : requests.filter((r) => r.status === "KAM Assessment Submitted").length === 0 ? (
              <EmptyState message="No assessments waiting on your review right now." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Brand / market</th>
                    <th className="px-4 py-3 font-medium">KAM cost</th>
                    <th className="px-4 py-3 font-medium">Timeline</th>
                    <th className="px-4 py-3 font-medium">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.filter((r) => r.status === "KAM Assessment Submitted").map((r) => (
                    <>
                      <tr key={r.id} className="border-b border-ink-700/5 last:border-0">
                        <td className="px-4 py-3 font-body text-sm text-ink-700">{r.org_name}</td>
                        <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.brand} · {r.market}</td>
                        <td className="px-4 py-3 font-body text-sm text-ink-700">
                          {r.kam_cost_usd != null ? `$${r.kam_cost_usd.toLocaleString()}` : "—"}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-ink-700/70">
                          {r.kam_timeline_months != null ? `${r.kam_timeline_months} mo` : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col gap-2">
                            <div className="flex gap-2">
                              <button
                                type="button" onClick={() => handleReview(r.id, "approve")}
                                className="rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50"
                              >
                                Approve
                              </button>
                              <button
                                type="button" onClick={() => handleReview(r.id, "revise")}
                                className="rounded-lg border border-orange-500 px-3 py-2 font-body text-sm text-orange-700 hover:bg-sand-50"
                              >
                                Send back
                              </button>
                              <button
                                type="button" onClick={() => toggleThread(r.id)}
                                className="rounded-lg border border-ink-700/15 px-3 py-2 font-body text-sm text-ink-700/70 hover:bg-sand-50"
                              >
                                {threadOpenFor === r.id ? "Hide messages" : "View messages"}
                              </button>
                            </div>
                            <textarea
                              placeholder="Revision note (required to send back)"
                              value={reviewNote[r.id] ?? ""} rows={2}
                              onChange={(e) => setReviewNote((prev) => ({ ...prev, [r.id]: e.target.value }))}
                              className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2 font-body text-sm text-ink-700"
                            />
                          </div>
                        </td>
                      </tr>
                      {threadOpenFor === r.id && (
                        <tr key={`${r.id}-thread`} className="border-b border-ink-700/5 last:border-0">
                          <td colSpan={5} className="bg-sand-50 px-4 py-4">
                            <MessageThread messages={thread} emptyLabel="No messages on this request yet." />
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>
```

- [ ] **Step 2: Verify the frontend typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke test**

As a BD Manager, confirm a request in `KAM Assessment Submitted` appears in the new section, approving advances it to `Approved — Awaiting KAM Response`, and sending back without a note shows the validation banner.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/manager/kams/page.tsx
git commit -m "feat(frontend): BD Manager review queue — approve/revise, read-only message thread"
```

---

### Task 12: Customer wizard — KAM response display and query composer

**Files:**
- Modify: `frontend/app/requests/[id]/page.tsx`

**Interfaces:**
- Consumes: `getMessages`, `postMessage` (Task 8), `MessageThread` (Task 9).

- [ ] **Step 1: Extend the page**

In `frontend/app/requests/[id]/page.tsx`, update the import block:

```tsx
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
  postMessage,
  selectOption,
  submitRequest,
  updateRequestStep1,
  updateServices,
} from "@/lib/api";
```

Add `MessageThread` to the component imports:

```tsx
import { MessageThread } from "@/components/MessageThread";
```

Add state (near the other `useState` declarations, after `submitBanner`):

```tsx
  const [messages, setMessages] = useState<Message[]>([]);
```

The page's respondable statuses:

```tsx
const RESPONDED_STATUSES = ["Responded to Customer", "Customer Query"];
```
(place this constant next to `STEPS`, near the top of the file).

Add a loader effect near the existing `detail`-loading effect (after it, so it re-fires whenever `detail` changes):

```tsx
  useEffect(() => {
    if (!token || !detail || !RESPONDED_STATUSES.includes(detail.status)) {
      setMessages([]);
      return;
    }
    getMessages(token, requestId).then(setMessages).catch(() => setMessages([]));
  }, [token, detail, requestId]);
```

Add a handler near the component's other handlers:

```tsx
  async function handlePostQuery(body: string) {
    if (!token) return;
    const msg = await postMessage(token, requestId, "customer", body);
    setMessages((prev) => [...prev, msg]);
    const updated = await getRequestDetail(token, requestId);
    setDetail(updated);
  }
```

Add the response/query section right after the existing `{!isDraft && (<Banner ... />)}` block:

```tsx
            {detail && RESPONDED_STATUSES.includes(detail.status) && (
              <Card className="flex flex-col gap-4">
                <div>
                  <h2 className="font-display text-base font-semibold text-forest-900">Shaily's response</h2>
                  {(detail.kam_cost_usd != null || detail.kam_timeline_months != null) && (
                    <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
                      <div>
                        <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Assessed cost</dt>
                        <dd className="font-body text-sm text-ink-700">
                          {detail.kam_cost_usd != null ? `$${detail.kam_cost_usd.toLocaleString()}` : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Timeline</dt>
                        <dd className="font-body text-sm text-ink-700">
                          {detail.kam_timeline_months != null ? `${detail.kam_timeline_months} months` : "—"}
                        </dd>
                      </div>
                    </dl>
                  )}
                </div>
                <MessageThread
                  messages={messages}
                  emptyLabel="No messages yet."
                  onPost={handlePostQuery}
                  placeholder="Ask a question about this response…"
                />
              </Card>
            )}
```

- [ ] **Step 2: Verify the frontend typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke test**

As the owning customer, open a request in `Responded to Customer` status, confirm the assessed cost/timeline and the KAM's message show, post a query, confirm the request's status flips to `Customer Query` (reload and check the wizard's read-only banner / status is reflected via a fresh `getRequestDetail` call).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/requests/[id]/page.tsx
git commit -m "feat(frontend): customer wizard — KAM response display and query composer"
```

---

## Documentation

### Task 13: Document the review workflow in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- None — documentation only.

- [ ] **Step 1: Add a new subsection**

In `CLAUDE.md`, after the existing "Multi-tenancy and roles" section and before "Backend layout (`backend/app/`)", add:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document the request review workflow in CLAUDE.md"
```
