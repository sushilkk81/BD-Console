# Customer Engagement Tracking & BD Manager Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture who a customer contact is (phone + job title) at login, log every customer login as a visit with the distinct pages they viewed, and notify every BD Manager in-app the first time a given customer logs in — so a BD Manager can act (assign a KAM) on real engagement signal.

**Architecture:** Two new tables (`customer_visits`, `notifications`) plus a `title` column on `users`; `POST /auth/login` gains required `title`/`phone` fields for non-`@shaily.com` domains and, as a side effect, writes a `customer_visits` row every login and fans out one `notifications` row per BD Manager on a customer's first-ever login. A lightweight `POST /activity/pageview` beacon (customer-only) appends distinct page paths to the current visit. Two new BD-Manager-only read endpoints (`GET /notifications`, `GET /customer-visits`) power a bell-icon dropdown in `Header` and a new `/dashboard/manager/customers` engagement-log page.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), Next.js App Router + TypeScript (frontend), pytest (backend tests only — no frontend test framework).

**Spec:** `docs/superpowers/customer-engagement-notifications/design.md`

## Global Constraints

- `VARCHAR` column lengths are enforced by Postgres but **not** by SQLite (the test DB) — every user-derived string written to a length-limited column must be truncated in code before the write, matching the `STATUS_MAX_LEN`/`DETAIL_MAX_LEN`/`COMMENT_MAX_LEN` pattern already used in `routers/kams.py` and `routers/requests.py`.
- Follow the existing one-router-per-resource layout (`routers/auth.py`, `routers/requests.py`, `routers/kams.py`, `routers/dashboard.py`) — new endpoints go in new router files (`routers/customer_visits.py`, `routers/notifications.py`), registered in `main.py`.
- `require_role(*roles)` (`deps.py`) is the only auth-scoping mechanism — no new auth machinery.
- No SMS/email delivery in this slice (design §2) — in-app notifications only.
- Notification fan-out happens only on a customer's first-ever login (design §3) — every login still writes a `customer_visits` row, but only the first fans out `notifications`.
- Pages-visited tracking is a distinct list of raw pathnames per session, not a timestamped clickstream (design §5).

---

### Task 1: Migration 0005 — `users.title`, `customer_visits`, `notifications`

**Files:**
- Create: `backend/alembic/versions/0005_customer_engagement.py`

**Interfaces:**
- Produces: `users.title` (String(50), nullable); table `customer_visits` (`id`, `user_id` FK, `org_id` FK, `session_id` String(36) unique, `contact_name`/`contact_email`/`contact_phone`/`contact_title`/`org_name` snapshot strings, `pages_visited` JSON, `started_at`); table `notifications` (`id`, `recipient_user_id` FK, `org_id` FK, `customer_visit_id` FK, `message` String(300), `link_path` String(200), `is_read` Boolean, `created_at`).

- [ ] **Step 1: Write the migration**

```python
"""Customer engagement tracking: users.title, customer_visits, notifications

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("title", sa.String(50), nullable=True))

    op.create_table(
        "customer_visits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False, unique=True),
        sa.Column("contact_name", sa.String(200), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(50), nullable=False),
        sa.Column("contact_title", sa.String(50), nullable=False),
        sa.Column("org_name", sa.String(200), nullable=False),
        sa.Column("pages_visited", sa.JSON, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipient_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_visit_id", sa.Integer, sa.ForeignKey("customer_visits.id"), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("link_path", sa.String(200), nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("customer_visits")
    op.drop_column("users", "title")
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
git add backend/alembic/versions/0005_customer_engagement.py
git commit -m "feat(backend): migration for users.title, customer_visits, and notifications"
```

---

### Task 2: ORM models — `User.title`, `CustomerVisit`, `Notification`

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: tables from Task 1.
- Produces: `User.title: Optional[str]`; `CustomerVisit` model class; `Notification` model class.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_models.py`:

```python
from app.models import CustomerVisit, Notification


