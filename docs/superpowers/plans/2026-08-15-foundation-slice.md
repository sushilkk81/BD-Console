# Foundation Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up FastAPI + Postgres + Next.js as three deployed containers on AWS (ECS Fargate + RDS), with one real flow working end-to-end — mock login → submit a request → request lands in Postgres, scoped to the user's organization — proving the pipeline before any other feature is ported.

**Architecture:** Next.js (App Router, TypeScript) frontend calls a FastAPI backend over JSON/HTTPS. FastAPI uses SQLAlchemy 2.0 + Alembic against Postgres (RDS in prod, a local container in dev). Auth is a mock endpoint (email + optional role, domain-checked against `@shaily.com`) issuing a real JWT, so every later piece (API auth dependency, React auth state, protected routes) is built against the real token mechanism from day one. Infra is provisioned with Terraform: ECR repos, RDS instance, ECS Fargate cluster/services, one ALB routing `/api/*` to the backend and everything else to the frontend.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, psycopg2, PyJWT, pytest + httpx; Node 20, Next.js 14 (App Router), TypeScript; Docker, Docker Compose (local); Terraform (AWS provider) for ECR/RDS/ECS/ALB.

**Spec:** `docs/superpowers/specs/2026-08-15-org-level-rebuild-design.md` (sections 4–6, 8 §1)

## Global Constraints

