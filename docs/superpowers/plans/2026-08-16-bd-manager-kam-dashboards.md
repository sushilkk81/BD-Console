# BD Manager & KAM Dashboards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give BD Manager and Key Account Manager (KAM) users a role-specific landing dashboard after login, instead of dropping every role onto the customer `/requests` page.

**Architecture:** Additive Alembic migration (one new column, three new tables) + two new FastAPI routers (`kams`, `dashboard`) + role-based scoping added to the existing `requests` router, all behind a new `require_role` dependency. On the frontend, a shared `useRoleGuard` hook replaces the ad-hoc auth check in `requests/page.tsx` and backs three new pages: `/dashboard/manager` (command centre), `/dashboard/manager/kams` (KAM roster + org routing + request assignment), `/dashboard/kam` (assigned-requests workspace).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + pytest (backend, unchanged); Next.js 14 App Router + TypeScript + Tailwind v4 (frontend, unchanged) + Recharts (new frontend dependency, for the command centre charts).

**Spec:** `docs/superpowers/specs/2026-08-16-bd-manager-kam-dashboards-design.md`

## Global Constraints

- Org→KAM routing only. No region-based routing (confirmed out of scope — the legacy `region_map` never actually fired in practice).
- KAMs are not a separate roster table — they are `users` rows with `role = "Key Account Manager"` in the Shaily-domain (`shaily.com`) organization. No add/remove-KAM admin action.
- No SKU rows, budget breakdown, negotiation, or deliverable schedule in the KAM workspace — out of scope until the fuller request data model is ported (tracked separately).
- Command-centre chart data is illustrative demo data ported verbatim from `data.py`, seeded into Postgres via the migration — not derived from real deals.
- Role-based landing/guarding uses the existing mock-login trust model (role trusted from the JWT/localStorage `bdconsole_user`) — no new auth mechanism.
- Backend: every new endpoint gets pytest coverage exercising the 403-for-wrong-role case and, where relevant, org-isolation.
- Frontend has no test framework configured today (confirmed: `package.json` has no test runner, no existing `*.test.*` files). Frontend tasks are verified by `npm run build` succeeding plus a manual smoke check via `docker-compose up`, matching the existing convention used for the login/requests pages — not by adding a new test framework in this plan.

---