def test_customer_visit_and_notification_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    org = Organization(name="Pfizer", kind="customer", domain="pfizer.com")
    db.add(org)
    db.flush()
    customer = User(org_id=org.id, email="a@pfizer.com", name="Alice", role="Customer",
                     phone="+1-555-0100", title="R&D Manager")
    db.add(customer)
    db.flush()
    visit = CustomerVisit(
        user_id=customer.id, org_id=org.id, session_id="11111111-1111-1111-1111-111111111111",
        contact_name="Alice", contact_email="a@pfizer.com", contact_phone="+1-555-0100",
        contact_title="R&D Manager", org_name="Pfizer", pages_visited=["/requests"],
    )
    db.add(visit)
    db.flush()
    db.add(Notification(
        recipient_user_id=customer.id, org_id=org.id, customer_visit_id=visit.id,
        message="Alice (Pfizer) logged in for the first time",
        link_path="/dashboard/manager/customers?visit=1",
    ))
    db.commit()

    fetched_user = db.query(User).one()
    assert fetched_user.title == "R&D Manager"

    fetched_visit = db.query(CustomerVisit).one()
    assert fetched_visit.pages_visited == ["/requests"]

    fetched_notification = db.query(Notification).one()
    assert fetched_notification.is_read is False
    assert "logged in" in fetched_notification.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_models.py::test_customer_visit_and_notification_roundtrip -v`
Expected: FAIL — `ImportError: cannot import name 'CustomerVisit'`.

- [ ] **Step 3: Add the column and models**

In `backend/app/models.py`, add `title` to `User`, right after `phone`:

```python
    title: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