- Tenant isolation: every request-scoped query filters by `org_id` (spec §5). Never write a query that returns rows across orgs for a customer-org user.
- Auth token issued by the mock login endpoint must be the same shape/claims the real magic-link login will issue later (spec §6) — don't special-case the mock in a way the real flow can't reuse.
- `@shaily.com` email domain → internal org, role chosen from `BD Manager` / `Key Account Manager`; any other domain → customer org named after the domain, role `Customer` (spec §6, matching today's `app.py` gate logic).
- No Streamlit — this plan starts the FastAPI/Next.js replacement (spec §4); do not add new Streamlit code.
- Backend and frontend are separate containers, separately deployable (spec §4).

---

## File Structure

```
backend/
  app/
    __init__.py
    main.py            # FastAPI app, CORS, router mounts, /health
    config.py           # env-driven settings (DATABASE_URL, JWT_SECRET, CORS origins)
    db.py                # SQLAlchemy engine/session, Base
    models.py           # Organization, User, Request ORM models
    schemas.py           # Pydantic request/response models
    security.py          # JWT encode/decode helpers
    deps.py               # get_db, get_current_user, require_org_scope
    routers/
      __init__.py
      auth.py             # POST /auth/login
      requests.py          # POST /requests, GET /requests
  alembic/
    env.py
    script.py.mako
    versions/
      0001_initial.py
  alembic.ini
  requirements.txt
  Dockerfile
  tests/
    conftest.py
    test_auth.py
    test_requests.py

frontend/
  package.json
  tsconfig.json
  next.config.js
  app/
    layout.tsx
    page.tsx              # redirects to /login or /requests based on token
    login/page.tsx
    requests/page.tsx
  lib/
    api.ts                 # fetch wrapper, token storage
  Dockerfile
  .env.example

infra/terraform/
  main.tf                  # provider, shared locals
  variables.tf
  outputs.tf
  ecr.tf
  rds.tf
  ecs.tf
  alb.tf

docker-compose.yml           # postgres + backend + frontend, local dev
.env.example                 # root-level compose env template
```

---

### Task 1: Backend scaffold + health check

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/conftest.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.main:app` (FastAPI instance), `app.config:Settings` (class with `.database_url: str`, `.jwt_secret: str`, `.cors_origins: list[str]`, loaded from env vars `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`), `app.config:get_settings()` (cached factory).

- [ ] **Step 1: Write requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
alembic==1.13.2
psycopg2-binary==2.9.9
pyjwt==2.9.0
pydantic-settings==2.5.2
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 2: Write `backend/app/config.py`**

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://bdconsole:bdconsole@localhost:5432/bdconsole"
    jwt_secret: str = "dev-only-secret-change-me"
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: Write `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="BD Console API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Write the failing test — `backend/tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)
```

```python
# backend/tests/test_health.py
def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it fails first (before app.py existed it would fail on import; now confirm it passes)**

Run (from `backend/`): `pip install -r requirements.txt && pytest tests/test_health.py -v`
Expected: PASS (app.main already written in Step 3 — this confirms the scaffold works end to end)

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/__init__.py backend/app/config.py backend/app/main.py backend/tests/conftest.py backend/tests/test_health.py
git commit -m "feat(backend): FastAPI scaffold with health check"
```

---

### Task 2: DB models + Alembic migration

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_initial.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `app.config:get_settings()` (Task 1)
- Produces: `app.db:Base` (declarative base), `app.db:engine`, `app.db:SessionLocal`, `app.db:get_db()` (generator yielding a `Session`); ORM models `app.models:Organization(id, name, kind, domain)`, `app.models:User(id, org_id, email, name, role, phone, created_at)`, `app.models:Request(id, org_id, submitted_by, brand, market, device, status, total, created_at)`.

- [ ] **Step 1: Write `backend/app/db.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Write `backend/app/models.py`**

```python
import datetime as dt

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # "internal" | "customer"
    domain: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="users")


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    brand: Mapped[str] = mapped_column(String(200), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    device: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Awaiting assignment")
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
```

- [ ] **Step 3: Write `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Write `backend/alembic/env.py`**

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db import Base
from app import models  # noqa: F401 — registers models on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                      prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Write `backend/alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Write `backend/alembic/versions/0001_initial.py`**

```python
"""initial: organizations, users, requests

Revision ID: 0001
Revises:
Create Date: 2026-08-15

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("domain", sa.String(200), nullable=False, unique=True),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("brand", sa.String(200), nullable=False),
        sa.Column("market", sa.String(50), nullable=False),
        sa.Column("device", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="Awaiting assignment"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("requests")
    op.drop_table("users")
    op.drop_table("organizations")
```

- [ ] **Step 7: Write the test — `backend/tests/test_models.py`** (uses SQLite in-memory to verify the ORM layer independent of Postgres/Alembic)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Organization, User, Request


def test_create_org_user_request_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    org = Organization(name="Shaily", kind="internal", domain="shaily.com")
    db.add(org)
    db.flush()

    user = User(org_id=org.id, email="a@shaily.com", name="Alice", role="BD Manager")
    db.add(user)
    db.flush()

    req = Request(org_id=org.id, submitted_by=user.id, brand="Ozempic", market="US")
    db.add(req)
    db.commit()

    fetched = db.query(Request).one()
    assert fetched.brand == "Ozempic"
    assert fetched.org_id == org.id
    assert fetched.status == "Awaiting assignment"
```

- [ ] **Step 8: Run test to verify it fails, then passes**

Run: `pytest backend/tests/test_models.py -v`
Expected: fails first with `ImportError` if models.py is missing any piece; after Steps 1–2 are in place, PASS.

- [ ] **Step 9: Apply the migration against a local Postgres to confirm it runs** (requires Task 9's `docker-compose.yml` for `postgres`; if not yet created, start one ad hoc)

```bash
docker run -d --name bdconsole-pg -e POSTGRES_USER=bdconsole -e POSTGRES_PASSWORD=bdconsole -e POSTGRES_DB=bdconsole -p 5432:5432 postgres:16
cd backend && DATABASE_URL="postgresql+psycopg2://bdconsole:bdconsole@localhost:5432/bdconsole" alembic upgrade head
docker stop bdconsole-pg && docker rm bdconsole-pg
```

Expected: `Running upgrade -> 0001, initial: organizations, users, requests` with no errors.

- [ ] **Step 10: Commit**

```bash
git add backend/app/db.py backend/app/models.py backend/alembic.ini backend/alembic/ backend/tests/test_models.py
git commit -m "feat(backend): SQLAlchemy models + initial Alembic migration"
```

---

### Task 3: JWT security + mock login endpoint

**Files:**
- Create: `backend/app/security.py`
- Create: `backend/app/schemas.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `app.db:get_db` (Task 2), `app.models:Organization, User` (Task 2), `app.config:get_settings()` (Task 1)
- Produces: `app.security:create_token(user_id: int, org_id: int, role: str) -> str`, `app.security:decode_token(token: str) -> dict` (raises `jwt.InvalidTokenError` on failure), `app.schemas:LoginRequest(name: str, email: str, role: str | None)`, `app.schemas:LoginResponse(access_token: str, token_type: str, user: UserOut)`, `app.schemas:UserOut(id, org_id, name, email, role)`, router `app.routers.auth:router` mounted at `/auth`.

- [ ] **Step 1: Write `backend/app/security.py`**

```python
import datetime as dt

import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def create_token(user_id: int, org_id: int, role: str) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "org_id": org_id,
        "role": role,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
```

- [ ] **Step 2: Write `backend/app/schemas.py`**

```python
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    name: str
    email: EmailStr
    role: str | None = None  # required when email domain is shaily.com


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


class RequestCreate(BaseModel):
    brand: str
    market: str
    device: str | None = None
    total: float = 0


class RequestOut(BaseModel):
    id: int
    org_id: int
    submitted_by: int
    brand: str
    market: str
    device: str | None
    status: str
    total: float
```

- [ ] **Step 3: Write `backend/app/routers/auth.py`**

Mock login: looks up or creates the organization by email domain (`@shaily.com` → internal org "Shaily", role must be one of `BD Manager`/`Key Account Manager`; any other domain → customer org named after the domain, role forced to `Customer`), looks up or creates the user, and returns a signed token. This mirrors the current `app.py` gate logic (`"@shaily." in email.lower()` deciding role choices) but persists the result instead of only holding it in `st.session_state`.

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Organization, User
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.security import create_token

router = APIRouter(prefix="/auth", tags=["auth"])

INTERNAL_DOMAIN = "shaily.com"
INTERNAL_ROLES = {"BD Manager", "Key Account Manager"}


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

    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.org_id, user.role)
    return LoginResponse(access_token=token, user=UserOut(
        id=user.id, org_id=user.org_id, name=user.name, email=user.email, role=user.role))