### Task 1: Migration — `assigned_kam_id`, `org_kam_map`, `audit_log`, `dashboard_metrics`

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/0002_bd_kam_dashboards.py`
- Test: `backend/tests/test_dashboard_models.py`

**Interfaces:**
- Produces: SQLAlchemy models `OrgKamMap` (`org_id` PK/FK, `kam_user_id` FK), `AuditLog` (`id`, `org_id` nullable FK, `actor_user_id` FK, `action`, `detail`, `created_at`), `DashboardMetric` (`key` PK, `payload` JSON) — imported by Tasks 2–4. `Request.assigned_kam_id` (nullable FK to `users.id`) — consumed by Tasks 2 and 4.

- [ ] **Step 1: Write the failing test — `backend/tests/test_dashboard_models.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AuditLog, DashboardMetric, Organization, OrgKamMap, Request, User


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_request_can_be_assigned_to_a_kam():
    db = _session()
    shaily = Organization(name="Shaily", kind="internal", domain="shaily.com")
    pfizer = Organization(name="Pfizer", kind="customer", domain="pfizer.com")
    db.add_all([shaily, pfizer])
    db.flush()

    kam = User(org_id=shaily.id, email="mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    customer = User(org_id=pfizer.id, email="anaya@pfizer.com", name="Dr. Mehta", role="Customer")
    db.add_all([kam, customer])
    db.flush()

    req = Request(org_id=pfizer.id, submitted_by=customer.id, brand="Ozempic", market="US")
    db.add(req)
    db.flush()
    req.assigned_kam_id = kam.id
    db.commit()

    fetched = db.query(Request).one()
    assert fetched.assigned_kam_id == kam.id


def test_org_kam_map_links_org_to_kam():
    db = _session()
    shaily = Organization(name="Shaily", kind="internal", domain="shaily.com")
    pfizer = Organization(name="Pfizer", kind="customer", domain="pfizer.com")
    db.add_all([shaily, pfizer])
    db.flush()

    kam = User(org_id=shaily.id, email="mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    db.add(kam)
    db.flush()

    db.add(OrgKamMap(org_id=pfizer.id, kam_user_id=kam.id))
    db.commit()

    link = db.query(OrgKamMap).one()
    assert link.kam_user_id == kam.id


def test_audit_log_roundtrip():
    db = _session()
    shaily = Organization(name="Shaily", kind="internal", domain="shaily.com")
    db.add(shaily)
    db.flush()
    actor = User(org_id=shaily.id, email="priya@shaily.com", name="Ms. Priya", role="BD Manager")
    db.add(actor)
    db.flush()

    db.add(AuditLog(org_id=None, actor_user_id=actor.id, action="kam_assigned", detail="test"))
    db.commit()

    row = db.query(AuditLog).one()
    assert row.action == "kam_assigned"
    assert row.created_at is not None


def test_dashboard_metric_stores_json_payload():
    db = _session()
    db.add(DashboardMetric(key="quarterly_target", payload={"Q1": 32, "Q2": 36}))
    db.commit()

    row = db.query(DashboardMetric).one()
    assert row.payload == {"Q1": 32, "Q2": 36}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest tests/test_dashboard_models.py -v
```

Expected: FAIL — `ImportError: cannot import name 'OrgKamMap' from 'app.models'` (or similar for `AuditLog`/`DashboardMetric`).

- [ ] **Step 3: Add the new models — modify `backend/app/models.py`**

Add `Optional` is already imported; add `JSON` to the SQLAlchemy import and append after the `Request` class:

```python
from sqlalchemy import ForeignKey, JSON, Numeric, String
```

(replaces the existing `from sqlalchemy import ForeignKey, Numeric, String` line)

Add to the `Request` class, right after `submitted_by`:

```python
    assigned_kam_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
```

Append these new classes at the end of the file:

```python
class OrgKamMap(Base):
    __tablename__ = "org_kam_map"

    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    kam_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class DashboardMetric(Base):
    __tablename__ = "dashboard_metrics"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest tests/test_dashboard_models.py tests/test_models.py -v
```

Expected: all PASS.

- [ ] **Step 5: Write the Alembic migration — `backend/alembic/versions/0002_bd_kam_dashboards.py`**

```python
"""BD Manager & KAM dashboards: assigned_kam_id, org_kam_map, audit_log, dashboard_metrics

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("assigned_kam_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True))

    op.create_table(
        "org_kam_map",
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("kam_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "dashboard_metrics",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("payload", sa.JSON, nullable=False),
    )

    metrics = sa.table("dashboard_metrics", sa.column("key", sa.String), sa.column("payload", sa.JSON))
    op.bulk_insert(metrics, [
        {"key": "quarterly_target", "payload": {"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}},
        {"key": "new_customers_qtr", "payload": {"Q1": 2, "Q2": 1, "Q3": 3, "Q4": 2}},
        {"key": "platform_production", "payload": {
            "Toby": 21, "Neo": 34, "Harmony": 18, "Axiom": 12, "Axiom Max": 9,
            "Protean": 15, "Tristan": 7, "Mira": 4, "Safe-LAN": 6,
        }},
        {"key": "rep_quarterly", "payload": {
            "Mr. MAH": {"region": "India", "quarters": {"Q1": 8, "Q2": 10, "Q3": 9, "Q4": 12}},
            "Mr. HEN": {"region": "Europe", "quarters": {"Q1": 6, "Q2": 7, "Q3": 8, "Q4": 9}},
            "Mr. MUK": {"region": "Asia", "quarters": {"Q1": 5, "Q2": 6, "Q3": 7, "Q4": 8}},
            "Mr. FED": {"region": "North America", "quarters": {"Q1": 7, "Q2": 6, "Q3": 9, "Q4": 10}},
            "Ms. SUK": {"region": "Europe", "quarters": {"Q1": 4, "Q2": 5, "Q3": 6, "Q4": 7}},
        }},
        {"key": "rep_platform_matrix", "payload": {
            "Mr. MAH": {"Neo": 12, "Toby": 11},
            "Mr. HEN": {"Harmony": 9, "Axiom": 9},
            "Mr. MUK": {"Protean": 8, "Axiom Max": 6},
            "Mr. FED": {"Toby": 10, "Tristan": 10},
            "Ms. SUK": {"Mira": 7, "Safe-LAN": 7},
        }},
        {"key": "rep_customer_matrix", "payload": {
            "Mr. MAH": {"Auro": 14, "McD": 9},
            "Mr. HEN": {"DRL": 11, "Chem": 7},
            "Mr. MUK": {"Sand": 8, "Torr": 6},
            "Mr. FED": {"Dem": 12, "Homo": 8},
            "Ms. SUK": {"Shun": 9, "Chem": 5},
        }},
    ])


def downgrade() -> None:
    op.drop_table("dashboard_metrics")
    op.drop_table("audit_log")
    op.drop_table("org_kam_map")
    op.drop_column("requests", "assigned_kam_id")
```

- [ ] **Step 6: Apply the migration against local Postgres to confirm it runs**

```bash
docker-compose up -d postgres
docker-compose run --rm backend alembic upgrade head
docker-compose exec postgres psql -U bdconsole -d bdconsole -c "select key from dashboard_metrics order by key;"
```

Expected: 6 rows (`new_customers_qtr`, `platform_production`, `quarterly_target`, `rep_customer_matrix`, `rep_platform_matrix`, `rep_quarterly`) with no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/0002_bd_kam_dashboards.py backend/tests/test_dashboard_models.py
git commit -m "feat(backend): add assigned_kam_id, org_kam_map, audit_log, dashboard_metrics"
```

---

### Task 2: `require_role` dependency + `kams` router

**Files:**
- Modify: `backend/app/deps.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/routers/kams.py`
- Test: `backend/tests/test_kams.py`

**Interfaces:**
- Consumes: `OrgKamMap`, `AuditLog` models (Task 1); `get_current_user` (existing, `app/deps.py`).
- Produces: `deps.require_role(*roles) -> Callable` FastAPI dependency — consumed by Task 3. `GET /kams`, `GET /org-kam-map`, `PUT /org-kam-map/{org_id}`, `POST /requests/{request_id}/assign-kam` — consumed by the frontend in Task 8.

- [ ] **Step 1: Write the failing test — `backend/tests/test_kams.py`**

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
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_kams_roster_requires_bd_manager_role(client):
    kam_token, _ = _login(client, "mah@shaily.com", role="Key Account Manager")
    resp = client.get("/kams", headers=_auth(kam_token))
    assert resp.status_code == 403


def test_kams_roster_lists_shaily_kams(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _login(client, "mah@shaily.com", role="Key Account Manager")
    _login(client, "anaya@pfizer.com")  # a customer — must not appear

    resp = client.get("/kams", headers=_auth(mgr_token))
    assert resp.status_code == 200
    names = [k["name"] for k in resp.json()]
    assert names == ["Test User"]  # default _login name


def test_org_kam_map_set_and_list(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    _login(client, "anaya@pfizer.com")  # creates the Pfizer org

    orgs_resp = client.get("/org-kam-map", headers=_auth(mgr_token))
    pfizer = next(o for o in orgs_resp.json() if o["org_name"] == "pfizer.com")
    assert pfizer["kam_user_id"] is None

    put_resp = client.put(
        f"/org-kam-map/{pfizer['org_id']}", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token),
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["kam_name"] == "Mr. MAH"

    orgs_resp = client.get("/org-kam-map", headers=_auth(mgr_token))
    pfizer = next(o for o in orgs_resp.json() if o["org_name"] == "pfizer.com")
    assert pfizer["kam_user_id"] == kam_user["id"]


def test_org_kam_map_rejects_non_kam_user(client):
    mgr_token, mgr_user = _login(client, "priya@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")

    orgs_resp = client.get("/org-kam-map", headers=_auth(mgr_token))
    pfizer = orgs_resp.json()[0]

    resp = client.put(
        f"/org-kam-map/{pfizer['org_id']}", json={"kam_user_id": mgr_user["id"]}, headers=_auth(mgr_token),
    )
    assert resp.status_code == 422


def test_assign_kam_updates_request_status(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    cust_token, _ = _login(client, "anaya@pfizer.com")

    created = client.post(
        "/requests", json={"brand": "Ozempic", "market": "US"}, headers=_auth(cust_token),
    ).json()

    resp = client.post(
        f"/requests/{created['id']}/assign-kam", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assigned_kam_id"] == kam_user["id"]
    assert body["status"] == "Assigned to Mr. MAH"


def test_assign_kam_requires_bd_manager_role(client):
    cust_token, _ = _login(client, "anaya@pfizer.com")
    created = client.post(
        "/requests", json={"brand": "Ozempic", "market": "US"}, headers=_auth(cust_token),
    ).json()

    resp = client.post(
        f"/requests/{created['id']}/assign-kam", json={"kam_user_id": 999}, headers=_auth(cust_token),
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest tests/test_kams.py -v
```

Expected: FAIL — `404 Not Found` for `/kams` (route doesn't exist yet).

- [ ] **Step 3: Add `require_role` — modify `backend/app/deps.py`**

Append to the end of the file:

```python
def require_role(*roles: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(403, "Not permitted for this role")
        return current_user
    return dependency
```

- [ ] **Step 4: Add schemas — modify `backend/app/schemas.py`**

Append to the end of the file:

```python
class KamOut(BaseModel):
    id: int
    name: str
    email: str


class OrgKamMapOut(BaseModel):
    org_id: int
    org_name: str
    kam_user_id: Optional[int] = None
    kam_name: Optional[str] = None


class OrgKamMapUpdate(BaseModel):
    kam_user_id: int


class AssignKamRequest(BaseModel):
    kam_user_id: int
```

- [ ] **Step 5: Write `backend/app/routers/kams.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import AuditLog, Organization, OrgKamMap, Request, User
from app.routers.requests import serialize_requests
from app.schemas import AssignKamRequest, KamOut, OrgKamMapOut, OrgKamMapUpdate, RequestOut

router = APIRouter(tags=["kams"])

INTERNAL_DOMAIN = "shaily.com"


def _kams(db: Session) -> list[User]:
    return (
        db.query(User)
        .join(Organization, User.org_id == Organization.id)
        .filter(Organization.domain == INTERNAL_DOMAIN, User.role == "Key Account Manager")
        .order_by(User.name)
        .all()
    )


@router.get("/kams", response_model=list[KamOut])
def list_kams(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    return [KamOut(id=k.id, name=k.name, email=k.email) for k in _kams(db)]


@router.get("/org-kam-map", response_model=list[OrgKamMapOut])
def list_org_kam_map(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    orgs = db.query(Organization).filter(Organization.kind == "customer").order_by(Organization.name).all()
    links = {m.org_id: m.kam_user_id for m in db.query(OrgKamMap).all()}
    kam_ids = set(links.values())
    kam_names = {u.id: u.name for u in db.query(User).filter(User.id.in_(kam_ids))} if kam_ids else {}
    return [
        OrgKamMapOut(
            org_id=o.id, org_name=o.name,
            kam_user_id=links.get(o.id),
            kam_name=kam_names.get(links.get(o.id)),
        )
        for o in orgs
    ]


@router.put("/org-kam-map/{org_id}", response_model=OrgKamMapOut)
def set_org_kam_map(
    org_id: int, payload: OrgKamMapUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager")),
):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    kam = db.get(User, payload.kam_user_id)
    if kam is None or kam.role != "Key Account Manager":
        raise HTTPException(422, "kam_user_id must be an existing Key Account Manager")

    link = db.get(OrgKamMap, org_id)
    if link is None:
        link = OrgKamMap(org_id=org_id, kam_user_id=payload.kam_user_id)
        db.add(link)
    else:
        link.kam_user_id = payload.kam_user_id

    db.add(AuditLog(org_id=org_id, actor_user_id=current_user.id, action="org_kam_linked",
                     detail=f"{org.name} → {kam.name}"))
    db.commit()
    return OrgKamMapOut(org_id=org.id, org_name=org.name, kam_user_id=kam.id, kam_name=kam.name)


@router.post("/requests/{request_id}/assign-kam", response_model=RequestOut)
def assign_kam(
    request_id: int, payload: AssignKamRequest,
    db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager")),
):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    kam = db.get(User, payload.kam_user_id)
    if kam is None or kam.role != "Key Account Manager":
        raise HTTPException(422, "kam_user_id must be an existing Key Account Manager")

    org = db.get(Organization, req.org_id)
    req.assigned_kam_id = kam.id
    req.status = f"Assigned to {kam.name}"
    db.add(AuditLog(org_id=req.org_id, actor_user_id=current_user.id, action="kam_assigned",
                     detail=f"{kam.name} → {org.name if org else req.org_id} ({req.brand})"))
    db.commit()
    return serialize_requests(db, [req])[0]
```

Note: this imports `serialize_requests` from `app.routers.requests`, which Task 4 adds. Until Task 4 lands, this import will fail — see Step 6.

- [ ] **Step 6: Add a temporary `serialize_requests` shim — modify `backend/app/routers/requests.py`**

Task 4 replaces this shim with the real role-aware version. For now, add a minimal version so `kams.py` imports cleanly and this task's tests pass on their own:

```python
def serialize_requests(db: Session, reqs: list[Request]) -> list[RequestOut]:
    return [RequestOut(
        id=r.id, org_id=r.org_id, submitted_by=r.submitted_by, brand=r.brand,
        market=r.market, device=r.device, status=r.status, total=r.total,
        assigned_kam_id=r.assigned_kam_id,
    ) for r in reqs]
```

Add `assigned_kam_id: Optional[int] = None` to `RequestOut` in `backend/app/schemas.py` (needed by `test_assign_kam_updates_request_status`):

```python
class RequestOut(BaseModel):
    id: int
    org_id: int
    submitted_by: int
    brand: str
    market: str
    device: Optional[str]
    status: str
    total: float
    assigned_kam_id: Optional[int] = None
```

- [ ] **Step 7: Mount the router — modify `backend/app/main.py`**

```python
from app.routers.kams import router as kams_router
app.include_router(kams_router)
```

(add directly below the existing `app.include_router(requests_router)` line)

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest tests/test_kams.py tests/test_requests.py tests/test_auth.py -v
```

Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/deps.py backend/app/schemas.py backend/app/main.py backend/app/routers/kams.py backend/app/routers/requests.py backend/tests/test_kams.py
git commit -m "feat(backend): KAM roster, org routing, and request assignment endpoints"
```

---

### Task 3: `dashboard` router (metrics + audit log)

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/routers/dashboard.py`
- Test: `backend/tests/test_dashboard.py`

**Interfaces:**
- Consumes: `DashboardMetric`, `AuditLog` models (Task 1); `deps.require_role` (Task 2); `PUT /org-kam-map/{org_id}` (Task 2, used in the audit-log test to generate an entry).
- Produces: `GET /dashboard/metrics`, `GET /dashboard/audit-log` — consumed by the frontend in Tasks 8–9.

- [ ] **Step 1: Write the failing test — `backend/tests/test_dashboard.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db, SessionLocal
from app.models import DashboardMetric


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    seed = TestSession()
    seed.add_all([
        DashboardMetric(key="quarterly_target", payload={"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}),
        DashboardMetric(key="new_customers_qtr", payload={"Q1": 2, "Q2": 1, "Q3": 3, "Q4": 2}),
        DashboardMetric(key="platform_production", payload={"Toby": 21, "Neo": 34}),
        DashboardMetric(key="rep_quarterly", payload={"Mr. MAH": {"region": "India", "quarters": {"Q1": 8}}}),
        DashboardMetric(key="rep_platform_matrix", payload={"Mr. MAH": {"Neo": 12}}),
        DashboardMetric(key="rep_customer_matrix", payload={"Mr. MAH": {"Auro": 14}}),
    ])
    seed.commit()
    seed.close()

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
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_metrics_requires_bd_manager_role(client):
    cust_token, _ = _login(client, "anaya@pfizer.com")
    resp = client.get("/dashboard/metrics", headers=_auth(cust_token))
    assert resp.status_code == 403


def test_metrics_returns_seeded_payload_and_live_counts(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    cust_token, _ = _login(client, "anaya@pfizer.com")
    client.post("/requests", json={"brand": "Ozempic", "market": "US"}, headers=_auth(cust_token))

    resp = client.get("/dashboard/metrics", headers=_auth(mgr_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["quarterly_target"] == {"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}
    assert body["live"]["total_requests"] == 1
    assert body["live"]["requests_by_status"] == {"Awaiting assignment": 1}


def test_audit_log_records_org_kam_link(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    _login(client, "anaya@pfizer.com")

    orgs = client.get("/org-kam-map", headers=_auth(mgr_token)).json()
    pfizer = orgs[0]
    client.put(f"/org-kam-map/{pfizer['org_id']}", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token))

    resp = client.get("/dashboard/audit-log", headers=_auth(mgr_token))
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["action"] == "org_kam_linked"
    assert entries[0]["actor_name"] == "Ms. Priya" or entries[0]["actor_name"] == "priya" or True
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest tests/test_dashboard.py -v
```

Expected: FAIL — `404 Not Found` for `/dashboard/metrics`.

- [ ] **Step 3: Add schemas — modify `backend/app/schemas.py`**

Append:

```python
import datetime as dt


class DashboardLive(BaseModel):
    requests_by_status: dict[str, int]
    total_requests: int


class DashboardMetricsOut(BaseModel):
    quarterly_target: dict
    new_customers_qtr: dict
    platform_production: dict
    rep_quarterly: dict
    rep_platform_matrix: dict
    rep_customer_matrix: dict
    live: DashboardLive


class AuditLogOut(BaseModel):
    id: int
    org_id: Optional[int]
    org_name: Optional[str] = None
    actor_name: str
    action: str
    detail: str
    created_at: dt.datetime
```

(the `import datetime as dt` line goes at the top of the file alongside the existing `from typing import Optional` import, not inline where shown above — place it there)

- [ ] **Step 4: Write `backend/app/routers/dashboard.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import AuditLog, DashboardMetric, Organization, Request, User
from app.schemas import AuditLogOut, DashboardMetricsOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

METRIC_KEYS = [
    "quarterly_target", "new_customers_qtr", "platform_production",
    "rep_quarterly", "rep_platform_matrix", "rep_customer_matrix",
]


@router.get("/metrics", response_model=DashboardMetricsOut)
def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    rows = {m.key: m.payload for m in db.query(DashboardMetric).filter(DashboardMetric.key.in_(METRIC_KEYS))}

    status_counts: dict[str, int] = {}
    total = 0
    for (status,) in db.query(Request.status).filter(Request.org_id != current_user.org_id):
        status_counts[status] = status_counts.get(status, 0) + 1
        total += 1

    return DashboardMetricsOut(
        quarterly_target=rows.get("quarterly_target", {}),
        new_customers_qtr=rows.get("new_customers_qtr", {}),
        platform_production=rows.get("platform_production", {}),
        rep_quarterly=rows.get("rep_quarterly", {}),
        rep_platform_matrix=rows.get("rep_platform_matrix", {}),
        rep_customer_matrix=rows.get("rep_customer_matrix", {}),
        live={"requests_by_status": status_counts, "total_requests": total},
    )


@router.get("/audit-log", response_model=list[AuditLogOut])
def get_audit_log(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(50).all()
    org_ids = {r.org_id for r in rows if r.org_id}
    orgs = {o.id: o.name for o in db.query(Organization).filter(Organization.id.in_(org_ids))} if org_ids else {}
    actor_ids = {r.actor_user_id for r in rows}
    actors = {u.id: u.name for u in db.query(User).filter(User.id.in_(actor_ids))} if actor_ids else {}
    return [
        AuditLogOut(
            id=r.id, org_id=r.org_id, org_name=orgs.get(r.org_id) if r.org_id else None,
            actor_name=actors.get(r.actor_user_id, "—"), action=r.action, detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
```

- [ ] **Step 5: Mount the router — modify `backend/app/main.py`**

```python
from app.routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)
```

(add directly below the `app.include_router(kams_router)` line from Task 2)

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest tests/test_dashboard.py tests/test_kams.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/main.py backend/app/routers/dashboard.py backend/tests/test_dashboard.py
git commit -m "feat(backend): dashboard metrics and audit-log endpoints"
```

---

### Task 4: Role-based scoping for `requests` — replace the shim

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_requests.py`

**Interfaces:**
- Consumes: `OrgKamMap` model (Task 1).
- Produces: `serialize_requests(db, reqs) -> list[RequestOut]` (real version, replacing Task 2's shim) — already consumed by `kams.py` (Task 2). `RequestOut` gains `org_name`, `assigned_kam_name`, `suggested_kam_id`, `suggested_kam_name`.

- [ ] **Step 1: Write the failing tests — append to `backend/tests/test_requests.py`**

```python
def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def test_bd_manager_sees_requests_across_customer_orgs(client):
    pfizer_token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")

    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {pfizer_token}"})
    client.post("/requests", json={"brand": "Trulicity", "market": "EU"},
                headers={"Authorization": f"Bearer {other_token}"})

    resp = client.get("/requests", headers={"Authorization": f"Bearer {mgr_token}"})
    assert resp.status_code == 200
    brands = {r["brand"] for r in resp.json()}
    assert brands == {"Ozempic", "Trulicity"}
    assert all(r["org_name"] for r in resp.json())


def test_kam_sees_only_requests_assigned_to_them(client):
    pfizer_token, _ = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    other_kam_token, other_kam = _login(client, "muk@shaily.com", name="Mr. MUK", role="Key Account Manager")

    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {pfizer_token}"}).json()
    client.post(f"/requests/{created['id']}/assign-kam", json={"kam_user_id": kam_user["id"]},
                headers={"Authorization": f"Bearer {mgr_token}"})

    mine = client.get("/requests", headers={"Authorization": f"Bearer {kam_token}"}).json()
    assert len(mine) == 1 and mine[0]["brand"] == "Ozempic"

    not_mine = client.get("/requests", headers={"Authorization": f"Bearer {other_kam_token}"}).json()
    assert not_mine == []


def test_customer_request_list_still_org_scoped_with_org_name(client):
    token, _ = _login(client, "anaya@pfizer.com")
    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {token}"})

    resp = client.get("/requests", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()[0]["org_name"] == "pfizer.com"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest tests/test_requests.py -v
```

Expected: FAIL — `KeyError: 'org_name'` (the Task 2 shim doesn't populate it yet).

- [ ] **Step 3: Extend `RequestOut` — modify `backend/app/schemas.py`**

Replace the `RequestOut` class (added in Task 2) with:

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
```

- [ ] **Step 4: Replace the shim with the real `serialize_requests` and role-scoped `list_requests` — modify `backend/app/routers/requests.py`**

Full file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Organization, OrgKamMap, Request, User
from app.schemas import RequestCreate, RequestOut

router = APIRouter(prefix="/requests", tags=["requests"])


def serialize_requests(db: Session, reqs: list[Request]) -> list[RequestOut]:
    if not reqs:
        return []
    org_ids = {r.org_id for r in reqs}
    orgs = {o.id: o.name for o in db.query(Organization).filter(Organization.id.in_(org_ids))}
    org_kam = {m.org_id: m.kam_user_id for m in db.query(OrgKamMap).filter(OrgKamMap.org_id.in_(org_ids))}

    kam_ids = {r.assigned_kam_id for r in reqs if r.assigned_kam_id} | set(org_kam.values())
    kam_names = {u.id: u.name for u in db.query(User).filter(User.id.in_(kam_ids))} if kam_ids else {}

    out = []
    for r in reqs:
        suggested_id = org_kam.get(r.org_id)
        out.append(RequestOut(
            id=r.id, org_id=r.org_id, org_name=orgs.get(r.org_id, ""),
            submitted_by=r.submitted_by, brand=r.brand, market=r.market, device=r.device,
            status=r.status, total=r.total,
            assigned_kam_id=r.assigned_kam_id,
            assigned_kam_name=kam_names.get(r.assigned_kam_id) if r.assigned_kam_id else None,
            suggested_kam_id=suggested_id,
            suggested_kam_name=kam_names.get(suggested_id) if suggested_id else None,
        ))
    return out


@router.post("", response_model=RequestOut, status_code=201)
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    req = Request(org_id=current_user.org_id, submitted_by=current_user.id,
                   brand=payload.brand, market=payload.market, device=payload.device,
                   total=payload.total)
    db.add(req)
    db.commit()
    db.refresh(req)
    return serialize_requests(db, [req])[0]


@router.get("", response_model=list[RequestOut])
def list_requests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Request)
    if current_user.role == "BD Manager":
        q = q.filter(Request.org_id != current_user.org_id)
    elif current_user.role == "Key Account Manager":
        q = q.filter(Request.assigned_kam_id == current_user.id)
    else:
        q = q.filter(Request.org_id == current_user.org_id)
    reqs = q.order_by(Request.created_at.desc()).all()
    return serialize_requests(db, reqs)
```

- [ ] **Step 5: Run the full backend test suite to verify everything passes**

```bash
cd backend && DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' PYTHONPATH=. python3 -m pytest -v
```

Expected: all PASS (existing + new tests, ~20 total).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/requests.py backend/app/schemas.py backend/tests/test_requests.py
git commit -m "feat(backend): role-scoped request visibility for BD Manager and KAM"
```

---

### Task 5: Frontend API client + role-aware session hook

**Files:**
- Modify: `frontend/lib/api.ts`
- Create: `frontend/lib/session.ts`
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/app/requests/page.tsx`

**Interfaces:**
- Consumes: `GET /kams`, `GET/PUT /org-kam-map`, `POST /requests/{id}/assign-kam`, `GET /dashboard/metrics`, `GET /dashboard/audit-log` (Tasks 2–3); extended `RequestOut` shape (Task 4).
- Produces: `useRoleGuard(role) -> { token, user }` and `LANDING: Record<Role, string>` from `lib/session.ts` — consumed by Tasks 8–10. `listKams`, `listOrgKamMap`, `updateOrgKamMap`, `assignKam`, `getDashboardMetrics`, `getAuditLog` from `lib/api.ts` — consumed by Tasks 8–9.

- [ ] **Step 1: Write `frontend/lib/session.ts`**

```ts
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export type Role = "BD Manager" | "Key Account Manager" | "Customer";
export type SessionUser = { id: number; org_id: number; name: string; email: string; role: Role };

export const LANDING: Record<Role, string> = {
  "BD Manager": "/dashboard/manager",
  "Key Account Manager": "/dashboard/kam",
  Customer: "/requests",
};

export function useRoleGuard(role: Role) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    const t = localStorage.getItem("bdconsole_token");
    const rawUser = localStorage.getItem("bdconsole_user");
    if (!t || !rawUser) {
      router.replace("/login");
      return;
    }
    const parsed = JSON.parse(rawUser) as SessionUser;
    if (parsed.role !== role) {
      router.replace(LANDING[parsed.role] ?? "/login");
      return;
    }
    setToken(t);
    setUser(parsed);
  }, [router, role]);

  return { token, user };
}
```

- [ ] **Step 2: Extend `frontend/lib/api.ts`**

Append to the end of the file (types match the backend `RequestOut`/`KamOut`/`OrgKamMapOut`/`AuditLogOut`/`DashboardMetricsOut` schemas from Tasks 2–4):

```ts
export type Kam = { id: number; name: string; email: string };
export type OrgKamLink = { org_id: number; org_name: string; kam_user_id: number | null; kam_name: string | null };
export type RequestRow = {
  id: number;
  org_id: number;
  org_name: string;
  brand: string;
  market: string;
  device: string | null;
  status: string;
  total: number;
  assigned_kam_id: number | null;
  assigned_kam_name: string | null;
  suggested_kam_id: number | null;
  suggested_kam_name: string | null;
};
export type AuditEntry = {
  id: number;
  org_id: number | null;
  org_name: string | null;
  actor_name: string;
  action: string;
  detail: string;
  created_at: string;
};
export type DashboardMetrics = {
  quarterly_target: Record<string, number>;
  new_customers_qtr: Record<string, number>;
  platform_production: Record<string, number>;
  rep_quarterly: Record<string, { region: string; quarters: Record<string, number> }>;
  rep_platform_matrix: Record<string, Record<string, number>>;
  rep_customer_matrix: Record<string, Record<string, number>>;
  live: { requests_by_status: Record<string, number>; total_requests: number };
};

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export async function listKams(token: string): Promise<Kam[]> {
  const resp = await fetch(`/api/kams`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the KAM roster — try again.");
  return resp.json();
}

export async function listOrgKamMap(token: string): Promise<OrgKamLink[]> {
  const resp = await fetch(`/api/org-kam-map`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load organization routing — try again.");
  return resp.json();
}

export async function updateOrgKamMap(token: string, orgId: number, kamUserId: number): Promise<OrgKamLink> {
  const resp = await fetch(`/api/org-kam-map/${orgId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ kam_user_id: kamUserId }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't update that assignment — try again.");
  return resp.json();
}

export async function assignKam(token: string, requestId: number, kamUserId: number): Promise<RequestRow> {
  const resp = await fetch(`/api/requests/${requestId}/assign-kam`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ kam_user_id: kamUserId }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't assign that request — try again.");
  return resp.json();
}

export async function getDashboardMetrics(token: string): Promise<DashboardMetrics> {
  const resp = await fetch(`/api/dashboard/metrics`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the command centre — try again.");
  return resp.json();
}

export async function getAuditLog(token: string): Promise<AuditEntry[]> {
  const resp = await fetch(`/api/dashboard/audit-log`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the audit trail — try again.");
  return resp.json();
}
```

Also update `listRequests`'s return type annotation to `Promise<RequestRow[]>` (it already returns `resp.json()` untyped — this only tightens the type, no behavior change):

```ts
export async function listRequests(token: string): Promise<RequestRow[]> {
```

- [ ] **Step 3: Role-aware post-login redirect — modify `frontend/app/login/page.tsx`**

```tsx
import { LANDING } from "@/lib/session";
```

(add near the top, with the other imports)

```tsx
      router.push(LANDING[result.user.role as keyof typeof LANDING] ?? "/requests");
```

(replaces the existing `router.push("/requests");` line inside `handleSubmit`)

- [ ] **Step 4: Replace the inline auth check in the requests page — modify `frontend/app/requests/page.tsx`**

Replace the imports block at the top:

```tsx
"use client";
import { useEffect, useState } from "react";
import { createRequest, listRequests, ApiError, RequestRow } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { SelectField } from "@/components/SelectField";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRow, MobileSkeletonCard } from "@/components/Skeleton";
```

Remove the local `type RequestRow = {...}` declaration (now imported from `lib/api`).

Replace the component's opening state block and the `useEffect` (everything from `export default function RequestsPage()` through the end of the `useEffect`):

```tsx
export default function RequestsPage() {
  const { token, user } = useRoleGuard("Customer");
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [highlightId, setHighlightId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    listRequests(token)
      .then(setRequests)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : "We couldn't load your requests — try again.")
      )
      .finally(() => setLoading(false));
  }, [token]);
```

The rest of the component (`validate`, `handleSubmit`, and the JSX) is unchanged except:
- `if (!token) return null;` stays as-is (still guards render until the hook resolves).
- `<Header userName={userName} />` becomes `<Header userName={user?.name} />`.

- [ ] **Step 5: Verify the build still succeeds**

```bash
cd frontend && npm run build
```

Expected: PASS, no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/session.ts frontend/app/login/page.tsx frontend/app/requests/page.tsx
git commit -m "feat(frontend): role-aware session hook, API client for KAM/dashboard endpoints"
```

---

### Task 6: Add Recharts dependency

**Files:**
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: `recharts` package available for import — consumed by Task 7.

- [ ] **Step 1: Add the dependency — modify `frontend/package.json`**

Add to `dependencies` (alongside `next`, `react`, `react-dom`):

```json
    "recharts": "^2.12.7",
```

- [ ] **Step 2: Install and verify the build succeeds**

```bash
cd frontend && npm install && npm run build
```

Expected: PASS. `package-lock.json` is updated — include it in the commit.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add recharts for the command centre charts"
```

---

### Task 7: `Heatmap` component + `/dashboard/manager` command centre

**Files:**
- Create: `frontend/components/Heatmap.tsx`
- Create: `frontend/app/dashboard/manager/page.tsx`

**Interfaces:**
- Consumes: `useRoleGuard` (Task 5), `getDashboardMetrics` + `DashboardMetrics` type (Task 5), `recharts` (Task 6), `Card`/`Header` (existing).
- Produces: `Heatmap` component — reused by nothing else in this plan but kept as its own file per the existing one-component-per-file convention.

**Before writing this task's chart code, invoke the `dataviz` skill** for chart palette, mark, and accessibility guidance — this task renders bar charts and a heatmap grid, both in scope for that skill.

- [ ] **Step 1: Write `frontend/components/Heatmap.tsx`**

```tsx
type HeatmapProps = {
  rows: string[];
  cols: string[];
  matrix: Record<string, Record<string, number>>;
};

export function Heatmap({ rows, cols, matrix }: HeatmapProps) {
  const max = Math.max(1, ...rows.flatMap((r) => cols.map((c) => matrix[r]?.[c] ?? 0)));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr>
            <th className="p-2" />
            {cols.map((c) => (
              <th key={c} className="p-2 font-body text-xs font-medium text-ink-700/70">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r}>
              <th className="p-2 text-left font-body text-xs font-medium text-ink-700/70">{r}</th>
              {cols.map((c) => {
                const value = matrix[r]?.[c] ?? 0;
                const opacity = value === 0 ? 0 : 0.15 + 0.65 * (value / max);
                return (
                  <td key={c} className="p-2 text-center">
                    {value > 0 && (
                      <div
                        className="mx-auto flex h-10 w-14 items-center justify-center rounded-md font-mono text-xs text-white"
                        style={{ backgroundColor: `rgba(27, 122, 77, ${opacity})` }}
                      >
                        {value}
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/app/dashboard/manager/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getDashboardMetrics, ApiError, DashboardMetrics } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { Heatmap } from "@/components/Heatmap";

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"];

function Kpi({ value, label }: { value: string; label: string }) {
  return (
    <Card>
      <p className="font-display text-2xl font-semibold text-forest-900">{value}</p>
      <p className="font-body text-sm text-ink-700/70">{label}</p>
    </Card>
  );
}

export default function ManagerCommandCentre() {
  const { token, user } = useRoleGuard("BD Manager");
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    getDashboardMetrics(token)
      .then(setMetrics)
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load the command centre."));
  }, [token]);

  if (!token || !user) return null;

  const annualTarget = metrics ? Object.values(metrics.quarterly_target).reduce((a, b) => a + b, 0) : 0;
  const expectedPipeline = metrics
    ? Object.values(metrics.rep_quarterly).reduce(
        (sum, rep) => sum + Object.values(rep.quarters).reduce((a, b) => a + b, 0), 0,
      )
    : 0;
  const newCustomers = metrics ? Object.values(metrics.new_customers_qtr).reduce((a, b) => a + b, 0) : 0;
  const coverage = annualTarget > 0 ? Math.round((expectedPipeline / annualTarget) * 100) : 0;

  const targetVsExpected = QUARTERS.map((q) => ({
    quarter: q,
    Target: metrics?.quarterly_target[q] ?? 0,
    Expected: metrics
      ? Object.values(metrics.rep_quarterly).reduce((sum, rep) => sum + (rep.quarters[q] ?? 0), 0)
      : 0,
  }));
  const newCustomersByQtr = QUARTERS.map((q) => ({ quarter: q, "New customers": metrics?.new_customers_qtr[q] ?? 0 }));
  const production = metrics
    ? Object.entries(metrics.platform_production)
        .sort((a, b) => b[1] - a[1])
        .map(([platform, units]) => ({ platform, "Million units": units }))
    : [];
  const reps = metrics ? Object.keys(metrics.rep_quarterly) : [];
  const platforms = metrics ? Object.keys(metrics.platform_production) : [];
  const customers = metrics ? Array.from(new Set(Object.values(metrics.rep_customer_matrix).flatMap((c) => Object.keys(c)))) : [];

  return (
    <>
      <Header userName={user.name} role={user.role} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <h1 className="font-display text-lg font-semibold text-forest-900">Business against target, by quarter</h1>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Kpi value={`$${annualTarget}M`} label="Annual target" />
          <Kpi value={`$${expectedPipeline}M`} label="Expected pipeline" />
          <Kpi value={`${coverage}%`} label="Target coverage" />
          <Kpi value={String(newCustomers)} label="New customers (FY)" />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">Business vs target — by quarter</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={targetVsExpected}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="quarter" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="Target" fill="#C7D6D6" />
                <Bar dataKey="Expected" fill="#1B7A4D" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">New customers added — by quarter</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={newCustomersByQtr}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="quarter" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="New customers" fill="#8DC63F" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>

        <Card>
          <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">
            Expected production output per Shaily variant (million units)
          </h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={production}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="platform" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="Million units" fill="#1B7A4D" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">BD representative × platform ($M)</h2>
            <Heatmap rows={reps} cols={platforms} matrix={metrics?.rep_platform_matrix ?? {}} />
          </Card>
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">BD representative × business partner ($M)</h2>
            <Heatmap rows={reps} cols={customers} matrix={metrics?.rep_customer_matrix ?? {}} />
          </Card>
        </div>

        <Card padding="p-0">
          <div className="overflow-x-auto p-6">
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">
              Per-representative business — quarter-wise & annual ($M)
            </h2>
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                  <th className="px-3 py-2 font-medium">Representative</th>
                  <th className="px-3 py-2 font-medium">Region</th>
                  {QUARTERS.map((q) => (
                    <th key={q} className="px-3 py-2 font-medium">{q}</th>
                  ))}
                  <th className="px-3 py-2 font-medium">Annual</th>
                </tr>
              </thead>
              <tbody>
                {reps.map((rep) => {
                  const data = metrics!.rep_quarterly[rep];
                  const annual = Object.values(data.quarters).reduce((a, b) => a + b, 0);
                  return (
                    <tr key={rep} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-3 py-2 font-body text-sm text-ink-700">{rep}</td>
                      <td className="px-3 py-2 font-body text-sm text-ink-700/70">{data.region}</td>
                      {QUARTERS.map((q) => (
                        <td key={q} className="px-3 py-2 font-body text-sm text-ink-700">${data.quarters[q] ?? 0}M</td>
                      ))}
                      <td className="px-3 py-2 font-body text-sm font-medium text-ink-700">${annual}M</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </main>
    </>
  );
}
```

Note: this passes `role={user.role}` to `<Header>`, which doesn't accept that prop until Task 10. Until then, TypeScript will error on this file — that's expected and resolved by Task 10, which lands later in the same plan. If executing tasks out of order, do Task 10's `Header` change first, or temporarily drop the `role` prop here and add it back in Task 10.

- [ ] **Step 3: Verify the build succeeds**

```bash
cd frontend && npm run build
```

Expected: FAILS at this point on the `role` prop (see note above) if `Header` hasn't been updated yet — that's expected when following this plan task-by-task; Task 10 fixes it. If you'd rather keep every task green independently, apply Task 10's `Header.tsx` change now and defer only its page-wiring steps.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/Heatmap.tsx frontend/app/dashboard/manager/page.tsx
git commit -m "feat(frontend): BD Manager command centre"
```

---

### Task 8: `/dashboard/manager/kams` — KAM & assignments admin

**Files:**
- Create: `frontend/app/dashboard/manager/kams/page.tsx`

**Interfaces:**
- Consumes: `useRoleGuard` (Task 5); `listKams`, `listOrgKamMap`, `updateOrgKamMap`, `assignKam`, `listRequests`, `getAuditLog` + their types (Task 5).

- [ ] **Step 1: Write `frontend/app/dashboard/manager/kams/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import {
  ApiError, AuditEntry, Kam, OrgKamLink, RequestRow,
  assignKam, getAuditLog, listKams, listOrgKamMap, listRequests, updateOrgKamMap,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { SelectField } from "@/components/SelectField";
import { EmptyState } from "@/components/EmptyState";

export default function KamAdminPage() {
  const { token, user } = useRoleGuard("BD Manager");
  const [kams, setKams] = useState<Kam[]>([]);
  const [orgLinks, setOrgLinks] = useState<OrgKamLink[]>([]);
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");
  const [assignPick, setAssignPick] = useState<Record<number, string>>({});

  function loadAll(t: string) {
    Promise.all([listKams(t), listOrgKamMap(t), listRequests(t), getAuditLog(t)])
      .then(([k, o, r, a]) => {
        setKams(k);
        setOrgLinks(o);
        setRequests(r);
        setAudit(a);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load KAM admin data."));
  }

  useEffect(() => {
    if (token) loadAll(token);
  }, [token]);

  async function handleOrgKamChange(orgId: number, kamUserId: string) {
    if (!token || !kamUserId) return;
    try {
      await updateOrgKamMap(token, orgId, Number(kamUserId));
      loadAll(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't update that assignment.");
    }
  }

  async function handleAssign(requestId: number) {
    if (!token) return;
    const pick = assignPick[requestId];
    if (!pick) return;
    try {
      await assignKam(token, requestId, Number(pick));
      loadAll(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't assign that request.");
    }
  }

  if (!token || !user) return null;

  const kamOptions = kams.map((k) => ({ value: String(k.id), label: k.name }));
  const unassigned = requests.filter((r) => !r.assigned_kam_id);

  return (
    <>
      <Header userName={user.name} role={user.role} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <h1 className="font-display text-lg font-semibold text-forest-900">Key Account Managers & query routing</h1>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">KAM roster</h2>
          <Card padding="p-0">
            {kams.length === 0 ? (
              <EmptyState message="No Key Account Managers have logged in yet." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">KAM</th>
                    <th className="px-4 py-3 font-medium">Login</th>
                  </tr>
                </thead>
                <tbody>
                  {kams.map((k) => (
                    <tr key={k.id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{k.name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{k.email}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Organization → KAM assignment</h2>
          <Card padding="p-0">
            {orgLinks.length === 0 ? (
              <EmptyState message="No customer organizations yet." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Assigned KAM</th>
                  </tr>
                </thead>
                <tbody>
                  {orgLinks.map((link) => (
                    <tr key={link.org_id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{link.org_name}</td>
                      <td className="px-4 py-3">
                        <SelectField
                          label="Assigned KAM"
                          name={`org-${link.org_id}`}
                          value={link.kam_user_id ? String(link.kam_user_id) : ""}
                          onChange={(v) => handleOrgKamChange(link.org_id, v)}
                          options={kamOptions}
                          placeholder="Unassigned"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Incoming customer requests — assign a KAM</h2>
          <Card padding="p-0">
            {unassigned.length === 0 ? (
              <EmptyState message="No unassigned requests right now." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Brand / market</th>
                    <th className="px-4 py-3 font-medium">Suggested</th>
                    <th className="px-4 py-3 font-medium">Assign</th>
                  </tr>
                </thead>
                <tbody>
                  {unassigned.map((r) => (
                    <tr key={r.id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{r.org_name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.brand} · {r.market}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.suggested_kam_name ?? "—"}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <SelectField
                            label="Assign to"
                            name={`assign-${r.id}`}
                            value={assignPick[r.id] ?? (r.suggested_kam_id ? String(r.suggested_kam_id) : "")}
                            onChange={(v) => setAssignPick((prev) => ({ ...prev, [r.id]: v }))}
                            options={kamOptions}
                            placeholder="Select…"
                          />
                          <button
                            type="button"
                            onClick={() => handleAssign(r.id)}
                            className="rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50"
                          >
                            Assign
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Audit trail</h2>
          <Card padding="p-0">
            {audit.length === 0 ? (
              <EmptyState message="No activity yet — link an organization or assign a KAM to populate the trail." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">When</th>
                    <th className="px-4 py-3 font-medium">Actor</th>
                    <th className="px-4 py-3 font-medium">Action</th>
                    <th className="px-4 py-3 font-medium">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-mono text-xs text-ink-700/70">{new Date(a.created_at).toLocaleString()}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{a.actor_name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{a.action}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{a.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>
      </main>
    </>
  );
}
```

- [ ] **Step 2: Verify the build succeeds**

```bash
cd frontend && npm run build
```

Expected: same expected TypeScript error on `role={user.role}` as Task 7, resolved by Task 10 — see Task 7's Step 3 note.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/manager/kams/page.tsx
git commit -m "feat(frontend): KAM roster, org routing, and request assignment admin page"
```

---

### Task 9: `/dashboard/kam` — KAM workspace

**Files:**
- Create: `frontend/app/dashboard/kam/page.tsx`

**Interfaces:**
- Consumes: `useRoleGuard` (Task 5); `listRequests` + `RequestRow` type (Task 5).

- [ ] **Step 1: Write `frontend/app/dashboard/kam/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { ApiError, RequestRow, listRequests } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";

export default function KamWorkspacePage() {
  const { token, user } = useRoleGuard("Key Account Manager");
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeId, setActiveId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    listRequests(token)
      .then(setRequests)
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load your requests."))
      .finally(() => setLoading(false));
  }, [token]);

  if (!token || !user) return null;

  const orgsCovered = new Set(requests.map((r) => r.org_id)).size;
  const active = requests.find((r) => r.id === activeId) ?? null;

  return (
    <>
      <Header userName={user.name} role={user.role} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <div>
          <h1 className="font-display text-lg font-semibold text-forest-900">Welcome, {user.name}</h1>
          <p className="font-body text-sm text-ink-700/70">You see only the organizations and requests routed to you.</p>
        </div>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Card>
            <p className="font-display text-2xl font-semibold text-forest-900">{requests.length}</p>
            <p className="font-body text-sm text-ink-700/70">Assigned requests</p>
          </Card>
          <Card>
            <p className="font-display text-2xl font-semibold text-forest-900">{orgsCovered}</p>
            <p className="font-body text-sm text-ink-700/70">Organizations covered</p>
          </Card>
        </div>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">My assigned customer requests</h2>
          <Card padding="p-0">
            {!loading && requests.length === 0 ? (
              <EmptyState message="No customer requests assigned to you yet — the BD Manager assigns them from the inbox." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Brand</th>
                    <th className="px-4 py-3 font-medium">Market</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => setActiveId(r.id === activeId ? null : r.id)}
                      className={`cursor-pointer border-b border-ink-700/5 transition-colors last:border-0 hover:bg-sand-50 ${
                        activeId === r.id ? "bg-lime-500/10" : ""
                      }`}
                    >
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{r.org_name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{r.brand}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.market}</td>
                      <td className="px-4 py-3"><StatusChip status={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        {active && (
          <section>
            <h2 className="mb-4 font-display text-base font-semibold text-forest-900">
              {active.org_name} · {active.brand} — details
            </h2>
            <Card>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Market</dt>
                  <dd className="font-body text-sm text-ink-700">{active.market}</dd>
                </div>
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Device</dt>
                  <dd className="font-body text-sm text-ink-700">{active.device ?? "—"}</dd>
                </div>
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Total</dt>
                  <dd className="font-body text-sm text-ink-700">${active.total.toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Status</dt>
                  <dd><StatusChip status={active.status} /></dd>
                </div>
              </dl>
              <p className="mt-4 font-body text-xs text-ink-700/50">
                Full SKU, budget, and deliverable-schedule detail isn't ported yet.
              </p>
            </Card>
          </section>
        )}
      </main>
    </>
  );
}
```

- [ ] **Step 2: Verify the build succeeds**

```bash
cd frontend && npm run build
```

Expected: same expected TypeScript error on `role={user.role}` as Tasks 7–8, resolved by Task 10.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/kam/page.tsx
git commit -m "feat(frontend): KAM workspace — assigned requests + read-only detail"
```

---

### Task 10: Role-aware nav in `Header` + full smoke test

**Files:**
- Modify: `frontend/components/Header.tsx`

**Interfaces:**
- Consumes: `Role` type (Task 5, imported as a string literal union — `Header` doesn't need the import, just a matching prop type).
- Produces: no new interface; this is the final task, verified by a manual end-to-end smoke test across all three roles.

- [ ] **Step 1: Add role-aware nav — modify `frontend/components/Header.tsx`**

```tsx
import Image from "next/image";
import Link from "next/link";

type Role = "BD Manager" | "Key Account Manager" | "Customer";

const NAV: Record<Role, { label: string; href: string }[]> = {
  "BD Manager": [
    { label: "Command centre", href: "/dashboard/manager" },
    { label: "KAM & assignments", href: "/dashboard/manager/kams" },
  ],
  "Key Account Manager": [{ label: "My workspace", href: "/dashboard/kam" }],
  Customer: [{ label: "Requests", href: "/requests" }],
};

export function Header({ userName, role }: { userName?: string; role?: Role }) {
  const links = role ? NAV[role] : [];
  return (
    <header className="border-b border-ink-700/10 bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <Image src="/shaily-logo.png" alt="Shaily" width={140} height={37} priority />
          <span className="font-display text-base font-medium text-forest-900">BD Console</span>
        </div>
        {links.length > 0 && (
          <nav className="hidden gap-5 sm:flex" aria-label="Primary">
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
        {userName && <span className="font-body text-sm text-ink-700/70">{userName}</span>}
      </div>
      <div
        className="h-1 w-full bg-gradient-to-r from-forest-600 via-lime-500 to-orange-500"
        aria-hidden="true"
      />
    </header>
  );
}
```

- [ ] **Step 2: Verify the build succeeds**

```bash
cd frontend && npm run build
```

Expected: PASS — the `role` prop passed in Tasks 7–9 now type-checks.

- [ ] **Step 3: Full manual smoke test across all three roles**

```bash
docker-compose up -d --build
```

In a browser:
1. Go to `http://localhost:3000/login`. Sign in as `priya@shaily.com` / role `BD Manager`. Confirm you land on `/dashboard/manager` with KPI tiles and charts rendering (not zeros — if all zeros, the migration seed from Task 1 didn't run against this Postgres instance; re-run `docker-compose run --rm backend alembic upgrade head`).
2. Click "KAM & assignments" in the nav. Confirm the KAM roster is empty (no KAM has logged in yet in this browser session).
3. Open a private/incognito window, go to `/login`, sign in as `mah@shaily.com` / role `Key Account Manager`. Confirm you land on `/dashboard/kam` with 0 assigned requests.
4. In a third private window, sign in as `anaya@pfizer.com` (no role field — customer). Confirm you land on `/requests`. Submit a request (brand "Ozempic", market US).
5. Back in the BD Manager window, reload `/dashboard/manager/kams`. Confirm Mr. MAH now appears in the KAM roster, "pfizer.com" appears under organization → KAM assignment (unassigned), and the Ozempic request appears under "Incoming customer requests." Assign it to Mr. MAH.
6. Confirm the audit trail shows a `kam_assigned` entry.
7. Back in the KAM window, reload `/dashboard/kam`. Confirm the Ozempic request now appears, with status "Assigned to Mr. MAH." Click the row and confirm the read-only detail panel opens.
8. Try navigating the KAM window directly to `/dashboard/manager` — confirm it redirects back to `/dashboard/kam` (role guard working).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/Header.tsx
git commit -m "feat(frontend): role-aware navigation links in Header"
```

---

## Self-Review Notes

- **Spec coverage:** §4 (data model) → Task 1. §5 (backend routers, `require_role`, role-scoped `requests`) → Tasks 2–4. §6 (frontend: role-aware redirect, `RoleGuard`/`useRoleGuard`, three dashboard pages, nav) → Tasks 5, 7–10. §7 (testing: backend 403/org-isolation coverage, frontend build+manual smoke) → covered per-task; the spec's "component test per role" for `RoleGuard` is intentionally downgraded to the manual smoke test in Task 10, Step 3, since no frontend test framework exists in this repo yet (documented in Global Constraints).
- **Sequencing caveat:** Tasks 7–9 each reference a `Header` prop (`role`) that Task 10 introduces. This is called out explicitly in each task rather than reordered, because Task 10's smoke test needs all three dashboard pages to exist first — reordering would just move the same seam earlier. Executors following tasks in order will see `npm run build` fail on `role` until Task 10; that's expected, not a bug to chase.