```

Append two new classes at the end of the file:

```python
class CustomerVisit(Base):
    __tablename__ = "customer_visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_title: Mapped[str] = mapped_column(String(50), nullable=False)
    org_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pages_visited: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    customer_visit_id: Mapped[int] = mapped_column(ForeignKey("customer_visits.id"), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    link_path: Mapped[str] = mapped_column(String(200), nullable=False)
    is_read: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_models.py -v`
Expected: PASS (all tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat(backend): ORM models for CustomerVisit, Notification, and User.title"
```

---

### Task 3: Schemas — login extension, visit, pageview, notification payloads

**Files:**
- Modify: `backend/app/schemas.py`

**Interfaces:**
- Consumes: `CustomerVisit`, `Notification` fields from Task 2.
- Produces: `LoginRequest.title/phone`, `LoginResponse.session_id`; `CustomerVisitOut`, `PageviewIn`, `NotificationOut` Pydantic models.

- [ ] **Step 1: Extend `LoginRequest`/`LoginResponse` and add the new schemas**

In `backend/app/schemas.py`, replace the existing `LoginRequest` and `LoginResponse`:

```python
class LoginRequest(BaseModel):
    name: str
    email: EmailStr
    role: Optional[str] = None  # required when email domain is shaily.com
    title: Optional[str] = None  # required when email domain is not shaily.com
    phone: Optional[str] = None  # required when email domain is not shaily.com


class UserOut(BaseModel):
    id: int
    org_id: int
    name: str
    email: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    session_id: Optional[str] = None
```

Append at the end of the file:

```python
class CustomerVisitOut(BaseModel):
    id: int
    org_id: int
    org_name: str
    contact_name: str
    contact_email: str
    contact_phone: str
    contact_title: str
    pages_visited: list[str]
    started_at: dt.datetime


class PageviewIn(BaseModel):
    session_id: str
    page: str = Field(min_length=1)


class NotificationOut(BaseModel):
    id: int
    org_id: int
    message: str
    link_path: str
    is_read: bool
    created_at: dt.datetime
```

- [ ] **Step 2: Sanity-check schema import**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/python -c "import app.schemas"`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(backend): customer-engagement schemas — login extension, visit, pageview, notification"
```

---

### Task 4: `POST /auth/login` — require title/phone, log visits, notify on first login

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/tests/test_auth.py`
- Modify: `backend/tests/test_kams.py`, `backend/tests/test_review_workflow.py`, `backend/tests/test_dashboard.py`, `backend/tests/test_requests.py`, `backend/tests/test_reference_products.py` (shared `_login` test helpers — see Step 5)

**Interfaces:**
- Consumes: `CustomerVisit`, `Notification` (Task 2); `LoginRequest.title/phone`, `LoginResponse.session_id` (Task 3).
- Produces: every customer login writes one `CustomerVisit` row; a customer's first-ever login writes one `Notification` row per current `BD Manager` user.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_auth.py`:

```python
def test_login_customer_requires_title_and_phone(client):
    resp = client.post("/auth/login", json={"name": "Dr. Mehta", "email": "anaya@pfizer.com"})
    assert resp.status_code == 422


def test_login_customer_ok_with_title_and_phone(client):
    resp = client.post("/auth/login", json={
        "name": "Dr. Mehta", "email": "anaya@pfizer.com",
        "title": "R&D Manager", "phone": "+1-555-0100",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "Customer"
    assert body["session_id"]


def test_login_internal_has_no_session_id(client):
    resp = client.post("/auth/login", json={"name": "Mahesh", "email": "mahesh@shaily.com", "role": "BD Manager"})
    assert resp.json()["session_id"] is None


def test_first_customer_login_notifies_every_bd_manager(client):
    mgr1_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]
    mgr2_token = client.post("/auth/login", json={
        "name": "Rahul", "email": "rahul@shaily.com", "role": "BD Manager"}).json()["access_token"]

    client.post("/auth/login", json={
        "name": "Dr. Mehta", "email": "anaya@pfizer.com",
        "title": "R&D Manager", "phone": "+1-555-0100",
    })

    for token in (mgr1_token, mgr2_token):
        resp = client.get("/notifications", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert "Dr. Mehta" in resp.json()[0]["message"]


def test_second_customer_login_does_not_notify_again(client):
    mgr_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]

    login_body = {"name": "Dr. Mehta", "email": "anaya@pfizer.com",
                  "title": "R&D Manager", "phone": "+1-555-0100"}
    client.post("/auth/login", json=login_body)
    client.post("/auth/login", json=login_body)  # second login, same user

    resp = client.get("/notifications", headers={"Authorization": f"Bearer {mgr_token}"})
    assert len(resp.json()) == 1  # still just the one, from the first login
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_auth.py -v`
Expected: FAIL — `test_login_customer_requires_title_and_phone` fails (login currently succeeds with 200), `GET /notifications` doesn't exist yet (404) for the other new tests.

- [ ] **Step 3: Implement the login extension**

Replace `backend/app/routers/auth.py` in full:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CustomerVisit, Notification, Organization, User
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.security import create_token

router = APIRouter(prefix="/auth", tags=["auth"])

INTERNAL_DOMAIN = "shaily.com"
INTERNAL_ROLES = {"BD Manager", "Key Account Manager"}
CUSTOMER_TITLES = {"R&D Manager", "BD Manager"}
MESSAGE_MAX_LEN = 300  # matches Notification.message column width (models.py)
LINK_PATH_MAX_LEN = 200  # matches Notification.link_path column width (models.py)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    domain = payload.email.split("@", 1)[-1].lower()
    is_internal = domain == INTERNAL_DOMAIN

    if is_internal:
        if payload.role not in INTERNAL_ROLES:
            raise HTTPException(422, f"role must be one of {sorted(INTERNAL_ROLES)} for @{INTERNAL_DOMAIN} emails")
        role = payload.role
        org = db.query(Organization).filter_by(domain=INTERNAL_DOMAIN).first()
        if org is None:
            org = Organization(name="Shaily", kind="internal", domain=INTERNAL_DOMAIN)
            db.add(org)
            db.flush()
    else:
        if payload.title not in CUSTOMER_TITLES:
            raise HTTPException(422, f"title must be one of {sorted(CUSTOMER_TITLES)}")
        if not payload.phone:
            raise HTTPException(422, "phone is required")
        role = "Customer"
        org = db.query(Organization).filter_by(domain=domain).first()
        if org is None:
            org = Organization(name=domain, kind="customer", domain=domain)
            db.add(org)
            db.flush()

    user = db.query(User).filter_by(email=payload.email).first()
    if user is None:
        user = User(org_id=org.id, email=payload.email, name=payload.name, role=role)
        db.add(user)
        db.flush()
    else:
        user.name = payload.name
        user.role = role
    if not is_internal:
        user.title = payload.title
        user.phone = payload.phone

    session_id = None
    if not is_internal:
        db.flush()
        is_first_login = db.query(CustomerVisit).filter_by(user_id=user.id).first() is None
        session_id = str(uuid.uuid4())
        visit = CustomerVisit(
            user_id=user.id, org_id=org.id, session_id=session_id,
            contact_name=user.name, contact_email=user.email,
            contact_phone=user.phone, contact_title=user.title,
            org_name=org.name, pages_visited=[],
        )
        db.add(visit)
        db.flush()
        if is_first_login:
            bd_managers = (
                db.query(User)
                .join(Organization, User.org_id == Organization.id)
                .filter(Organization.domain == INTERNAL_DOMAIN, User.role == "BD Manager")
                .all()
            )
            message = f"{user.name} ({org.name}) logged in for the first time"[:MESSAGE_MAX_LEN]
            link_path = f"/dashboard/manager/customers?visit={visit.id}"[:LINK_PATH_MAX_LEN]
            for mgr in bd_managers:
                db.add(Notification(
                    recipient_user_id=mgr.id, org_id=org.id, customer_visit_id=visit.id,
                    message=message, link_path=link_path,
                ))

    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.org_id, user.role)
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user.id, org_id=user.org_id, name=user.name, email=user.email, role=user.role),
        session_id=session_id,
    )