```

- [ ] **Step 4: Mount the router — modify `backend/app/main.py`**

```python
from app.routers.auth import router as auth_router
app.include_router(auth_router)
```

(Add this import/line after the existing `app = FastAPI(...)` block.)

- [ ] **Step 5: Write the test — `backend/tests/test_auth.py`** (overrides `get_db` with a SQLite session per test)

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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


def test_login_internal_requires_role(client):
    resp = client.post("/auth/login", json={"name": "Mahesh", "email": "mahesh@shaily.com"})
    assert resp.status_code == 422


def test_login_internal_ok(client):
    resp = client.post("/auth/login", json={
        "name": "Mahesh", "email": "mahesh@shaily.com", "role": "BD Manager"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "BD Manager"
    assert body["access_token"]


def test_login_customer_creates_org_by_domain(client):
    resp = client.post("/auth/login", json={"name": "Dr. Mehta", "email": "anaya@pfizer.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "Customer"
```

- [ ] **Step 6: Run tests to verify they fail, then pass**

Run: `pytest backend/tests/test_auth.py -v`
Expected: fails first (router not mounted) → after Steps 1–4, PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/security.py backend/app/schemas.py backend/app/routers/__init__.py backend/app/routers/auth.py backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(backend): JWT tokens + mock domain-based login endpoint"
```

---

### Task 4: Org-scope dependency + requests endpoints

**Files:**
- Create: `backend/app/deps.py`
- Create: `backend/app/routers/requests.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_requests.py`

**Interfaces:**
- Consumes: `app.security:decode_token` (Task 3), `app.db:get_db` (Task 2), `app.models:User, Request` (Task 2), `app.schemas:RequestCreate, RequestOut` (Task 3)
- Produces: `app.deps:get_current_user(token, db) -> User` (FastAPI dependency reading the `Authorization: Bearer <token>` header, 401 on missing/invalid token or unknown user), router `app.routers.requests:router` mounted at `/requests`.

- [ ] **Step 1: Write `backend/app/deps.py`**

```python
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
import jwt

from app.db import get_db
from app.models import User
from app.security import decode_token


def get_current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(401, "User no longer exists")
    return user
```

Org scoping itself is enforced inline in each route below by always filtering on `current_user.org_id` — every data-access route depends on `get_current_user` and never accepts an `org_id` from the client.

- [ ] **Step 2: Write `backend/app/routers/requests.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Request, User
from app.schemas import RequestCreate, RequestOut

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=RequestOut, status_code=201)
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    req = Request(org_id=current_user.org_id, submitted_by=current_user.id,
                   brand=payload.brand, market=payload.market, device=payload.device,
                   total=payload.total)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("", response_model=list[RequestOut])
def list_requests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Request).filter_by(org_id=current_user.org_id).order_by(Request.created_at.desc()).all()
```

- [ ] **Step 3: Mount the router — modify `backend/app/main.py`**

```python
from app.routers.requests import router as requests_router
app.include_router(requests_router)
```

- [ ] **Step 4: Write the test — `backend/tests/test_requests.py`** (reuses the SQLite-override pattern from Task 3; asserts cross-org isolation)

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
    return resp.json()["access_token"]


def test_create_and_list_request(client):
    token = _login(client, "anaya@pfizer.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "Awaiting assignment"

    resp = client.get("/requests", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_requests_are_org_isolated(client):
    pfizer_token = _login(client, "anaya@pfizer.com")
    other_token = _login(client, "someone@othercompany.com")

    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {pfizer_token}"})

    resp = client.get("/requests", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.json() == []


def test_requests_requires_auth(client):
    resp = client.get("/requests")
    assert resp.status_code == 401
```

- [ ] **Step 5: Run tests to verify they fail, then pass**

Run: `pytest backend/tests/test_requests.py -v`
Expected: fails first (router/module missing) → after Steps 1–3, PASS, including the org-isolation test.

- [ ] **Step 6: Commit**

```bash
git add backend/app/deps.py backend/app/routers/requests.py backend/app/main.py backend/tests/test_requests.py
git commit -m "feat(backend): org-scoped requests endpoints"
```

---

### Task 5: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Consumes: `backend/requirements.txt` (Task 1), `backend/app/` (Tasks 1–4), `backend/alembic/` (Task 2)
- Produces: a container image exposing port 8000, running `alembic upgrade head` then `uvicorn app.main:app` — consumed by Task 9 (docker-compose) and Task 10 (ECS task definition).

- [ ] **Step 1: Write `backend/.dockerignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
tests/
```

- [ ] **Step 2: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 3: Build the image locally to verify it builds**

```bash
cd backend && docker build -t bdconsole-backend:local .
```

Expected: build completes with no errors (no need to run it yet — Task 9 wires it to a real Postgres via compose).

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "feat(backend): Dockerfile"
```

---

### Task 6: Frontend scaffold + API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.js`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/lib/api.ts`
- Create: `frontend/.env.example`

**Interfaces:**
- Produces: `lib/api.ts` exporting `login(name: string, email: string, role?: string): Promise<{access_token: string, user: object}>`, `createRequest(token: string, body: {brand: string, market: string, device?: string}): Promise<object>`, `listRequests(token: string): Promise<object[]>`, all reading the API base URL from `process.env.NEXT_PUBLIC_API_URL`.

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "bdconsole-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "14.2.13",
    "react": "18.3.1",
    "react-dom": "18.3.1"
  },
  "devDependencies": {
    "typescript": "5.6.2",
    "@types/react": "18.3.5",
    "@types/node": "22.5.5"
  }
}
```

- [ ] **Step 2: Write `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Write `frontend/next.config.js`**

```js
/** @type {import('next').NextConfig} */
const nextConfig = {};
module.exports = nextConfig;
```

- [ ] **Step 4: Write `frontend/lib/api.ts`**

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function login(name: string, email: string, role?: string) {
  const resp = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, role }),
  });
  if (!resp.ok) throw new Error(`Login failed: ${resp.status}`);
  return resp.json();
}

export async function createRequest(
  token: string,
  body: { brand: string; market: string; device?: string }
) {
  const resp = await fetch(`${API_URL}/requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Create request failed: ${resp.status}`);
  return resp.json();
}

export async function listRequests(token: string) {
  const resp = await fetch(`${API_URL}/requests`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`List requests failed: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 5: Write `frontend/app/layout.tsx`**

```tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 6: Write `frontend/app/page.tsx`** (redirect root to login for now — Task 7 builds the real login page)

```tsx
"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/login");
  }, [router]);
  return null;
}
```

- [ ] **Step 7: Write `frontend/.env.example`**

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 8: Install deps and verify the dev server boots**

```bash
cd frontend && npm install && npm run build
```

Expected: build completes with no TypeScript errors (the `/login` route referenced by `page.tsx` doesn't exist yet — that's fine, Next.js only fails the build on errors in routes that exist; Task 7 adds it next).

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/next.config.js frontend/app/layout.tsx frontend/app/page.tsx frontend/lib/api.ts frontend/.env.example
git commit -m "feat(frontend): Next.js scaffold + API client"
```

---

### Task 7: Frontend login page

**Files:**
- Create: `frontend/app/login/page.tsx`