```

- [ ] **Step 4: Update the shared `_login` test helpers so unrelated tests still pass**

`title`/`phone` are now required for any customer-domain login, so every other test file's `_login` helper needs to send them. In `backend/tests/test_kams.py`, `backend/tests/test_review_workflow.py`, `backend/tests/test_dashboard.py`, and `backend/tests/test_requests.py`, replace:

```python
def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]
```

with:

```python
def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    else:
        body["title"] = "R&D Manager"
        body["phone"] = "+1-555-0100"
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]
```

In `backend/tests/test_reference_products.py`, replace:

```python
def _login(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={"name": "Anaya", "email": email})
    return resp.json()["access_token"]
```

with:

```python
def _login(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={
        "name": "Anaya", "email": email, "title": "R&D Manager", "phone": "+1-555-0100"})
    return resp.json()["access_token"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_auth.py -v`
Expected: the two new-schema tests (`test_login_customer_requires_title_and_phone`, `test_login_internal_has_no_session_id`) PASS now; the notification tests still FAIL (404 — `GET /notifications` doesn't exist until Task 7). That's expected at this point.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth.py backend/tests/test_kams.py \
        backend/tests/test_review_workflow.py backend/tests/test_dashboard.py backend/tests/test_requests.py \
        backend/tests/test_reference_products.py
git commit -m "feat(backend): require title/phone at customer login, log visits, notify BD Managers on first login"
```

---

### Task 5: `POST /activity/pageview`

**Files:**
- Create: `backend/app/routers/customer_visits.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_customer_visits.py`

**Interfaces:**
- Consumes: `CustomerVisit` (Task 2), `PageviewIn` (Task 3).
- Produces: `POST /activity/pageview` — Customer-only, appends a distinct page path to the caller's current visit.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_customer_visits.py`:

```python
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


def _login_customer(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={
        "name": "Anaya", "email": email, "title": "R&D Manager", "phone": "+1-555-0100"})
    body = resp.json()
    return body["access_token"], body["session_id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_pageview_requires_customer_role(client):
    mgr_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]
    resp = client.post("/activity/pageview", json={"session_id": "x", "page": "/requests"},
                        headers=_auth(mgr_token))
    assert resp.status_code == 403


def test_pageview_rejects_foreign_session_id(client):
    token, _ = _login_customer(client, "anaya@pfizer.com")
    resp = client.post("/activity/pageview", json={"session_id": "not-mine", "page": "/requests"},
                        headers=_auth(token))
    assert resp.status_code == 404


def test_pageview_appends_distinct_pages(client):
    token, session_id = _login_customer(client)
    client.post("/activity/pageview", json={"session_id": session_id, "page": "/requests"},
                headers=_auth(token))
    client.post("/activity/pageview", json={"session_id": session_id, "page": "/requests/1"},
                headers=_auth(token))
    client.post("/activity/pageview", json={"session_id": session_id, "page": "/requests"},
                headers=_auth(token))  # repeat — should not duplicate

    mgr_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]
    resp = client.get("/customer-visits", headers=_auth(mgr_token))
    visit = resp.json()[0]
    assert visit["pages_visited"] == ["/requests", "/requests/1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_customer_visits.py -v`
Expected: FAIL — 404 Not Found on `/activity/pageview` (route doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Create `backend/app/routers/customer_visits.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import CustomerVisit, User
from app.schemas import CustomerVisitOut, PageviewIn

router = APIRouter(tags=["customer-visits"])

PAGE_MAX_LEN = 200  # keeps a single pageview entry bounded; not tied to a column width directly


@router.post("/activity/pageview", status_code=204)
def record_pageview(
    payload: PageviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("Customer")),
):
    visit = (
        db.query(CustomerVisit)
        .filter_by(session_id=payload.session_id, user_id=current_user.id)
        .first()
    )
    if visit is None:
        raise HTTPException(404, "Session not found")
    page = payload.page[:PAGE_MAX_LEN]
    if page not in visit.pages_visited:
        visit.pages_visited = visit.pages_visited + [page]
        db.commit()


@router.get("/customer-visits", response_model=list[CustomerVisitOut])
def list_customer_visits(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("BD Manager")),
):
    rows = db.query(CustomerVisit).order_by(CustomerVisit.started_at.desc()).all()
    return [
        CustomerVisitOut(
            id=v.id, org_id=v.org_id, org_name=v.org_name,
            contact_name=v.contact_name, contact_email=v.contact_email,
            contact_phone=v.contact_phone, contact_title=v.contact_title,
            pages_visited=v.pages_visited, started_at=v.started_at,
        )
        for v in rows
    ]
```

In `backend/app/main.py`, register the router (after the `kams_router` include):

```python
from app.routers.customer_visits import router as customer_visits_router
app.include_router(customer_visits_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_customer_visits.py -v`
Expected: PASS. (`test_pageview_appends_distinct_pages` also exercises `GET /customer-visits`, implemented in this same step — both endpoints ship together since they're tightly coupled.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/customer_visits.py backend/app/main.py backend/tests/test_customer_visits.py
git commit -m "feat(backend): POST /activity/pageview and GET /customer-visits"
```

---

### Task 6: `GET /notifications` and `POST /notifications/{id}/read`

**Files:**
- Create: `backend/app/routers/notifications.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_notifications.py`

**Interfaces:**
- Consumes: `Notification` (Task 2), `NotificationOut` (Task 3).
- Produces: `GET /notifications` (BD Manager, own rows only), `POST /notifications/{id}/read` (BD Manager, own rows only).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_notifications.py`:

```python
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


def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    else:
        body["title"] = "R&D Manager"
        body["phone"] = "+1-555-0100"
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_notifications_requires_bd_manager_role(client):
    kam_token, _ = _login(client, "mah@shaily.com", role="Key Account Manager")
    resp = client.get("/notifications", headers=_auth(kam_token))
    assert resp.status_code == 403


def test_notifications_scoped_to_recipient(client):
    mgr1_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    mgr2_token, _ = _login(client, "rahul@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")  # first customer login — notifies both managers

    resp1 = client.get("/notifications", headers=_auth(mgr1_token)).json()
    resp2 = client.get("/notifications", headers=_auth(mgr2_token)).json()
    assert len(resp1) == 1
    assert len(resp2) == 1
    assert resp1[0]["id"] != resp2[0]["id"]  # separate rows, not shared


def test_mark_notification_read(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")

    notif_id = client.get("/notifications", headers=_auth(mgr_token)).json()[0]["id"]
    resp = client.post(f"/notifications/{notif_id}/read", headers=_auth(mgr_token))
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


def test_mark_notification_read_rejects_other_managers_row(client):
    mgr1_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    mgr2_token, _ = _login(client, "rahul@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")

    mgr1_notif_id = client.get("/notifications", headers=_auth(mgr1_token)).json()[0]["id"]
    resp = client.post(f"/notifications/{mgr1_notif_id}/read", headers=_auth(mgr2_token))
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_notifications.py -v`
Expected: FAIL — 404 Not Found (routes don't exist).

- [ ] **Step 3: Implement the endpoints**

Create `backend/app/routers/notifications.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import Notification, User
from app.schemas import NotificationOut

router = APIRouter(tags=["notifications"])


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, org_id=n.org_id, message=n.message, link_path=n.link_path,
        is_read=n.is_read, created_at=n.created_at,
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("BD Manager")),
):
    rows = (
        db.query(Notification)
        .filter(Notification.recipient_user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return [_out(n) for n in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("BD Manager")),
):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_user_id != current_user.id:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return _out(n)
```

In `backend/app/main.py`, register the router:

```python
from app.routers.notifications import router as notifications_router
app.include_router(notifications_router)
```

- [ ] **Step 4: Run the notifications tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_notifications.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite to check nothing else broke**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest -v`
Expected: PASS — including the two `test_auth.py` notification tests from Task 4 that were failing until now (`GET /notifications` exists as of this task).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/notifications.py backend/app/main.py backend/tests/test_notifications.py
git commit -m "feat(backend): GET /notifications and POST /notifications/{id}/read"
```

---

### Task 7: `api.ts` — types and calls for engagement tracking & notifications

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: backend response shapes from Tasks 4–6.
- Produces: `login()` gains `title`/`phone` params and returns `session_id`; `recordPageview()`, `listCustomerVisits()`, `listNotifications()`, `markNotificationRead()`; `CustomerVisit`, `Notification` types.

- [ ] **Step 1: Extend `login()` and add the new calls/types**

Replace the existing `login` function:

```typescript
export async function login(name: string, email: string, role?: string, title?: string, phone?: string) {
  const resp = await fetch(`/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, role, title, phone }),
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't sign you in — check your name and email and try again.");
  }
  return resp.json() as Promise<{
    access_token: string;
    token_type: string;
    user: { id: number; org_id: number; name: string; email: string; role: string };
    session_id: string | null;
  }>;
}
```

Append near the bottom of the file (after `getMessages`):

```typescript
export async function recordPageview(token: string, sessionId: string, page: string): Promise<void> {
  await fetch(`/api/activity/pageview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ session_id: sessionId, page }),
  });
  // fire-and-forget — a failed beacon must never block navigation or surface an error
}

export type CustomerVisit = {
  id: number;
  org_id: number;
  org_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  contact_title: string;
  pages_visited: string[];
  started_at: string;
};

export async function listCustomerVisits(token: string): Promise<CustomerVisit[]> {
  const resp = await fetch(`/api/customer-visits`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the customer engagement log — try again.");
  return resp.json();
}

export type Notification = {
  id: number;
  org_id: number;
  message: string;
  link_path: string;
  is_read: boolean;
  created_at: string;
};

export async function listNotifications(token: string): Promise<Notification[]> {
  const resp = await fetch(`/api/notifications`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load notifications — try again.");
  return resp.json();
}

export async function markNotificationRead(token: string, id: number): Promise<Notification> {
  const resp = await fetch(`/api/notifications/${id}/read`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't update that notification — try again.");
  return resp.json();
}
```

- [ ] **Step 2: Verify the frontend still typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds (existing callers of `login()` pass positional args that still match — `role` stays the 3rd param, new params are optional and appended after it).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): API client types and calls for engagement tracking and notifications"
```

---

### Task 8: Login page — role/title + phone fields for customer logins

**Files:**
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/lib/session.ts` (store `session_id`)

**Interfaces:**
- Consumes: `login()` (Task 7).
- Produces: customer logins collect and submit `title`/`phone`; `session_id` persisted to `localStorage` as `bdconsole_session_id`.

- [ ] **Step 1: Extend the login page**

In `frontend/app/login/page.tsx`, add a title dropdown constant near `INTERNAL_ROLES`:

```typescript
const CUSTOMER_TITLES = ["R&D Manager", "BD Manager"];
```

Add two more pieces of state alongside `role`:

```typescript
const [title, setTitle] = useState("");
const [phone, setPhone] = useState("");
```

Update `validate()`:

```typescript
function validate(): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!name.trim()) errors.name = "Enter your name.";
  if (!email.trim()) errors.email = "Enter your email.";
  if (isInternal && !role) errors.role = "Select your role.";
  if (!isInternal && email.trim()) {
    if (!title) errors.title = "Select your role in the organization.";
    if (!phone.trim()) errors.phone = "Enter your phone number.";
  }
  return errors;
}
```

Update `handleSubmit`'s call to `login()` and the `localStorage` writes:

```typescript
const result = await login(name, email, isInternal ? role : undefined, isInternal ? undefined : title,
                            isInternal ? undefined : phone);
localStorage.setItem("bdconsole_token", result.access_token);
localStorage.setItem("bdconsole_user", JSON.stringify(result.user));
if (result.session_id) {
  localStorage.setItem("bdconsole_session_id", result.session_id);
}
router.push(LANDING[result.user.role as keyof typeof LANDING] ?? "/requests");
```

Add the new fields to the form, right after the existing internal-role reveal block (mirroring its animated-reveal pattern, gated on `!isInternal` and only once an email is entered):

```tsx
<div
  className={`grid transition-[grid-template-rows,opacity] duration-200 motion-reduce:transition-none ${
    !isInternal && email.trim() ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
  }`}
  aria-hidden={isInternal || !email.trim()}
  inert={isInternal || !email.trim() ? true : undefined}
>
  <div className="overflow-hidden flex flex-col gap-4">
    <SelectField
      label="Your role in the organization"
      name="title"
      value={title}
      onChange={setTitle}
      placeholder="Select…"
      options={CUSTOMER_TITLES.map((t) => ({ value: t, label: t }))}
      error={fieldErrors.title}
    />
    <TextField label="Phone number" name="phone" type="tel" value={phone} onChange={setPhone}
               error={fieldErrors.phone} />
  </div>
</div>
```

- [ ] **Step 2: Verify the frontend typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke test**

Run `npm run dev` (with `API_URL` pointing at a running backend), open `/login`, enter a non-`@shaily.com` email, confirm the role dropdown and phone field appear, and that submitting without them shows the new validation errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/login/page.tsx
git commit -m "feat(frontend): collect role-in-organization and phone at customer login"
```

---

### Task 9: Pageview beacon — track page navigation for customer sessions

**Files:**
- Create: `frontend/components/PageviewBeacon.tsx`
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Consumes: `recordPageview()` (Task 7); `bdconsole_session_id`/`bdconsole_token`/`bdconsole_user` from `localStorage` (Task 8).
- Produces: a route-change beacon mounted once at the root, active only for Customer sessions.

- [ ] **Step 1: Write the component**

Create `frontend/components/PageviewBeacon.tsx`:

```tsx
"use client";
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { recordPageview } from "@/lib/api";

export function PageviewBeacon() {
  const pathname = usePathname();

  useEffect(() => {
    const token = localStorage.getItem("bdconsole_token");
    const sessionId = localStorage.getItem("bdconsole_session_id");
    const rawUser = localStorage.getItem("bdconsole_user");
    if (!token || !sessionId || !rawUser) return;
    const user = JSON.parse(rawUser) as { role: string };
    if (user.role !== "Customer") return;
    recordPageview(token, sessionId, pathname).catch(() => {
      // fire-and-forget — a beacon failure must never surface to the customer
    });
  }, [pathname]);

  return null;
}
```

- [ ] **Step 2: Mount it in the root layout**

In `frontend/app/layout.tsx`, import and render it inside `<body>`:

```tsx
import { PageviewBeacon } from "@/components/PageviewBeacon";
```

```tsx
      <body>
        <PageviewBeacon />
        {children}
      </body>
```

- [ ] **Step 3: Verify the frontend still typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds. (`RootLayout` is a server component; `PageviewBeacon` is a client component rendered inside it, which Next.js supports without extra wiring.)

- [ ] **Step 4: Commit**

```bash
git add frontend/components/PageviewBeacon.tsx frontend/app/layout.tsx
git commit -m "feat(frontend): pageview beacon for customer engagement tracking"
```

---

### Task 10: `Header` — notification bell for BD Manager

**Files:**
- Modify: `frontend/components/Header.tsx`
- Modify: `frontend/app/dashboard/manager/page.tsx`, `frontend/app/dashboard/manager/kams/page.tsx` (pass `token` prop)

**Interfaces:**
- Consumes: `listNotifications()`, `markNotificationRead()` (Task 7).
- Produces: `Header` gains an optional `token` prop; when `role === "BD Manager"` and `token` is present, renders a bell with an unread-count badge and a click-through dropdown.

- [ ] **Step 1: Extend `Header`**

Replace `frontend/components/Header.tsx` in full:

```tsx
"use client";
import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Notification, listNotifications, markNotificationRead } from "@/lib/api";