**Interfaces:**
- Consumes: `lib/api.ts:login()` (Task 6)
- Produces: stores `access_token` and `user` in `localStorage` under keys `bdconsole_token` / `bdconsole_user` — consumed by Task 8's requests page.

- [ ] **Step 1: Write `frontend/app/login/page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

const INTERNAL_ROLES = ["BD Manager", "Key Account Manager"];

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState("");

  const isInternal = email.toLowerCase().endsWith("@shaily.com");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const result = await login(name, email, isInternal ? role : undefined);
      localStorage.setItem("bdconsole_token", result.access_token);
      localStorage.setItem("bdconsole_user", JSON.stringify(result.user));
      router.push("/requests");
    } catch (err) {
      setError("Login failed. Check your details and try again.");
    }
  }

  return (
    <main>
      <h1>Sign in to the BD Console</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        {isInternal && (
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value)} required>
              <option value="">Select…</option>
              {INTERNAL_ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
        )}
        {error && <p role="alert">{error}</p>}
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}
```

- [ ] **Step 2: Verify the build still succeeds**

```bash
cd frontend && npm run build
```

Expected: PASS, no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/login/page.tsx
git commit -m "feat(frontend): login page wired to mock login endpoint"
```

---

### Task 8: Frontend request submission + list page

**Files:**
- Create: `frontend/app/requests/page.tsx`

**Interfaces:**
- Consumes: `lib/api.ts:createRequest(), listRequests()` (Task 6), `localStorage` keys `bdconsole_token`/`bdconsole_user` (Task 7)

- [ ] **Step 1: Write `frontend/app/requests/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, listRequests } from "@/lib/api";

type RequestRow = {
  id: number;
  brand: string;
  market: string;
  device: string | null;
  status: string;
  total: number;
};

export default function RequestsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");

  useEffect(() => {
    const t = localStorage.getItem("bdconsole_token");
    if (!t) {
      router.replace("/login");
      return;
    }
    setToken(t);
    listRequests(t).then(setRequests);
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    await createRequest(token, { brand, market });
    setRequests(await listRequests(token));
    setBrand("");
  }

  if (!token) return null;

  return (
    <main>
      <h1>Requests</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Brand
          <input value={brand} onChange={(e) => setBrand(e.target.value)} required />
        </label>
        <label>
          Market
          <select value={market} onChange={(e) => setMarket(e.target.value)}>
            <option value="US">US</option>
            <option value="EU">EU</option>
            <option value="Canada">Canada</option>
          </select>
        </label>
        <button type="submit">Submit request</button>
      </form>
      <table>
        <thead>
          <tr><th>ID</th><th>Brand</th><th>Market</th><th>Status</th></tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td><td>{r.brand}</td><td>{r.market}</td><td>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
```

- [ ] **Step 2: Verify the build still succeeds**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/requests/page.tsx
git commit -m "feat(frontend): request submission + list page"
```

---

### Task 9: Frontend Dockerfile + full-stack docker-compose

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Create: `docker-compose.yml`
- Create: `.env.example`

**Interfaces:**
- Consumes: `backend/Dockerfile` (Task 5), `frontend/` (Tasks 6–8)
- Produces: three running local services (`postgres`, `backend` on :8000, `frontend` on :3000) usable for manual end-to-end verification and as the pattern Task 10's ECS task definitions mirror.

- [ ] **Step 1: Write `frontend/.dockerignore`**

```
node_modules/
.next/
```

- [ ] **Step 2: Write `frontend/Dockerfile`**

```dockerfile
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json .
COPY --from=builder /app/next.config.js .
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["npm", "start"]
```

(`frontend/public/` doesn't exist yet — create an empty `frontend/public/.gitkeep` alongside this step so the `COPY` doesn't fail.)

- [ ] **Step 3: Write `frontend/public/.gitkeep`**

```
```

(empty file)

- [ ] **Step 4: Write root `.env.example`**

```
POSTGRES_USER=bdconsole
POSTGRES_PASSWORD=bdconsole
POSTGRES_DB=bdconsole
JWT_SECRET=dev-only-secret-change-me
```

- [ ] **Step 5: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-bdconsole}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bdconsole}
      POSTGRES_DB: ${POSTGRES_DB:-bdconsole}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+psycopg2://${POSTGRES_USER:-bdconsole}:${POSTGRES_PASSWORD:-bdconsole}@postgres:5432/${POSTGRES_DB:-bdconsole}
      JWT_SECRET: ${JWT_SECRET:-dev-only-secret-change-me}
      CORS_ORIGINS: '["http://localhost:3000"]'
    ports:
      - "8000:8000"
    depends_on:
      - postgres

  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  pgdata:
```

- [ ] **Step 6: Bring the stack up and manually verify the end-to-end flow**

```bash
docker compose up --build -d
sleep 5
curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"name":"Dr. Mehta","email":"anaya@pfizer.com"}'
```

Expected: JSON response with `access_token` and `"role":"Customer"`. Then open `http://localhost:3000/login` in a browser, sign in, submit a request on `/requests`, and confirm it appears in the table.

```bash
docker compose down -v
```

- [ ] **Step 7: Commit**

```bash
git add frontend/Dockerfile frontend/.dockerignore frontend/public/.gitkeep docker-compose.yml .env.example
git commit -m "feat: docker-compose for local full-stack dev"
```

---

### Task 10: AWS infra (Terraform) + deploy

**Files:**
- Create: `infra/terraform/main.tf`
- Create: `infra/terraform/variables.tf`
- Create: `infra/terraform/outputs.tf`
- Create: `infra/terraform/ecr.tf`
- Create: `infra/terraform/rds.tf`
- Create: `infra/terraform/ecs.tf`
- Create: `infra/terraform/alb.tf`

**Interfaces:**
- Consumes: `backend/Dockerfile` (Task 5), `frontend/Dockerfile` (Task 9)
- Produces: two ECR repos, one RDS Postgres instance, one ECS Fargate cluster running the two services, one ALB routing `/api/*` → backend, everything else → frontend. Outputs `alb_dns_name`.

- [ ] **Step 1: Write `infra/terraform/main.tf`**

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
```

- [ ] **Step 2: Write `infra/terraform/variables.tf`**

```hcl
variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "bdconsole"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}
```

- [ ] **Step 3: Write `infra/terraform/ecr.tf`**

```hcl
resource "aws_ecr_repository" "backend" {
  name = "${var.project}-backend"
}

resource "aws_ecr_repository" "frontend" {
  name = "${var.project}-frontend"
}
```

- [ ] **Step 4: Write `infra/terraform/rds.tf`**

```hcl
resource "aws_security_group" "rds" {
  name   = "${var.project}-rds-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db-subnets"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "main" {
  identifier              = "${var.project}-db"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = "db.t4g.micro"
  allocated_storage       = 20
  db_name                 = "bdconsole"
  username                = "bdconsole"
  password                = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  skip_final_snapshot     = true
  publicly_accessible     = false
}
```

- [ ] **Step 5: Write `infra/terraform/alb.tf`**

```hcl
resource "aws_security_group" "alb" {
  name   = "${var.project}-alb-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "main" {
  name               = "${var.project}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project}-backend-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip"
  health_check {
    path = "/health"
  }
}

resource "aws_lb_target_group" "frontend" {
  name        = "${var.project}-frontend-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip"
  health_check {
    path = "/login"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 1

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/auth/*", "/requests*"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
```

- [ ] **Step 6: Write `infra/terraform/ecs.tf`**

```hcl
resource "aws_ecs_cluster" "main" {
  name = "${var.project}-cluster"
}

resource "aws_security_group" "ecs" {
  name   = "${var.project}-ecs-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "ecs_execution" {
  name = "${var.project}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  container_definitions = jsonencode([{
    name  = "backend"
    image = "${aws_ecr_repository.backend.repository_url}:latest"
    portMappings = [{ containerPort = 8000 }]
    environment = [
      { name = "DATABASE_URL", value = "postgresql+psycopg2://bdconsole:${var.db_password}@${aws_db_instance.main.address}:5432/bdconsole" },
      { name = "JWT_SECRET", value = var.jwt_secret },
      { name = "CORS_ORIGINS", value = "[\"http://${aws_lb.main.dns_name}\"]" },
    ]
  }])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.project}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  container_definitions = jsonencode([{
    name  = "frontend"
    image = "${aws_ecr_repository.frontend.repository_url}:latest"
    portMappings = [{ containerPort = 3000 }]
    environment = [
      { name = "NEXT_PUBLIC_API_URL", value = "http://${aws_lb.main.dns_name}" },
    ]
  }])
}

resource "aws_ecs_service" "backend" {
  name            = "${var.project}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name    = "backend"
    container_port     = 8000
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "frontend" {
  name            = "${var.project}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name    = "frontend"
    container_port     = 3000
  }

  depends_on = [aws_lb_listener.http]
}
```

- [ ] **Step 7: Write `infra/terraform/outputs.tf`**

```hcl
output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "backend_ecr_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_url" {
  value = aws_ecr_repository.frontend.repository_url
}
```

- [ ] **Step 8: Provision infra, then build/push/deploy images**

```bash
cd infra/terraform
terraform init
terraform apply -var="db_password=$(openssl rand -hex 16)" -var="jwt_secret=$(openssl rand -hex 32)"
```

Expected: Terraform prompts for approval, then creates ECR/RDS/ECS/ALB resources and prints `alb_dns_name`.

```bash
BACKEND_REPO=$(terraform output -raw backend_ecr_url)
FRONTEND_REPO=$(terraform output -raw frontend_ecr_url)
aws ecr get-login-password | docker login --username AWS --password-stdin "${BACKEND_REPO%/*}"

cd ../../backend
docker build -t "$BACKEND_REPO:latest" . && docker push "$BACKEND_REPO:latest"

cd ../frontend
docker build -t "$FRONTEND_REPO:latest" . && docker push "$FRONTEND_REPO:latest"

aws ecs update-service --cluster bdconsole-cluster --service bdconsole-backend --force-new-deployment
aws ecs update-service --cluster bdconsole-cluster --service bdconsole-frontend --force-new-deployment
```

- [ ] **Step 9: Commit**

```bash
git add infra/terraform
git commit -m "feat(infra): Terraform for ECR/RDS/ECS Fargate/ALB"
```

---

### Task 11: End-to-end smoke test against the deployed AWS stack

**Files:**
- Create: `scripts/smoke_test.sh`

**Interfaces:**
- Consumes: the deployed `alb_dns_name` (Task 10 output)

- [ ] **Step 1: Write `scripts/smoke_test.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

ALB_DNS="${1:?Usage: smoke_test.sh <alb-dns-name>}"
BASE="http://${ALB_DNS}"

echo "→ Health check"
curl -sf "${BASE}/health" | grep -q '"status":"ok"'

echo "→ Login as a customer"
LOGIN_RESP=$(curl -sf -X POST "${BASE}/auth/login" -H "Content-Type: application/json" \
  -d '{"name":"Smoke Test","email":"smoke@example.com"}')
TOKEN=$(echo "$LOGIN_RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "→ Submit a request"
curl -sf -X POST "${BASE}/requests" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"brand":"Ozempic","market":"US"}' | grep -q '"status":"Awaiting assignment"'

echo "→ List requests, expect exactly one"
COUNT=$(curl -sf "${BASE}/requests" -H "Authorization: Bearer ${TOKEN}" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')
[ "$COUNT" = "1" ]

echo "✓ Smoke test passed against ${BASE}"
```

- [ ] **Step 2: Run it against the deployed stack**

```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh "$(cd infra/terraform && terraform output -raw alb_dns_name)"
```

Expected: `✓ Smoke test passed against http://<alb-dns-name>` — this confirms the full chain (ALB → ECS backend → RDS, and the routing rule that will also serve the frontend) works in AWS, not just locally. This is the foundation-slice exit criterion from spec §8.1.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_test.sh
git commit -m "test: end-to-end smoke test against deployed AWS stack"
```

---

## Self-Review Notes

- **Spec coverage:** §4 architecture → Tasks 1–10. §5 data model (organizations/users/requests subset) → Task 2. §6 mock auth → Task 3. §8 step 1 (foundation slice + AWS deploy) → all tasks, verified by Task 11. Full data model (sku_rows, deliverables, uploaded_files, audit_log, reference data), real magic-link auth, dashboards, and UI refinement are explicitly out of scope for this plan — they belong to Phases 2–6 (spec §8 steps 2–6), each to get its own plan once this one lands.
- **Placeholder scan:** none found — every step has runnable code or an exact command.
- **Type consistency:** `RequestOut`/`RequestCreate` fields match `Request` ORM columns; `LoginResponse.user` matches `UserOut`; frontend `RequestRow` type matches the JSON shape `RequestOut` serializes to; `get_current_user` return type (`User`) matches what `requests.py` routes depend on.