type Role = "BD Manager" | "Key Account Manager" | "Customer";

const NAV: Record<Role, { label: string; href: string }[]> = {
  "BD Manager": [
    { label: "Command centre", href: "/dashboard/manager" },
    { label: "KAM & assignments", href: "/dashboard/manager/kams" },
    { label: "Customer activity", href: "/dashboard/manager/customers" },
  ],
  "Key Account Manager": [{ label: "My workspace", href: "/dashboard/kam" }],
  Customer: [{ label: "Requests", href: "/requests" }],
};

const POLL_INTERVAL_MS = 30_000;

function NotificationBell({ token }: { token: string }) {
  const router = useRouter();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);

  function load() {
    listNotifications(token).then(setNotifications).catch(() => {
      // a failed poll should never break header rendering — just skip this cycle
    });
  }

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    window.addEventListener("focus", load);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", load);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  async function handleClick(n: Notification) {
    setOpen(false);
    try {
      await markNotificationRead(token, n.id);
    } finally {
      router.push(n.link_path);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
        className="relative rounded-full p-2 text-ink-700/70 transition-colors hover:bg-sand-50 hover:text-forest-600"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             aria-hidden="true">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-orange-500 px-1 font-mono text-[10px] text-white">
            {unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 rounded-xl border border-ink-700/10 bg-white shadow-lg">
          {notifications.length === 0 ? (
            <p className="p-4 font-body text-sm text-ink-700/70">No notifications yet.</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {notifications.map((n) => (
                <li key={n.id} className="border-b border-ink-700/5 last:border-0">
                  <button
                    type="button"
                    onClick={() => handleClick(n)}
                    className={`w-full px-4 py-3 text-left font-body text-sm transition-colors hover:bg-sand-50 ${
                      n.is_read ? "text-ink-700/60" : "text-ink-700"
                    }`}
                  >
                    {n.message}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function Header({ userName, role, token }: { userName?: string; role?: Role; token?: string }) {
  const links = role ? NAV[role] : [];
  return (
    <header className="border-b border-ink-700/10 bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <Image src="/shaily-logo.png" alt="Shaily" width={140} height={37} priority />
          <span className="font-display text-base font-medium text-forest-900">BD Console</span>
        </div>
        {links.length > 0 && (
          <nav className="flex flex-wrap gap-3 sm:gap-5" aria-label="Primary">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="font-body text-sm text-ink-700/70 transition-colors hover:text-forest-600"
              >
                {l.label}
              </Link>
            ))}
          </nav>
        )}
        <div className="flex items-center gap-3">
          {role === "BD Manager" && token && <NotificationBell token={token} />}
          {userName && <span className="font-body text-sm text-ink-700/70">{userName}</span>}
        </div>
      </div>
      <div
        className="h-1 w-full bg-gradient-to-r from-forest-600 via-lime-500 to-orange-500"
        aria-hidden="true"
      />
    </header>
  );
}
```

- [ ] **Step 2: Pass `token` from the two BD Manager pages**

In `frontend/app/dashboard/manager/page.tsx` and `frontend/app/dashboard/manager/kams/page.tsx`, update the `<Header .../>` call:

```tsx
<Header userName={user.name} role={user.role} token={token ?? undefined} />
```

(Both pages already have `token` in scope from `useRoleGuard("BD Manager")`.)

- [ ] **Step 3: Verify the frontend typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual smoke test**

Log in as a BD Manager, confirm the bell renders with no badge when there are no notifications; in a second browser/incognito session log in as a brand-new customer; back in the BD Manager tab (wait for the 30s poll or refocus the window) confirm the badge appears and clicking a notification navigates to `/dashboard/manager/customers` and marks it read.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/Header.tsx frontend/app/dashboard/manager/page.tsx frontend/app/dashboard/manager/kams/page.tsx
git commit -m "feat(frontend): BD Manager notification bell in Header"
```

---

### Task 11: `/dashboard/manager/customers` — engagement log page

**Files:**
- Create: `frontend/app/dashboard/manager/customers/page.tsx`

**Interfaces:**
- Consumes: `listCustomerVisits()` (Task 7); `Header`'s new `Customer activity` nav link (Task 10).
- Produces: a BD-Manager-only page listing every customer visit.

- [ ] **Step 1: Write the page**

Create `frontend/app/dashboard/manager/customers/page.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";
import { ApiError, CustomerVisit, listCustomerVisits } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { EmptyState } from "@/components/EmptyState";

export default function CustomerActivityPage() {
  const { token, user } = useRoleGuard("BD Manager");
  const [visits, setVisits] = useState<CustomerVisit[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    listCustomerVisits(token)
      .then(setVisits)
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load customer activity."))
      .finally(() => setLoading(false));
  }, [token]);

  if (!token || !user) return null;

  return (
    <>
      <Header userName={user.name} role={user.role} token={token} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <h1 className="font-display text-lg font-semibold text-forest-900">Customer activity</h1>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <Card padding="p-0">
          {loading ? (
            <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
          ) : error ? null : visits.length === 0 ? (
            <EmptyState message="No customer logins recorded yet." />
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Organization</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Access date</th>
                  <th className="px-4 py-3 font-medium">Pages visited</th>
                </tr>
              </thead>
              <tbody>
                {visits.map((v) => (
                  <tr key={v.id} className="border-b border-ink-700/5 last:border-0">
                    <td className="px-4 py-3 font-body text-sm text-ink-700">
                      {v.contact_name}
                      <span className="block font-body text-xs text-ink-700/50">{v.contact_title}</span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-ink-700/70">{v.org_name}</td>
                    <td className="px-4 py-3 font-body text-sm text-ink-700/70">{v.contact_email}</td>
                    <td className="px-4 py-3 font-body text-sm text-ink-700/70">{v.contact_phone}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ink-700/70">
                      {new Date(v.started_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-body text-xs text-ink-700/70">
                      {v.pages_visited.length === 0 ? "—" : v.pages_visited.join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </main>
    </>
  );
}
```

- [ ] **Step 2: Verify the frontend typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual smoke test**

Log in as a customer (creating a visit), navigate a couple of pages, then log in as a BD Manager and open "Customer activity" from the nav — confirm the row appears with the right name/org/email/phone/date and the pages visited.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/manager/customers/page.tsx
git commit -m "feat(frontend): BD Manager customer activity / engagement log page"
```

---

### Task 12: Document the feature in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: an "Customer engagement tracking & notifications" subsection under Architecture, matching the depth of the existing "Request review workflow" subsection.

- [ ] **Step 1: Add a new subsection**

In `CLAUDE.md`, after the "### Request review workflow" subsection and before "### Backend layout (`backend/app/`)", add:

```markdown
### Customer engagement tracking & notifications

Every customer login (`POST /auth/login`, non-`@shaily.com` domains) now
requires a `title` (their role in the organization — `R&D Manager` or
`BD Manager`, metadata only, unrelated to the app's own `role` field) and a
`phone` number, and writes one `customer_visits` row snapshotting the
contact's name/email/phone/title/org at that moment, plus the distinct
pages they visit that session (`POST /activity/pageview`, Customer-only,
correlated by a `session_id` issued at login). A customer's **first-ever**
login additionally fans out one `notifications` row per current `BD
Manager` user — repeat logins by the same customer keep extending the
visit log but don't notify again. `GET /notifications` and
`GET /customer-visits` (both BD-Manager-only) power the bell icon in
`Header` and the `/dashboard/manager/customers` engagement-log page,
respectively. KAM assignment itself is unchanged — a BD Manager still uses
`org_kam_map` (see above) to assign or reassign a KAM once they've seen
the notification.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document customer engagement tracking and notifications in CLAUDE.md"
```
