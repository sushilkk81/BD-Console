# Core Customer Flow (Request → Platform Options → Cost & Deal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the legacy Streamlit app's three-screen customer flow (request form → platform options → cost & deal) onto the real FastAPI/Postgres backend and Next.js frontend, with draft persistence from step 1 onward.

**Architecture:** A new Alembic migration adds `sku_rows`, `service_selections`, seeded reference-data tables (`reference_products`, `reference_product_markets`, `platform_sheet`, `service_pricing`), and new columns on `requests`. A new `app/services/platform_matching.py` ports the mechanism-similarity ranking algorithm verbatim; a new `app/services/reference_data.py` ports the RLD-merge/presentation lookup. `requests.py` gains the wizard endpoints (create/edit draft, compute options, select option, price services, submit). The frontend replaces the current single-page request list/form with a list-of-drafts-and-submissions page plus a three-step wizard at `/requests/[id]`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest (backend); Next.js App Router, React, Tailwind (frontend). No new dependencies.

**Spec:** [`docs/superpowers/core-customer-flow/design.md`](design.md)

## Global Constraints

- No `sub_fy`/`sub_q`/`dossier_fy` fields anywhere (spec §3).
- No deliverable/drawing schedule, no cost negotiation UI, no file uploads (spec §3).
- No changes to the ranking/pricing math — `mechanism_similarity`, `rank_platforms_for_sku`, and the DV/threshold/IFU/human-factor cost formulas are a straight port (spec §3, §5). Same weights `W_ARCH=0.5, W_DRIVE=0.3, W_DOSE=0.2`, band thresholds `BAND_CLOSE=0.80, BAND_SIMILAR=0.50`.
- No multi-draft limit — any number of a customer's drafts may exist at once (spec §3).
- Every request-mutation endpoint requires `get_current_user` plus an ownership check (`submitted_by == current_user.id`) — 404 (not 403) on mismatch, to avoid confirming a request id exists to a non-owner (spec §5, §7).
- 409 on any mutation attempted against a non-Draft request (spec §5, §7).
- `GET /requests/{id}` uses the same role-scoping as `list_requests` (owner Customer, any-org BD Manager, assigned KAM), not the strict-ownership rule the mutation endpoints use (spec §5).
- SQLite (test suite) doesn't enforce `VARCHAR` lengths — be explicit about column widths matching Postgres, and truncate any user-derived string written into a length-limited column (see `backend/app/routers/kams.py`'s `STATUS_MAX_LEN`/`DETAIL_MAX_LEN` pattern).
- Frontend: no test framework — verification is `npm run build` plus manual/curl smoke testing (spec §7).

## Implementation decisions filling spec's open items (§8)

These resolve gaps the spec left to planning — noted here so later tasks don't re-litigate them:

1. **Base (non-market-override) presentation data needs a home.** The spec's `reference_products` table (§4) has no `presentations` column, but the legacy `PRESENTATIONS` dict (brand → strength → cartridge/fill) is the *base* lookup that `reference_product_markets` only overrides for 4 (brand, market) pairs. This plan adds `presentations` (JSON) and `presentations_ref` (string) columns to `reference_products` to hold it — otherwise `presentation_for` would have nowhere to read the non-overridden cases from.
2. **`GET /reference-products` response shape**: brand, molecule, device, strengths, visc_val, visc_ref, cartridge — enough for step-1 selects and defaults, nothing else (platform-sheet/mechanism internals stay server-side, used only by the ranking endpoint).
3. **Cartridge/fill validation**: `SkuRowIn.cartridge` is validated against the seeded `CART_SIZES` list (`1.5 mL`, `3 mL`, `1 mL PFS`, `3 mL PFS`, `1 mL Bespoke`) with a Pydantic validator — matches the legacy `SelectboxColumn`'s fixed option list. `fill_ml` just needs `gt=0`.
4. **`PUT /requests/{id}`'s full sku_rows replace, reconciled with `service_selections`' FK.** The endpoint always receives the *full* current SKU table from the frontend (per spec), but "replace" is implemented as an upsert-by-strength (update cartridge/fill_ml in place for strengths still present, delete rows for strengths removed, insert rows for strengths newly added) rather than delete-everything-then-recreate. This preserves `sku_rows.id` — and therefore `service_selections` rows — for any SKU whose strength didn't change, which is what makes "cascade only when brand/market/strengths changed" (spec §5) a coherent rule rather than one that dangles FKs on every edit.

---

## Backend

### Task 1: Migration 0003 — schema + seed reference data

**Files:**
- Create: `backend/alembic/versions/0003_core_customer_flow.py`
- Test: `backend/tests/test_models.py` (extend)

**Interfaces:**
- Produces: tables `sku_rows`, `service_selections`, `reference_products`, `reference_product_markets`, `platform_sheet`, `service_pricing`; new columns on `requests` (`viscosity_val`, `differentiated`, `chosen_option`, `severity`, `timeline_months`, `comment`, `urgency`); `requests.status` default becomes `"Draft"`.

- [ ] **Step 1: Write the migration**

```python
"""Core customer flow: sku_rows, service_selections, seeded reference data, requests fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("viscosity_val", sa.Numeric(6, 2), nullable=True))
    op.add_column("requests", sa.Column("differentiated", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("requests", sa.Column("chosen_option", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("severity", sa.String(20), nullable=True))
    op.add_column("requests", sa.Column("timeline_months", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("comment", sa.String(2000), nullable=True))
    op.add_column("requests", sa.Column("urgency", sa.String(100), nullable=True))
    op.alter_column("requests", "status", server_default="Draft")

    op.create_table(
        "sku_rows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("strength", sa.String(50), nullable=False),
        sa.Column("cartridge", sa.String(50), nullable=False),
        sa.Column("fill_ml", sa.Numeric(6, 2), nullable=False),
    )
    op.create_table(
        "service_selections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku_row_id", sa.Integer, sa.ForeignKey("sku_rows.id"), nullable=False),
        sa.Column("standard_dv", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("threshold", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ifu", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("human_factor", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "reference_products",
        sa.Column("brand", sa.String(100), primary_key=True),
        sa.Column("molecule", sa.String(200), nullable=False),
        sa.Column("device", sa.String(100), nullable=False),
        sa.Column("dose", sa.String(20), nullable=False),
        sa.Column("visc", sa.String(20), nullable=False),
        sa.Column("visc_val", sa.Numeric(6, 2), nullable=False),
        sa.Column("cartridge", sa.String(50), nullable=False),
        sa.Column("strengths", sa.JSON, nullable=False),
        sa.Column("visc_ref", sa.String(300), nullable=False),
        sa.Column("mech_drive", sa.String(50), nullable=False),
        sa.Column("mech_dose", sa.String(20), nullable=False),
        sa.Column("mech_label", sa.String(200), nullable=False),
        sa.Column("ob_ref", sa.String(300), nullable=False),
        sa.Column("ob_claims", sa.JSON, nullable=False),
        sa.Column("presentations", sa.JSON, nullable=False),
        sa.Column("presentations_ref", sa.String(300), nullable=False, server_default=""),
    )
    op.create_table(
        "reference_product_markets",
        sa.Column("brand", sa.String(100), sa.ForeignKey("reference_products.brand"), primary_key=True),
        sa.Column("market", sa.String(50), primary_key=True),
        sa.Column("device", sa.String(100), nullable=True),
        sa.Column("mech_drive", sa.String(50), nullable=True),
        sa.Column("mech_dose", sa.String(20), nullable=True),
        sa.Column("mech_label", sa.String(200), nullable=True),
        sa.Column("ob_ref", sa.String(300), nullable=True),
        sa.Column("ob_claims", sa.JSON, nullable=True),
        sa.Column("market_note", sa.String(300), nullable=True),
        sa.Column("presentations", sa.JSON, nullable=True),
        sa.Column("pres_ref", sa.String(300), nullable=True),
    )
    op.create_table(
        "platform_sheet",
        sa.Column("variant", sa.String(100), primary_key=True),
        sa.Column("family", sa.String(100), nullable=False),
        sa.Column("cls", sa.String(50), nullable=False),
        sa.Column("sub", sa.String(50), nullable=False, server_default=""),
        sa.Column("resolution", sa.String(200), nullable=False),
        sa.Column("lockout", sa.String(10), nullable=False),
        sa.Column("carts", sa.JSON, nullable=False),
        sa.Column("mech", sa.String(50), nullable=False),
        sa.Column("color", sa.String(10), nullable=False),
        sa.Column("moderate", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "service_pricing",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("payload", sa.JSON, nullable=False),
    )

    ref_products = sa.table(
        "reference_products", sa.column("brand", sa.String), sa.column("molecule", sa.String),
        sa.column("device", sa.String), sa.column("dose", sa.String), sa.column("visc", sa.String),
        sa.column("visc_val", sa.Numeric), sa.column("cartridge", sa.String), sa.column("strengths", sa.JSON),
        sa.column("visc_ref", sa.String), sa.column("mech_drive", sa.String), sa.column("mech_dose", sa.String),
        sa.column("mech_label", sa.String), sa.column("ob_ref", sa.String), sa.column("ob_claims", sa.JSON),
        sa.column("presentations", sa.JSON), sa.column("presentations_ref", sa.String),
    )
    op.bulk_insert(ref_products, [
        dict(brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
             visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg", "0.5 mg", "1 mg", "2 mg"],
             visc_ref="DailyMed SmPC (NDC 0169-4181); aqueous GLP-1 solution",
             mech_drive="torsion_spring", mech_dose="variable",
             mech_label="FlexTouch dial pen — torsion-spring + lead-screw",
             ob_ref="FDA Orange Book device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
             ob_claims=["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set variable dose"],
             presentations={"0.25 mg": ["1.5 mL", 1.5], "0.5 mg": ["1.5 mL", 1.5], "1 mg": ["3 mL", 3.0], "2 mg": ["3 mL", 3.0]},
             presentations_ref="Ozempic FDA label 209637 / DailyMed — 2 mg/1.5 mL, 4 mg/3 mL, 8 mg/3 mL pens"),
        dict(brand="Wegovy", molecule="Semaglutide", device="Auto-Injector", dose="fixed", visc="water",
             visc_val=1.6, cartridge="1 mL PFS", strengths=["0.25 mg", "0.5 mg", "1 mg", "1.7 mg", "2.4 mg"],
             visc_ref="FDA label 215256; single-dose AI",
             mech_drive="spring_single", mech_dose="fixed", mech_label="Single-dose spring pen",
             ob_ref="FDA Orange Book device patents — Wegovy single-dose pen (Novo Nordisk); exact patent nos. to confirm",
             ob_claims=["Pre-set fixed dose", "Spring-assisted single delivery"],
             presentations={"0.25 mg": ["1 mL PFS", 0.5], "0.5 mg": ["1 mL PFS", 0.5], "1 mg": ["1 mL PFS", 0.5],
                             "1.7 mg": ["1 mL PFS", 0.75], "2.4 mg": ["1 mL PFS", 0.75]},
             presentations_ref="Wegovy PI (Novo Nordisk) — single-dose pens 0.5 mL (≤1 mg), 0.75 mL (1.7/2.4 mg)"),
        dict(brand="Trulicity", molecule="Dulaglutide", device="Auto-Injector", dose="fixed", visc="higher",
             visc_val=6.2, cartridge="1 mL PFS", strengths=["0.75 mg", "1.5 mg", "3 mg", "4.5 mg"],
             visc_ref="Lilly label; mAb fusion, elevated viscosity",
             mech_drive="spring_ai", mech_dose="fixed", mech_label="Single-dose auto-injector (2-step, hidden needle)",
             ob_ref="FDA Orange Book device patents — Trulicity single-dose AI (Lilly); exact patent nos. to confirm",
             ob_claims=["Spring-driven auto-injection", "Automatic needle insertion + retraction", "Single fixed dose"],
             presentations={"0.75 mg": ["1 mL PFS", 0.5], "1.5 mg": ["1 mL PFS", 0.5], "3 mg": ["1 mL PFS", 0.5], "4.5 mg": ["1 mL PFS", 0.5]},
             presentations_ref="Trulicity FDA label 125469 — single-dose pen 0.5 mL, all doses"),
        dict(brand="Mounjaro", molecule="Tirzepatide", device="Auto-Injector", dose="fixed", visc="higher",
             visc_val=5.0, cartridge="1 mL PFS", strengths=["2.5 mg", "5 mg", "7.5 mg", "10 mg", "12.5 mg", "15 mg"],
             visc_ref="Lilly KwikPen literature",
             mech_drive="spring_ai", mech_dose="fixed", mech_label="Single-dose auto-injector",
             ob_ref="FDA Orange Book device patents — Mounjaro single-dose AI (Lilly); exact patent nos. to confirm",
             ob_claims=["Spring-driven auto-injection", "Push-on-skin activation", "Single fixed dose"],
             presentations={"2.5 mg": ["1 mL PFS", 0.5], "5 mg": ["1 mL PFS", 0.5], "7.5 mg": ["1 mL PFS", 0.5],
                             "10 mg": ["1 mL PFS", 0.5], "12.5 mg": ["1 mL PFS", 0.5], "15 mg": ["1 mL PFS", 0.5]},
             presentations_ref="Mounjaro DailyMed — single-dose pen 0.5 mL, all doses"),
        dict(brand="Victoza", molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water",
             visc_val=1.5, cartridge="3 mL", strengths=["0.6 mg", "1.2 mg", "1.8 mg"],
             visc_ref="EMA SmPC; multi-dose pen",
             mech_drive="torsion_spring", mech_dose="variable", mech_label="FlexTouch-type dial pen — torsion-spring",
             ob_ref="FDA Orange Book device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
             ob_claims=["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set variable dose"],
             presentations={"0.6 mg": ["3 mL", 3.0], "1.2 mg": ["3 mL", 3.0], "1.8 mg": ["3 mL", 3.0]},
             presentations_ref="Victoza DailyMed — 18 mg/3 mL multi-dose pen"),
        dict(brand="Saxenda", molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water",
             visc_val=1.5, cartridge="3 mL", strengths=["0.6 mg", "1.2 mg", "1.8 mg", "2.4 mg", "3 mg"],
             visc_ref="EMA SmPC; weight-management pen",
             mech_drive="torsion_spring", mech_dose="variable",
             mech_label="FlexTouch dial pen — torsion-spring + lead-screw",
             ob_ref="FDA Orange Book device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
             ob_claims=["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set variable dose"],
             presentations={"0.6 mg": ["3 mL", 3.0], "1.2 mg": ["3 mL", 3.0], "1.8 mg": ["3 mL", 3.0],
                             "2.4 mg": ["3 mL", 3.0], "3 mg": ["3 mL", 3.0]},
             presentations_ref="Saxenda EMA SmPC — 18 mg/3 mL multi-dose pen"),
        dict(brand="Toujeo", molecule="Insulin glargine U300", device="Pen Injector", dose="variable", visc="water",
             visc_val=1.8, cartridge="1.5 mL", strengths=["300 U/mL"],
             visc_ref="Sanofi label; basal insulin",
             mech_drive="manual_dial", mech_dose="variable", mech_label="SoloStar-type dial pen — manual lead-screw",
             ob_ref="FDA Orange Book device patents — SoloStar platform (Sanofi); exact patent nos. to confirm",
             ob_claims=["Manual dial-set variable dose", "Lead-screw plunger advance", "Button-push delivery"],
             presentations={"300 U/mL": ["1.5 mL", 1.5]},
             presentations_ref="Toujeo DailyMed — SoloStar 1.5 mL (450 U), U-300"),
        dict(brand="Lantus", molecule="Insulin glargine", device="Pen Injector", dose="variable", visc="water",
             visc_val=1.7, cartridge="3 mL", strengths=["100 U/mL"],
             visc_ref="Sanofi label; basal insulin",
             mech_drive="manual_dial", mech_dose="variable", mech_label="SoloStar dial pen — manual lead-screw",
             ob_ref="FDA Orange Book device patents — SoloStar platform (Sanofi); exact patent nos. to confirm",
             ob_claims=["Manual dial-set variable dose", "Lead-screw plunger advance", "Button-push delivery"],
             presentations={"100 U/mL": ["3 mL", 3.0]},
             presentations_ref="Lantus DailyMed — SoloStar 3 mL (300 U), U-100"),
        dict(brand="Humira", molecule="Adalimumab", device="Auto-Injector", dose="fixed", visc="higher",
             visc_val=12.5, cartridge="1 mL PFS", strengths=["10 mg", "20 mg", "40 mg", "80 mg"],
             visc_ref="AbbVie label; high-viscosity mAb",
             mech_drive="spring_ai_hv", mech_dose="fixed", mech_label="High-viscosity mAb auto-injector",
             ob_ref="FDA Orange Book device patents — Humira pen/AI (AbbVie); exact patent nos. to confirm",
             ob_claims=["Spring-driven auto-injection", "High-force delivery for viscous mAb", "Single fixed dose"],
             presentations={"10 mg": ["1 mL PFS", 0.1], "20 mg": ["1 mL PFS", 0.2], "40 mg": ["1 mL PFS", 0.4], "80 mg": ["1 mL PFS", 0.8]},
             presentations_ref="Humira IFU/label — citrate-free 40 mg/0.4 mL, 80 mg/0.8 mL, 20 mg/0.2 mL, 10 mg/0.1 mL"),
        dict(brand="Enbrel", molecule="Etanercept", device="Auto-Injector", dose="fixed", visc="higher",
             visc_val=9.0, cartridge="1 mL PFS", strengths=["25 mg", "50 mg"],
             visc_ref="Amgen label; mAb",
             mech_drive="spring_ai", mech_dose="fixed", mech_label="mAb auto-injector (SureClick-type)",
             ob_ref="FDA Orange Book device patents — SureClick platform (Amgen); exact patent nos. to confirm",
             ob_claims=["Spring-driven auto-injection", "Automatic needle insertion", "Single fixed dose"],
             presentations={"25 mg": ["1 mL PFS", 0.5], "50 mg": ["1 mL PFS", 1.0]},
             presentations_ref="Enbrel FDA label 103795 — SureClick 50 mg/1.0 mL, 25 mg/0.5 mL"),
        dict(brand="Dupixent", molecule="Dupilumab", device="Auto-Injector", dose="fixed", visc="higher",
             visc_val=8.5, cartridge="3 mL PFS", strengths=["200 mg", "300 mg"],
             visc_ref="Regeneron label; mAb",
             mech_drive="spring_ai", mech_dose="fixed", mech_label="mAb auto-injector / pre-filled pen",
             ob_ref="FDA Orange Book device patents — Dupixent pen (Regeneron/Sanofi); exact patent nos. to confirm",
             ob_claims=["Spring-driven auto-injection", "Pre-filled single dose", "Automatic delivery"],
             presentations={"200 mg": ["3 mL PFS", 1.14], "300 mg": ["3 mL PFS", 2.0]},
             presentations_ref="Dupixent DailyMed — pre-filled pen 200 mg/1.14 mL, 300 mg/2 mL"),
    ])

    ref_markets = sa.table(
        "reference_product_markets", sa.column("brand", sa.String), sa.column("market", sa.String),
        sa.column("device", sa.String), sa.column("mech_drive", sa.String), sa.column("mech_dose", sa.String),
        sa.column("mech_label", sa.String), sa.column("ob_ref", sa.String), sa.column("ob_claims", sa.JSON),
        sa.column("market_note", sa.String), sa.column("presentations", sa.JSON), sa.column("pres_ref", sa.String),
    )
    wegovy_eu_claims = ["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set dose", "Multi-dose reusable pen"]
    wegovy_presentations = {s: ["1.5 mL", 1.5] for s in ["0.25 mg", "0.5 mg", "1 mg", "1.7 mg", "2.4 mg"]}
    mounjaro_md_claims = ["Manual dial/push delivery", "Fixed 0.6 mL dose", "Multi-dose (4 doses/pen)"]
    mounjaro_presentations = {s: ["3 mL", 2.4] for s in ["2.5 mg", "5 mg", "7.5 mg", "10 mg", "12.5 mg", "15 mg"]}
    op.bulk_insert(ref_markets, [
        dict(brand="Wegovy", market="EU", device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable",
             mech_label="Wegovy FlexTouch multi-dose pen — torsion-spring",
             ob_ref="EMA/FDA device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
             ob_claims=wegovy_eu_claims, market_note="Multi-dose FlexTouch pen (1.5 mL) — differs from US single-dose",
             presentations=wegovy_presentations, pres_ref="EMA Wegovy SmPC — FlexTouch multi-dose pen, 1.5 mL (all strengths)"),
        dict(brand="Wegovy", market="Canada", device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable",
             mech_label="Wegovy FlexTouch multi-dose pen — torsion-spring",
             ob_ref="EMA/FDA device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
             ob_claims=wegovy_eu_claims, market_note="Multi-dose FlexTouch pen (1.5 mL) — differs from US single-dose",
             presentations=wegovy_presentations, pres_ref="Health Canada Wegovy Product Monograph — FlexTouch multi-dose pen"),
        dict(brand="Mounjaro", market="EU", device="Pen Injector", mech_drive="manual_dial", mech_dose="fixed",
             mech_label="Mounjaro KwikPen — multi-dose (4 × 0.6 mL)",
             ob_ref="EMA device patents — KwikPen platform (Lilly); exact patent nos. to confirm",
             ob_claims=mounjaro_md_claims, market_note="KwikPen multi-dose (4 doses/pen) — differs from US single-dose",
             presentations=mounjaro_presentations, pres_ref="EMA Mounjaro SmPC — KwikPen 2.4 mL (4 × 0.6 mL)"),
        dict(brand="Mounjaro", market="Canada", device="Pen Injector", mech_drive="manual_dial", mech_dose="fixed",
             mech_label="Mounjaro KwikPen — multi-dose (4 × 0.6 mL)",
             ob_ref="EMA device patents — KwikPen platform (Lilly); exact patent nos. to confirm",
             ob_claims=mounjaro_md_claims, market_note="KwikPen multi-dose (4 doses/pen) — differs from US single-dose",
             presentations=mounjaro_presentations, pres_ref="Health Canada Mounjaro KwikPen IFU — 2.4 mL (4 × 0.6 mL)"),
    ])

    platforms = sa.table(
        "platform_sheet", sa.column("variant", sa.String), sa.column("family", sa.String), sa.column("cls", sa.String),
        sa.column("sub", sa.String), sa.column("resolution", sa.String), sa.column("lockout", sa.String),
        sa.column("carts", sa.JSON), sa.column("mech", sa.String), sa.column("color", sa.String), sa.column("moderate", sa.Boolean),
    )
    op.bulk_insert(platforms, [
        dict(variant="Axiom", family="Axiom", cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",
             lockout="Yes", carts=["3 mL"], mech="Push-Pull", color="#8FBF52", moderate=False),
        dict(variant="Axiom Max", family="Axiom Max", cls="Pen Injector", sub="Disposable", resolution="Fixed – 80 IU",
             lockout="Yes", carts=["3 mL", "1.5 mL"], mech="Push-Pull", color="#E5883B", moderate=False),
        dict(variant="Protean P3", family="Protean", cls="Pen Injector", sub="Disposable",
             resolution="Variable – 3 dose settings – 80 IU", lockout="Yes", carts=["3 mL"], mech="Geared Pen", color="#5FA0C4", moderate=False),
        dict(variant="Protean P5", family="Protean", cls="Pen Injector", sub="Disposable",
             resolution="Variable – 5 dose settings – 80 IU", lockout="Yes", carts=["3 mL"], mech="Geared Pen", color="#5FA0C4", moderate=False),
        dict(variant="Protean P60", family="Protean", cls="Pen Injector", sub="Disposable", resolution="Fixed – 60 IU",
             lockout="Yes", carts=["3 mL"], mech="Geared Pen", color="#5FA0C4", moderate=False),
        dict(variant="Protean PS1", family="Protean", cls="Pen Injector", sub="Disposable", resolution="Fixed – only 1 dose",
             lockout="Yes", carts=["1.5 mL"], mech="Geared Pen", color="#5FA0C4", moderate=False),
        dict(variant="Protean PR60", family="Protean", cls="Pen Injector", sub="Reusable", resolution="Fixed – 60 IU",
             lockout="Yes", carts=["3 mL"], mech="Geared Pen", color="#5FA0C4", moderate=False),
        dict(variant="Neo (3 mL)", family="Neo", cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",
             lockout="Yes", carts=["3 mL"], mech="Torsion Spring", color="#7DB343", moderate=False),
        dict(variant="Neo (1.5 mL)", family="Neo", cls="Pen Injector", sub="Disposable", resolution="Variable Dose – 80 IU",
             lockout="Yes", carts=["1.5 mL"], mech="Torsion Spring", color="#7DB343", moderate=False),
        dict(variant="Harmony HS1", family="Harmony", cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",
             lockout="Yes", carts=["3 mL"], mech="Clutch Pen", color="#3D7CA6", moderate=False),
        dict(variant="Harmony H2", family="Harmony", cls="Pen Injector", sub="Disposable", resolution="Variable Dose – 80 IU",
             lockout="Yes", carts=["1.5 mL"], mech="Clutch Pen", color="#3D7CA6", moderate=False),
        dict(variant="Maxim (Disposable)", family="Maxim", cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",
             lockout="Yes", carts=["3 mL"], mech="Pulley", color="#2F6E97", moderate=False),
        dict(variant="Maxim (Reusable)", family="Maxim", cls="Pen Injector", sub="Reusable", resolution="Fixed Dose – 80 IU",
             lockout="Yes", carts=["3 mL"], mech="Pulley", color="#2F6E97", moderate=True),
        dict(variant="Tristan", family="Tristan", cls="Autoinjector", sub="", resolution="0.2 – 1 mL",
             lockout="N/A", carts=["1 mL PFS"], mech="3-step AI", color="#234F70", moderate=False),
        dict(variant="Toby", family="Toby", cls="Autoinjector", sub="", resolution="0.2 – 2.25 mL",
             lockout="N/A", carts=["1 mL PFS", "3 mL PFS"], mech="2-step AI", color="#2E7D46", moderate=False),
        dict(variant="Safe LAN", family="Safe-LAN", cls="Autoinjector", sub="", resolution="0.5 mL",
             lockout="N/A", carts=["1 mL Bespoke"], mech="2-step AI (high visc.)", color="#C0392B", moderate=False),
        dict(variant="Mira", family="Mira", cls="On-Body", sub="", resolution="0.5 – 20 mL",
             lockout="N/A", carts=["1 mL Bespoke"], mech="On-body device", color="#6D6E71", moderate=False),
    ])

    pricing = sa.table("service_pricing", sa.column("key", sa.String), sa.column("payload", sa.JSON))
    op.bulk_insert(pricing, [
        {"key": "PKG", "payload": {"minor": 200, "moderate": 250, "major": 350}},
        {"key": "ADD_DV", "payload": {"value": 50}},
        {"key": "TIMELINE", "payload": {"minor": 3, "moderate": 6, "major": 9}},
        {"key": "SEV_LABEL", "payload": {"minor": "Minor change", "moderate": "Moderate change", "major": "Major change"}},
        {"key": "SEV_LOGIC", "payload": {
            "minor": "Minor tool modification + tool validation",
            "moderate": "Up to 2 tool modifications + tool validation",
            "major": "> 2 tool modifications + tool validation",
        }},
        {"key": "SERVICES", "payload": {"standard_dv": 200, "threshold": 2110, "ifu": 1110, "human_factor": 400000}},
        {"key": "STD_CONDITION_TESTS", "payload": {"items": [
            "Deliverable Volume (ISO 11608-1)", "Dose Accuracy — rear", "Dose Accuracy — middle",
            "Dose Accuracy — end", "Last-dose lock-out", "Injection force (ISO 11608-1)",
        ]}},
    ])


def downgrade() -> None:
    op.drop_table("service_pricing")
    op.drop_table("platform_sheet")
    op.drop_table("reference_product_markets")
    op.drop_table("reference_products")
    op.drop_table("service_selections")
    op.drop_table("sku_rows")
    op.alter_column("requests", "status", server_default="Awaiting assignment")
    for col in ["urgency", "comment", "timeline_months", "severity", "chosen_option", "differentiated", "viscosity_val"]:
        op.drop_column("requests", col)
```

- [ ] **Step 2: Verify the migration applies cleanly against SQLite in a throwaway script**

Run:
```bash
PYTHONPATH=backend python3 -c "
from sqlalchemy import create_engine
from alembic.config import Config
from alembic import command
cfg = Config('backend/alembic.ini')
cfg.set_main_option('sqlalchemy.url', 'sqlite:///./_migration_check.db')
command.upgrade(cfg, 'head')
command.downgrade(cfg, 'base')
"
rm -f _migration_check.db
```
Expected: no errors (SQLite tolerates `sa.JSON`/`sa.Boolean`/`server_default` the same way Postgres does here).

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/0003_core_customer_flow.py
git commit -m "feat(backend): migration for core customer flow — sku_rows, service_selections, seeded reference data"
```

---

### Task 2: ORM models for the new tables

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: tables created in Task 1.
- Produces: `SkuRow`, `ServiceSelection`, `ReferenceProduct`, `ReferenceProductMarket`, `PlatformSheet`, `ServicePricing` model classes; `Request.sku_rows` relationship (ordered by `id`); `SkuRow.service_selections` relationship; `Request` gains `viscosity_val: Optional[float]`, `differentiated: bool`, `chosen_option: Optional[int]`, `severity: Optional[str]`, `timeline_months: Optional[int]`, `comment: Optional[str]`, `urgency: Optional[str]`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_models.py`:

```python
from app.models import SkuRow, ServiceSelection


def test_request_sku_rows_and_service_selections_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    org = Organization(name="Pfizer", kind="customer", domain="pfizer.com")
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email="a@pfizer.com", name="Alice", role="Customer")
    db.add(user)
    db.flush()
    req = Request(org_id=org.id, submitted_by=user.id, brand="Ozempic", market="US", status="Draft")
    db.add(req)
    db.flush()

    sku = SkuRow(request_id=req.id, strength="1 mg", cartridge="3 mL", fill_ml=3.0)
    db.add(sku)
    db.flush()
    db.add(ServiceSelection(sku_row_id=sku.id, standard_dv=True, threshold=True))
    db.commit()

    fetched = db.query(Request).one()
    assert fetched.status == "Draft"
    assert len(fetched.sku_rows) == 1
    assert fetched.sku_rows[0].strength == "1 mg"
    assert fetched.sku_rows[0].service_selections[0].threshold is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_models.py::test_request_sku_rows_and_service_selections_roundtrip -v`
Expected: FAIL — `ImportError: cannot import name 'SkuRow'`.

- [ ] **Step 3: Add the models**

In `backend/app/models.py`, change the `Request.status` default comment context and add the new columns/relationship, then append the new classes:

```python
class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_kam_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    brand: Mapped[str] = mapped_column(String(200), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    device: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Draft")
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    viscosity_val: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    differentiated: Mapped[bool] = mapped_column(nullable=False, default=False)
    chosen_option: Mapped[Optional[int]] = mapped_column(nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    timeline_months: Mapped[Optional[int]] = mapped_column(nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    urgency: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    sku_rows: Mapped[list["SkuRow"]] = relationship(back_populates="request", order_by="SkuRow.id")


class SkuRow(Base):
    __tablename__ = "sku_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    strength: Mapped[str] = mapped_column(String(50), nullable=False)
    cartridge: Mapped[str] = mapped_column(String(50), nullable=False)
    fill_ml: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    request: Mapped["Request"] = relationship(back_populates="sku_rows")
    service_selections: Mapped[list["ServiceSelection"]] = relationship(back_populates="sku_row")


class ServiceSelection(Base):
    __tablename__ = "service_selections"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_row_id: Mapped[int] = mapped_column(ForeignKey("sku_rows.id"), nullable=False)
    standard_dv: Mapped[bool] = mapped_column(nullable=False, default=True)
    threshold: Mapped[bool] = mapped_column(nullable=False, default=False)
    ifu: Mapped[bool] = mapped_column(nullable=False, default=False)
    human_factor: Mapped[bool] = mapped_column(nullable=False, default=False)

    sku_row: Mapped["SkuRow"] = relationship(back_populates="service_selections")


class ReferenceProduct(Base):
    __tablename__ = "reference_products"

    brand: Mapped[str] = mapped_column(String(100), primary_key=True)
    molecule: Mapped[str] = mapped_column(String(200), nullable=False)
    device: Mapped[str] = mapped_column(String(100), nullable=False)
    dose: Mapped[str] = mapped_column(String(20), nullable=False)
    visc: Mapped[str] = mapped_column(String(20), nullable=False)
    visc_val: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    cartridge: Mapped[str] = mapped_column(String(50), nullable=False)
    strengths: Mapped[list] = mapped_column(JSON, nullable=False)
    visc_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    mech_drive: Mapped[str] = mapped_column(String(50), nullable=False)
    mech_dose: Mapped[str] = mapped_column(String(20), nullable=False)
    mech_label: Mapped[str] = mapped_column(String(200), nullable=False)
    ob_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    ob_claims: Mapped[list] = mapped_column(JSON, nullable=False)
    presentations: Mapped[dict] = mapped_column(JSON, nullable=False)
    presentations_ref: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class ReferenceProductMarket(Base):
    __tablename__ = "reference_product_markets"

    brand: Mapped[str] = mapped_column(ForeignKey("reference_products.brand"), primary_key=True)
    market: Mapped[str] = mapped_column(String(50), primary_key=True)
    device: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mech_drive: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mech_dose: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    mech_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ob_ref: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    ob_claims: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    market_note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    presentations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    pres_ref: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)


class PlatformSheet(Base):
    __tablename__ = "platform_sheet"

    variant: Mapped[str] = mapped_column(String(100), primary_key=True)
    family: Mapped[str] = mapped_column(String(100), nullable=False)
    cls: Mapped[str] = mapped_column(String(50), nullable=False)
    sub: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    resolution: Mapped[str] = mapped_column(String(200), nullable=False)
    lockout: Mapped[str] = mapped_column(String(10), nullable=False)
    carts: Mapped[list] = mapped_column(JSON, nullable=False)
    mech: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(10), nullable=False)
    moderate: Mapped[bool] = mapped_column(nullable=False, default=False)


class ServicePricing(Base):
    __tablename__ = "service_pricing"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
```

Also update the existing `test_create_org_user_request_roundtrip` assertion in the same file — it currently asserts `fetched.status == "Awaiting assignment"`; since the ORM `default=` (used when a test constructs a `Request` without a DB-level `server_default`) now applies at flush time, change the assertion to:

```python
    assert fetched.status == "Draft"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_models.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat(backend): ORM models for sku_rows, service_selections, seeded reference data"
```

---

### Task 3: `platform_matching` service — mechanism-similarity ranking + unit tests

**Files:**
- Create: `backend/app/services/__init__.py` (empty)
- Create: `backend/app/services/platform_matching.py`
- Test: `backend/tests/test_platform_matching.py`

**Interfaces:**
- Consumes: `PlatformSheet` rows (Task 2) — reads `.cls`, `.mech`, `.resolution`, `.carts`, `.variant`.
- Produces: `rank_platforms_for_sku(cart: str, rld: dict | None, platforms: list[PlatformSheet]) -> list[dict]`, each dict `{platform: PlatformSheet, score: float|None, pct: int|None, band: str, rationale: str, fallback: bool, visc_limited: bool}`. Also exports `mechanism_similarity(rld: dict, p: PlatformSheet) -> tuple[float, str, str]` and `platform_max_visc(p: PlatformSheet) -> float` for direct unit testing.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_platform_matching.py
from app.models import PlatformSheet
from app.services import platform_matching as pm


def _platform(**kw):
    defaults = dict(variant="test", family="test", cls="Pen Injector", sub="", resolution="Fixed Dose – 80 IU",
                     lockout="Yes", carts=["3 mL"], mech="Torsion Spring", color="#000", moderate=False)
    defaults.update(kw)
    return PlatformSheet(**defaults)


WEGOVY_RLD = dict(device="Auto-Injector", mech_drive="spring_single", mech_dose="fixed", visc_val=1.6)


def test_same_archetype_drive_dose_scores_close():
    toby = _platform(variant="Toby", cls="Autoinjector", mech="2-step AI", resolution="0.2 – 2.25 mL", carts=["1 mL PFS"])
    score, band, _ = pm.mechanism_similarity(WEGOVY_RLD, toby)
    # arch differs (Auto-Injector vs Autoinjector normalise equal), drive spring_single~spring_ai=0.5, dose fixed==fixed
    assert band in ("Close", "Similar")
    assert score == pm.W_ARCH * 1.0 + pm.W_DRIVE * 0.5 + pm.W_DOSE * 1.0


def test_unrelated_drive_and_archetype_scores_divergent():
    axiom = _platform(variant="Axiom", cls="Pen Injector", mech="Push-Pull", resolution="Fixed Dose – 80 IU", carts=["3 mL"])
    score, band, _ = pm.mechanism_similarity(WEGOVY_RLD, axiom)
    assert band == "Divergent"
    assert score == pm.W_DRIVE * 0.0 + pm.W_DOSE * 1.0  # different archetype, unrelated drive, dose matches


def test_platform_max_visc_by_class():
    assert pm.platform_max_visc(_platform(cls="Pen Injector")) == 8.0
    assert pm.platform_max_visc(_platform(cls="Autoinjector", mech="2-step AI")) == 15.0
    assert pm.platform_max_visc(_platform(cls="Autoinjector", mech="2-step AI (high visc.)")) == 50.0
    assert pm.platform_max_visc(_platform(cls="On-Body", mech="On-body device")) == 50.0


def test_rank_platforms_for_sku_soft_penalises_visc_limited_platform():
    low_visc_pen = _platform(variant="Neo", cls="Pen Injector", mech="Torsion Spring", carts=["3 mL"])
    high_visc_rld = dict(device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable", visc_val=20.0)
    ranked = pm.rank_platforms_for_sku("3 mL", high_visc_rld, [low_visc_pen])
    assert ranked[0]["visc_limited"] is True
    assert ranked[0]["score"] == 1.0 * 0.5  # perfect match halved by the soft penalty


def test_rank_platforms_for_sku_filters_by_cartridge_and_orders_qualifying_before_fallback():
    close = _platform(variant="Neo", cls="Pen Injector", mech="Torsion Spring", carts=["3 mL"])
    divergent = _platform(variant="Axiom", cls="Pen Injector", mech="Push-Pull", carts=["3 mL"])
    wrong_cart = _platform(variant="Tristan", cls="Autoinjector", mech="3-step AI", carts=["1 mL PFS"])
    rld = dict(device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable", visc_val=1.5)
    ranked = pm.rank_platforms_for_sku("3 mL", rld, [close, divergent, wrong_cart])
    assert [r["platform"].variant for r in ranked] == ["Neo", "Axiom"]
    assert ranked[0]["fallback"] is False
    assert ranked[1]["fallback"] is True


def test_rank_platforms_for_sku_falls_back_to_cartridge_only_without_curated_profile():
    p = _platform(variant="Neo", carts=["3 mL"])
    ranked = pm.rank_platforms_for_sku("3 mL", None, [p])
    assert ranked == [{"platform": p, "score": None, "pct": None, "band": "n/a",
                        "rationale": "no curated mechanism profile", "fallback": False, "visc_limited": False}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_platform_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'`.

- [ ] **Step 3: Write the service module**

```python
# backend/app/services/platform_matching.py
"""Mechanism-similarity platform ranking.

Direct port of `mechanism_similarity`, `platform_max_visc`, and `rank_platforms_for_sku`
from the legacy Streamlit app's `data.py`, operating on `PlatformSheet` ORM rows instead
of dicts. Same weights, band thresholds, and drive-adjacency table as the original — see
the org-level-rebuild spec's "no change to the ranking/pricing math" constraint.
"""
from __future__ import annotations

from app.models import PlatformSheet

DRIVE_MANUAL = "manual_dial"
DRIVE_TORSION = "torsion_spring"
DRIVE_SPRING_ONE = "spring_single"
DRIVE_SPRING_AI = "spring_ai"
DRIVE_SPRING_AIHV = "spring_ai_hv"
DRIVE_ON_BODY = "on_body"

PLATFORM_MECH_DRIVE = {
    "Push-Pull": DRIVE_MANUAL, "Geared Pen": DRIVE_MANUAL,
    "Clutch Pen": DRIVE_MANUAL, "Pulley": DRIVE_MANUAL,
    "Torsion Spring": DRIVE_TORSION,
    "3-step AI": DRIVE_SPRING_AI, "2-step AI": DRIVE_SPRING_AI,
    "2-step AI (high visc.)": DRIVE_SPRING_AIHV,
    "On-body device": DRIVE_ON_BODY,
}

DRIVE_ADJACENCY = {
    frozenset((DRIVE_SPRING_AI, DRIVE_SPRING_AIHV)): 0.6,
    frozenset((DRIVE_SPRING_ONE, DRIVE_SPRING_AI)): 0.5,
    frozenset((DRIVE_SPRING_ONE, DRIVE_TORSION)): 0.4,
    frozenset((DRIVE_TORSION, DRIVE_MANUAL)): 0.2,
    frozenset((DRIVE_SPRING_ONE, DRIVE_MANUAL)): 0.2,
}

W_ARCH, W_DRIVE, W_DOSE = 0.5, 0.3, 0.2
BAND_CLOSE, BAND_SIMILAR = 0.80, 0.50


def _norm_archetype(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _dose_from_resolution(res: str) -> str:
    r = res.lower()
    if "variable" in r:
        return "variable"
    if "fixed" in r:
        return "fixed"
    return "na"


def platform_signature(p: PlatformSheet) -> dict:
    return {
        "archetype": _norm_archetype(p.cls),
        "drive": PLATFORM_MECH_DRIVE.get(p.mech, ""),
        "dose": _dose_from_resolution(p.resolution),
    }


def _drive_match(a: str, b: str) -> float:
    if a and a == b:
        return 1.0
    return DRIVE_ADJACENCY.get(frozenset((a, b)), 0.0)


def _dose_match(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if a == "na" or b == "na":
        return 0.5
    return 0.0


def mechanism_similarity(rld: dict, p: PlatformSheet):
    """Return (score 0..1, band, rationale) comparing an RLD profile to a platform."""
    sig = platform_signature(p)
    arch = 1.0 if _norm_archetype(rld["device"]) == sig["archetype"] else 0.0
    drv = _drive_match(rld.get("mech_drive", ""), sig["drive"])
    dose = _dose_match(rld.get("mech_dose", ""), sig["dose"])
    score = W_ARCH * arch + W_DRIVE * drv + W_DOSE * dose
    band = "Close" if score >= BAND_CLOSE else "Similar" if score >= BAND_SIMILAR else "Divergent"
    parts = [
        "same archetype" if arch else "different archetype",
        "same drive" if drv == 1.0 else "related drive" if drv > 0 else "unrelated drive",
        "dose match" if dose == 1.0 else "dose n/a" if dose == 0.5 else "dose differs",
    ]
    return score, band, "; ".join(parts)


def platform_max_visc(p: PlatformSheet) -> float:
    if "high visc" in p.mech.lower():
        return 50.0
    if p.cls == "On-Body":
        return 50.0
    if p.cls == "Pen Injector":
        return 8.0
    return 15.0


def rank_platforms_for_sku(cart: str, rld: dict | None, platforms: list[PlatformSheet]) -> list[dict]:
    """Cartridge-compatible platforms ranked by mechanism closeness, viscosity-aware.

    Hard filter: Close/Similar first (sorted by score). Fallback: Divergent platforms
    appended (tagged fallback=True). Platforms whose viscosity capability is below the
    RLD's viscosity get a soft score penalty (not hidden) and a visc_limited flag. If
    rld has no curated profile, fall back to cartridge-only order with band 'n/a'.
    """
    comp = [p for p in platforms if cart in (p.carts or [])]
    if not rld or not rld.get("mech_drive"):
        return [{"platform": p, "score": None, "pct": None, "band": "n/a",
                 "rationale": "no curated mechanism profile", "fallback": False, "visc_limited": False}
                for p in comp]
    visc = rld.get("visc_val")
    scored = []
    for p in comp:
        s, _band, why = mechanism_similarity(rld, p)
        cap = platform_max_visc(p)
        visc_limited = bool(visc and visc > cap)
        if visc_limited:
            s *= 0.5
            why += f"; viscosity {visc} cP exceeds platform capability (~{cap:.0f} cP)"
        band = "Close" if s >= BAND_CLOSE else "Similar" if s >= BAND_SIMILAR else "Divergent"
        scored.append({"platform": p, "score": s, "pct": round(s * 100), "band": band,
                        "rationale": why, "fallback": band == "Divergent", "visc_limited": visc_limited})
    qualifying = sorted((x for x in scored if x["band"] != "Divergent"), key=lambda x: -x["score"])
    fallback = sorted((x for x in scored if x["band"] == "Divergent"), key=lambda x: -x["score"])
    return qualifying + fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_platform_matching.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/platform_matching.py backend/tests/test_platform_matching.py
git commit -m "feat(backend): port mechanism-similarity platform ranking as platform_matching service"
```

---

### Task 4: `reference_data` service — RLD merge + presentation lookup

**Files:**
- Create: `backend/app/services/reference_data.py`
- Test: `backend/tests/test_reference_data.py`

**Interfaces:**
- Consumes: `ReferenceProduct`, `ReferenceProductMarket` rows (Task 2).
- Produces: `variants_for(db: Session, brand: str, market: str) -> dict | None` (keys: `brand, molecule, device, dose, visc, visc_val, cartridge, strengths, visc_ref, mech_drive, mech_dose, mech_label, ob_ref, ob_claims, market_note`); `presentation_for(db: Session, brand: str, strength: str, market: str, default_cart: str = "3 mL") -> tuple[str, float, str]` (cartridge, fill_ml, citation).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_reference_data.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ReferenceProduct, ReferenceProductMarket
from app.services import reference_data as rd


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(ReferenceProduct(
        brand="Wegovy", molecule="Semaglutide", device="Auto-Injector", dose="fixed", visc="water",
        visc_val=1.6, cartridge="1 mL PFS", strengths=["0.25 mg", "1.7 mg"], visc_ref="ref",
        mech_drive="spring_single", mech_dose="fixed", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"0.25 mg": ["1 mL PFS", 0.5], "1.7 mg": ["1 mL PFS", 0.75]}, presentations_ref="pref",
    ))
    session.add(ReferenceProductMarket(
        brand="Wegovy", market="EU", device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable",
        mech_label="EU label", ob_ref="EU ob", ob_claims=["EU c"], market_note="Multi-dose pen",
        presentations={"0.25 mg": ["1.5 mL", 1.5]}, pres_ref="EU pref",
    ))
    session.commit()
    yield session
    session.close()


def test_variants_for_unknown_brand_returns_none(db):
    assert rd.variants_for(db, "Nope", "US") is None


def test_variants_for_us_uses_base_profile_with_empty_market_note(db):
    v = rd.variants_for(db, "Wegovy", "US")
    assert v["device"] == "Auto-Injector"
    assert v["mech_drive"] == "spring_single"
    assert v["market_note"] == ""


def test_variants_for_eu_merges_override_over_base(db):
    v = rd.variants_for(db, "Wegovy", "EU")
    assert v["device"] == "Pen Injector"
    assert v["mech_drive"] == "torsion_spring"
    assert v["molecule"] == "Semaglutide"  # non-overridden field falls through from base
    assert v["market_note"] == "Multi-dose pen"


def test_presentation_for_us_uses_base_presentations(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "0.25 mg", "US")
    assert (cart, fill, ref) == ("1 mL PFS", 0.5, "pref")


def test_presentation_for_eu_prefers_market_override(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "0.25 mg", "EU")
    assert (cart, fill, ref) == ("1.5 mL", 1.5, "EU pref")


def test_presentation_for_eu_falls_back_to_base_when_strength_not_overridden(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "1.7 mg", "EU")
    assert (cart, fill, ref) == ("1 mL PFS", 0.75, "pref")


def test_presentation_for_unknown_strength_uses_default(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "9 mg", "US", default_cart="3 mL")
    assert (cart, fill, ref) == ("3 mL", 1.5, "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_reference_data.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the service module**

```python
# backend/app/services/reference_data.py
"""Reference-product lookups backing the request wizard.

Ports `variants_for` and `presentation_for` from the legacy app's data.py onto the
seeded `reference_products` / `reference_product_markets` tables (Task 1 migration).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ReferenceProduct, ReferenceProductMarket

_OVERRIDABLE = ["device", "mech_drive", "mech_dose", "mech_label", "ob_ref", "ob_claims"]


def variants_for(db: Session, brand: str, market: str) -> dict | None:
    """Effective RLD profile for a (brand, market): base merged with any market override."""
    base = db.get(ReferenceProduct, brand)
    if base is None:
        return None
    eff = {
        "brand": base.brand, "molecule": base.molecule, "device": base.device,
        "dose": base.dose, "visc": base.visc, "visc_val": float(base.visc_val),
        "cartridge": base.cartridge, "strengths": base.strengths, "visc_ref": base.visc_ref,
        "mech_drive": base.mech_drive, "mech_dose": base.mech_dose, "mech_label": base.mech_label,
        "ob_ref": base.ob_ref, "ob_claims": base.ob_claims,
    }
    ov = db.get(ReferenceProductMarket, (brand, market))
    if ov is not None:
        for key in _OVERRIDABLE:
            val = getattr(ov, key)
            if val:
                eff[key] = val
    eff["market_note"] = (ov.market_note or "") if ov is not None else ""
    return eff


def presentation_for(db: Session, brand: str, strength: str, market: str, default_cart: str = "3 mL"):
    """Return (cartridge, fill_mL, citation) for an RLD SKU, market-aware.

    A (brand, market) override wins for the strengths it covers; else the base
    presentations apply; else (default_cart, 1.5, "") for an unknown brand/strength.
    """
    ov = db.get(ReferenceProductMarket, (brand, market))
    if ov is not None and ov.presentations and strength in ov.presentations:
        cart, fill = ov.presentations[strength]
        return cart, fill, ov.pres_ref or ""
    base = db.get(ReferenceProduct, brand)
    presentations = base.presentations if base else {}
    if strength in presentations:
        cart, fill = presentations[strength]
        return cart, fill, base.presentations_ref
    return default_cart, 1.5, ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_reference_data.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reference_data.py backend/tests/test_reference_data.py
git commit -m "feat(backend): reference-product RLD merge and presentation lookup service"
```

---

### Task 5: Wizard schemas

**Files:**
- Modify: `backend/app/schemas.py`

**Interfaces:**
- Produces: `SkuRowIn`, `SkuRowOut`, `ServiceSelectionIn`, `ServiceSelectionOut`, `ServicesUpdate`, `SelectOptionRequest`, `PlatformOptionRow`, `PlatformOptionsOut`, `ReferenceProductOut`, `RequestStep1Update`; extends `RequestCreate` and `RequestOut`; adds `RequestDetailOut(RequestOut)`.

- [ ] **Step 1: Add the schemas**

In `backend/app/schemas.py`, add near the top:

```python
CART_SIZES = ["1.5 mL", "3 mL", "1 mL PFS", "3 mL PFS", "1 mL Bespoke"]
```

Replace `RequestCreate` with:

```python
class RequestCreate(BaseModel):
    brand: str
    market: str
    strengths: list[str] = []
    viscosity_val: Optional[float] = None
    device: Optional[str] = None
    differentiated: bool = False
    total: float = 0
```

Add after it (before `RequestOut`):

```python
class SkuRowIn(BaseModel):
    strength: str
    cartridge: str
    fill_ml: float

    @field_validator("cartridge")
    @classmethod
    def cartridge_must_be_known_size(cls, v: str) -> str:
        if v not in CART_SIZES:
            raise ValueError(f"cartridge must be one of {CART_SIZES}")
        return v

    @field_validator("fill_ml")
    @classmethod
    def fill_ml_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("fill_ml must be greater than 0")
        return v


class SkuRowOut(BaseModel):
    id: int
    strength: str
    cartridge: str
    fill_ml: float


class RequestStep1Update(BaseModel):
    brand: str
    market: str
    strengths: list[str]
    viscosity_val: Optional[float] = None
    device: Optional[str] = None
    differentiated: bool = False
    sku_rows: list[SkuRowIn]


class ServiceSelectionIn(BaseModel):
    sku_row_id: int
    standard_dv: bool = True
    threshold: bool = False
    ifu: bool = False
    human_factor: bool = False


class ServiceSelectionOut(BaseModel):
    id: int
    sku_row_id: int
    standard_dv: bool
    threshold: bool
    ifu: bool
    human_factor: bool


class ServicesUpdate(BaseModel):
    selections: list[ServiceSelectionIn]
    comment: Optional[str] = None
    urgency: Optional[str] = None


class SelectOptionRequest(BaseModel):
    chosen_option: int = Field(ge=1, le=3)


class PlatformOptionRow(BaseModel):
    sku: str
    cartridge: str
    platform: Optional[str] = None
    cls: Optional[str] = None
    sub: Optional[str] = None
    resolution: Optional[str] = None
    lockout: Optional[str] = None
    mech: Optional[str] = None
    band: str
    pct: Optional[int] = None
    fallback: bool
    visc_limited: bool


class PlatformOptionsOut(BaseModel):
    options: dict[str, list[PlatformOptionRow]]


class ReferenceProductOut(BaseModel):
    brand: str
    molecule: str
    device: str
    strengths: list[str]
    visc_val: float
    visc_ref: str
    cartridge: str
```

Replace `RequestOut` with (adds the new flat fields; existing fields unchanged):

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


class RequestDetailOut(RequestOut):
    sku_rows: list[SkuRowOut] = []
    service_selections: list[ServiceSelectionOut] = []
```

Add `field_validator` and `Field` to the top-of-file import:

```python
from pydantic import BaseModel, EmailStr, Field, field_validator
```

- [ ] **Step 2: Sanity-check schema import**

Run: `PYTHONPATH=backend backend/.venv/bin/python -c "from app import schemas; print(schemas.RequestDetailOut.model_fields.keys())"`
Expected: prints a field list including `sku_rows` and `service_selections`, no import error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(backend): request-wizard Pydantic schemas"
```

---

### Task 6: `GET /reference-products` endpoint

**Files:**
- Create: `backend/app/routers/reference_products.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_reference_products.py`

**Interfaces:**
- Consumes: `ReferenceProduct` model (Task 2), `ReferenceProductOut` schema (Task 5).
- Produces: `GET /reference-products` — any authenticated user, returns `list[ReferenceProductOut]` sorted by brand.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_reference_products.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db
from app.models import ReferenceProduct


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg", "1 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={}, presentations_ref="",
    ))
    session.commit()
    session.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={"name": "Anaya", "email": email})
    return resp.json()["access_token"]


def test_reference_products_requires_auth(client):
    assert client.get("/reference-products").status_code == 401


def test_reference_products_lists_seeded_brands(client):
    token = _login(client)
    resp = client.get("/reference-products", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{
        "brand": "Ozempic", "molecule": "Semaglutide", "device": "Pen Injector",
        "strengths": ["0.25 mg", "1 mg"], "visc_val": 1.4, "visc_ref": "ref", "cartridge": "3 mL",
    }]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_reference_products.py -v`
Expected: FAIL — 404 (route doesn't exist).

- [ ] **Step 3: Write the router**

```python
# backend/app/routers/reference_products.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ReferenceProduct, User
from app.schemas import ReferenceProductOut

router = APIRouter(tags=["reference-products"])


@router.get("/reference-products", response_model=list[ReferenceProductOut])
def list_reference_products(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    products = db.query(ReferenceProduct).order_by(ReferenceProduct.brand).all()
    return [
        ReferenceProductOut(
            brand=p.brand, molecule=p.molecule, device=p.device, strengths=p.strengths,
            visc_val=float(p.visc_val), visc_ref=p.visc_ref, cartridge=p.cartridge,
        )
        for p in products
    ]
```

Wire it into `backend/app/main.py` — add after the `kams_router` include:

```python
from app.routers.reference_products import router as reference_products_router
app.include_router(reference_products_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_reference_products.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/reference_products.py backend/app/main.py backend/tests/test_reference_products.py
git commit -m "feat(backend): GET /reference-products endpoint"
```

---

### Task 7: `POST /requests` (extended) + `GET /requests/{id}` + fix existing tests for the Draft default

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/tests/test_requests.py`
- Modify: `backend/tests/test_dashboard.py`

**Interfaces:**
- Consumes: `reference_data.variants_for`/`presentation_for` (Task 4), `RequestCreate`/`RequestDetailOut` (Task 5).
- Produces: `serialize_requests(db, reqs, include_routing) -> list[RequestOut]` now also populates the new flat fields; new helper `_serialize_detail(db, req, include_routing=False) -> RequestDetailOut`; new helpers `_owned_request_or_404(db, request_id, user) -> Request` and `_owned_draft_or_404(db, request_id, user) -> Request`, used by every later task in this router; `POST /requests` returns `RequestDetailOut` (status 201); `GET /requests/{id}` returns `RequestDetailOut`, role-scoped like `list_requests`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_requests.py`:

```python
def test_create_request_defaults_to_draft_status(client):
    token, _ = _login(client, "anaya@pfizer.com")
    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "Draft"
    assert resp.json()["sku_rows"] == []


def test_create_request_with_strengths_seeds_sku_rows_from_reference_data(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                        headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert len(body["sku_rows"]) == 1
    assert body["sku_rows"][0] == {"id": body["sku_rows"][0]["id"], "strength": "1 mg", "cartridge": "3 mL", "fill_ml": 3.0}


def test_get_request_detail_not_found_for_non_owner_customer(client):
    token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 404


def test_get_request_detail_visible_to_bd_manager_and_assigned_kam(client):
    token, _ = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()

    assert client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200

    not_assigned = client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {kam_token}"})
    assert not_assigned.status_code == 404

    client.post(f"/requests/{created['id']}/assign-kam", json={"kam_user_id": kam_user["id"]},
                headers={"Authorization": f"Bearer {mgr_token}"})
    assigned = client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {kam_token}"})
    assert assigned.status_code == 200
```

Add a `seed_reference_product` fixture near the top of `backend/tests/test_requests.py` (after the `client` fixture) that other tasks' tests will also reuse:

```python
@pytest.fixture
def seed_reference_product(client):
    from app.db import get_db
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg", "0.5 mg", "1 mg", "2 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"0.25 mg": ["1.5 mL", 1.5], "0.5 mg": ["1.5 mL", 1.5], "1 mg": ["3 mL", 3.0], "2 mg": ["3 mL", 3.0]},
        presentations_ref="pref",
    ))
    db.commit()
    db.close()
```

(This needs `app` imported in the test file — add `from app.main import app` alongside the existing imports if not already present via `from app.main import app` at top; it already is, per the existing `client` fixture.)

Update the existing `test_create_and_list_request` assertion — `status` is now `"Draft"` on creation:

```python
def test_create_and_list_request(client):
    token, _ = _login(client, "anaya@pfizer.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "Draft"

    resp = client.get("/requests", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
```

Update `backend/tests/test_dashboard.py`'s `test_metrics_returns_seeded_payload_and_live_counts` — the created request is now a Draft, not "Awaiting assignment":

```python
    assert body["live"]["requests_by_status"] == {"Draft": 1}
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_requests.py backend/tests/test_dashboard.py -v`
Expected: the new tests FAIL (404 on `/requests/{id}` GET, `status` still `"Awaiting assignment"`); the two edited assertions FAIL for the same reason.

- [ ] **Step 3: Rewrite `backend/app/routers/requests.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Organization, OrgKamMap, Request, SkuRow, User
from app.schemas import RequestCreate, RequestDetailOut, RequestOut, ServiceSelectionOut, SkuRowOut
from app.services import reference_data

router = APIRouter(prefix="/requests", tags=["requests"])


def serialize_requests(db: Session, reqs: list[Request], include_routing: bool = False) -> list[RequestOut]:
    if not reqs:
        return []
    org_ids = {r.org_id for r in reqs}
    orgs = {o.id: o.name for o in db.query(Organization).filter(Organization.id.in_(org_ids))}
    org_kam = {m.org_id: m.kam_user_id for m in db.query(OrgKamMap).filter(OrgKamMap.org_id.in_(org_ids))}

    kam_ids = {r.assigned_kam_id for r in reqs if r.assigned_kam_id} | set(org_kam.values())
    kam_names = {u.id: u.name for u in db.query(User).filter(User.id.in_(kam_ids))} if kam_ids else {}

    out = []
    for r in reqs:
        suggested_id = org_kam.get(r.org_id) if include_routing else None
        out.append(RequestOut(
            id=r.id, org_id=r.org_id, org_name=orgs.get(r.org_id, ""),
            submitted_by=r.submitted_by, brand=r.brand, market=r.market, device=r.device,
            status=r.status, total=r.total,
            assigned_kam_id=r.assigned_kam_id,
            assigned_kam_name=kam_names.get(r.assigned_kam_id) if r.assigned_kam_id else None,
            suggested_kam_id=suggested_id,
            suggested_kam_name=kam_names.get(suggested_id) if suggested_id else None,
            viscosity_val=float(r.viscosity_val) if r.viscosity_val is not None else None,
            differentiated=r.differentiated,
            chosen_option=r.chosen_option,
            severity=r.severity,
            timeline_months=r.timeline_months,
            comment=r.comment,
            urgency=r.urgency,
        ))
    return out


def _serialize_detail(db: Session, req: Request, include_routing: bool = False) -> RequestDetailOut:
    base = serialize_requests(db, [req], include_routing=include_routing)[0]
    selections = [sel for row in req.sku_rows for sel in row.service_selections]
    return RequestDetailOut(
        **base.model_dump(),
        sku_rows=[SkuRowOut(id=r.id, strength=r.strength, cartridge=r.cartridge, fill_ml=float(r.fill_ml))
                  for r in req.sku_rows],
        service_selections=[
            ServiceSelectionOut(id=s.id, sku_row_id=s.sku_row_id, standard_dv=s.standard_dv,
                                 threshold=s.threshold, ifu=s.ifu, human_factor=s.human_factor)
            for s in selections
        ],
    )


def _owned_request_or_404(db: Session, request_id: int, user: User) -> Request:
    req = db.get(Request, request_id)
    if req is None or req.submitted_by != user.id:
        raise HTTPException(404, "Request not found")
    return req


def _owned_draft_or_404(db: Session, request_id: int, user: User) -> Request:
    req = _owned_request_or_404(db, request_id, user)
    if req.status != "Draft":
        raise HTTPException(409, "This request is no longer a draft")
    return req


@router.post("", response_model=RequestDetailOut, status_code=201)
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    req = Request(org_id=current_user.org_id, submitted_by=current_user.id,
                   brand=payload.brand, market=payload.market, device=payload.device,
                   viscosity_val=payload.viscosity_val, differentiated=payload.differentiated,
                   status="Draft", total=payload.total)
    db.add(req)
    db.flush()

    ref = reference_data.variants_for(db, payload.brand, payload.market)
    default_cart = ref["cartridge"] if ref else "3 mL"
    for strength in payload.strengths:
        cart, fill, _ = reference_data.presentation_for(db, payload.brand, strength, payload.market, default_cart)
        db.add(SkuRow(request_id=req.id, strength=strength, cartridge=cart, fill_ml=fill))

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


@router.get("", response_model=list[RequestOut])
def list_requests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Request)
    include_routing = False
    if current_user.role == "BD Manager":
        q = q.filter(Request.org_id != current_user.org_id)
        include_routing = True
    elif current_user.role == "Key Account Manager":
        q = q.filter(Request.assigned_kam_id == current_user.id)
        include_routing = True
    else:
        q = q.filter(Request.org_id == current_user.org_id)
    reqs = q.order_by(Request.created_at.desc()).all()
    return serialize_requests(db, reqs, include_routing=include_routing)


def _visible_or_404(db: Session, request_id: int, user: User) -> tuple[Request, bool]:
    """Role-scoped visibility matching list_requests; returns (request, include_routing)."""
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    if user.role == "BD Manager":
        allowed, include_routing = req.org_id != user.org_id, True
    elif user.role == "Key Account Manager":
        allowed, include_routing = req.assigned_kam_id == user.id, True
    else:
        allowed, include_routing = req.org_id == user.org_id, False
    if not allowed:
        raise HTTPException(404, "Request not found")
    return req, include_routing


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request_detail(request_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    req, include_routing = _visible_or_404(db, request_id, current_user)
    return _serialize_detail(db, req, include_routing=include_routing)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_requests.py backend/tests/test_dashboard.py backend/tests/test_kams.py -v`
Expected: PASS — including the pre-existing tests in `test_kams.py`/`test_requests.py`/`test_dashboard.py` that this change touches indirectly (`assign_kam` calls `serialize_requests`, unaffected in shape).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_requests.py backend/tests/test_dashboard.py
git commit -m "feat(backend): extend POST /requests, add GET /requests/{id}, default status to Draft"
```

---

### Task 8: `PUT /requests/{id}` — step-1 edit with upsert-by-strength and RLD-change cascade

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/tests/test_requests.py`

**Interfaces:**
- Consumes: `_owned_draft_or_404`, `_serialize_detail` (Task 7); `RequestStep1Update`, `SkuRowIn` (Task 5).
- Produces: `PUT /requests/{id}` → `RequestDetailOut`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_requests.py`:

```python
def test_put_request_step1_upserts_sku_rows_and_computes_total_fields(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["1 mg", "2 mg"], "viscosity_val": 1.4,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [
            {"strength": "1 mg", "cartridge": "1.5 mL", "fill_ml": 2.0},  # edited cartridge/fill, id preserved
            {"strength": "2 mg", "cartridge": "3 mL", "fill_ml": 3.0},    # new row
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    rows_by_strength = {r["strength"]: r for r in body["sku_rows"]}
    assert rows_by_strength["1 mg"]["id"] == created["sku_rows"][0]["id"]
    assert rows_by_strength["1 mg"]["cartridge"] == "1.5 mL"
    assert rows_by_strength["2 mg"]["fill_ml"] == 3.0


def test_put_request_step1_preserves_service_selections_when_strengths_unchanged(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"}, json={
        "selections": [{"sku_row_id": sku_id, "standard_dv": True, "threshold": True}],
    })

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["1 mg"], "viscosity_val": 1.4,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [{"strength": "1 mg", "cartridge": "1 mL PFS", "fill_ml": 0.75}],  # only cartridge/fill changed
    })
    body = resp.json()
    assert body["chosen_option"] == 1  # not reset — strengths didn't change
    assert len(body["service_selections"]) == 1


def test_put_request_step1_cascades_reset_when_strengths_change(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"}, json={
        "selections": [{"sku_row_id": sku_id, "standard_dv": True}],
    })

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["2 mg"], "viscosity_val": 1.4,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [{"strength": "2 mg", "cartridge": "3 mL", "fill_ml": 3.0}],
    })
    body = resp.json()
    assert body["chosen_option"] is None
    assert body["severity"] is None
    assert body["service_selections"] == []


def test_put_request_step1_rejects_unknown_cartridge(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["1 mg"], "sku_rows": [
            {"strength": "1 mg", "cartridge": "9 mL bogus", "fill_ml": 3.0},
        ],
    })
    assert resp.status_code == 422


def test_put_request_returns_404_for_non_owner(client):
    token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {other_token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": [], "sku_rows": [],
    })
    assert resp.status_code == 404


def test_put_request_returns_409_when_not_draft(client):
    token, _ = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
               json={"selections": []})
    client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": [], "sku_rows": [],
    })
    assert resp.status_code == 409
```

(These last two tests reference `select-option`/`services`/`submit` endpoints landing in Tasks 9–10 — leave them here now, marked `xfail` isn't needed since the whole task set lands together before this task's commit per the plan's execution order below; see Step 2's expected failures for the ones this task's own code covers.)

- [ ] **Step 2: Run test to verify the core one fails**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_requests.py::test_put_request_step1_upserts_sku_rows_and_computes_total_fields -v`
Expected: FAIL — 405 Method Not Allowed (no `PUT` route yet).

- [ ] **Step 3: Add the endpoint**

Add to `backend/app/routers/requests.py` (needs `RequestStep1Update` and `ServiceSelection` imported — update the top imports to `from app.models import Organization, OrgKamMap, Request, ServiceSelection, SkuRow, User` and `from app.schemas import RequestCreate, RequestDetailOut, RequestOut, RequestStep1Update, ServiceSelectionOut, SkuRowOut`):

```python
def _upsert_sku_rows(db: Session, req: Request, rows_in: list) -> bool:
    """Upsert req.sku_rows by strength; returns True if the strength set changed.

    Preserves sku_rows.id (and therefore service_selections) for any strength that's
    still present, so an edit that only tweaks cartridge/fill_ml doesn't orphan an
    already-priced SKU's service selections. See the plan's "implementation decisions"
    note on reconciling the full-replace contract with the service_selections FK.
    """
    existing = {row.strength: row for row in req.sku_rows}
    incoming_strengths = {r.strength for r in rows_in}
    changed = set(existing.keys()) != incoming_strengths

    for strength, row in list(existing.items()):
        if strength not in incoming_strengths:
            db.query(ServiceSelection).filter(ServiceSelection.sku_row_id == row.id).delete()
            db.delete(row)
    db.flush()

    for r in rows_in:
        row = existing.get(r.strength)
        if row is not None and r.strength in incoming_strengths:
            row.cartridge = r.cartridge
            row.fill_ml = r.fill_ml
        else:
            db.add(SkuRow(request_id=req.id, strength=r.strength, cartridge=r.cartridge, fill_ml=r.fill_ml))
    return changed


@router.put("/{request_id}", response_model=RequestDetailOut)
def update_request_step1(request_id: int, payload: RequestStep1Update, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)

    rld_changed = (req.brand != payload.brand or req.market != payload.market
                   or _upsert_sku_rows(db, req, payload.sku_rows))

    req.brand = payload.brand
    req.market = payload.market
    req.viscosity_val = payload.viscosity_val
    req.device = payload.device
    req.differentiated = payload.differentiated

    if rld_changed:
        req.chosen_option = None
        req.severity = None
        req.timeline_months = None

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)
```

Note `_upsert_sku_rows` is called before the brand/market fields are overwritten so `rld_changed` can compare old vs. new brand/market; the strength-set comparison happens inside `_upsert_sku_rows` against `req.sku_rows` as loaded (SQLAlchemy hasn't flushed the new brand/market yet at that point, so this ordering is safe either way — sku_rows aren't keyed by brand/market).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_requests.py -v -k put_request`
Expected: `test_put_request_step1_upserts...`, `..._preserves_service_selections...`, `..._rejects_unknown_cartridge`, and `..._returns_404_for_non_owner` PASS now. `..._cascades_reset...` and `..._returns_409_when_not_draft` still FAIL (need Tasks 9–10's endpoints) — confirm the failure is a 404/405 on `/select-option` or `/services`, not an error in this task's own code.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_requests.py
git commit -m "feat(backend): PUT /requests/{id} step-1 edit with upsert-by-strength cascade"
```

---

### Task 9: `GET /requests/{id}/platform-options` + `POST /requests/{id}/select-option`

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/tests/test_requests.py`

**Interfaces:**
- Consumes: `platform_matching.rank_platforms_for_sku` (Task 3), `reference_data.variants_for` (Task 4), `PlatformOptionsOut`/`PlatformOptionRow`/`SelectOptionRequest` (Task 5).
- Produces: shared helper `_scoring_rld(db, req) -> dict | None` and `_option_tables(db, req) -> dict[int, list[PlatformOptionRow]]`, reused by Task 10; `GET /requests/{id}/platform-options` → `PlatformOptionsOut`; `POST /requests/{id}/select-option` → `RequestDetailOut`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_requests.py` — needs a seeded platform, so extend the `seed_reference_product` fixture into a combined fixture (rename usages accordingly is unnecessary; just add a second fixture):

```python
@pytest.fixture
def seed_platform_sheet(client):
    from app.db import get_db
    from app.models import PlatformSheet
    db = next(app.dependency_overrides[get_db]())
    db.add(PlatformSheet(variant="Neo (3 mL)", family="Neo", cls="Pen Injector", sub="Disposable",
                          resolution="Fixed Dose – 80 IU", lockout="Yes", carts=["3 mL"],
                          mech="Torsion Spring", color="#7DB343", moderate=False))
    db.add(PlatformSheet(variant="Axiom", family="Axiom", cls="Pen Injector", sub="Disposable",
                          resolution="Fixed Dose – 80 IU", lockout="Yes", carts=["3 mL"],
                          mech="Push-Pull", color="#8FBF52", moderate=False))
    db.commit()
    db.close()


def test_get_platform_options_ranks_by_mechanism_closeness(client, seed_reference_product, seed_platform_sheet):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()

    resp = client.get(f"/requests/{created['id']}/platform-options", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    options = resp.json()["options"]
    assert options["1"][0]["platform"] == "Neo (3 mL)"  # torsion-spring pen closest to Ozempic's RLD
    assert options["1"][0]["band"] == "Close"


def test_get_platform_options_422_without_sku_rows(client, seed_reference_product, seed_platform_sheet):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.get(f"/requests/{created['id']}/platform-options", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_select_option_persists_choice(client, seed_reference_product, seed_platform_sheet):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 2},
                        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["chosen_option"] == 2


def test_select_option_rejects_out_of_range(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 4},
                        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_requests.py -v -k "platform_options or select_option"`
Expected: FAIL — 405 on both new routes.

- [ ] **Step 3: Add the endpoints**

Add to `backend/app/routers/requests.py` (add `PlatformSheet` to the `app.models` import, and `PlatformOptionRow, PlatformOptionsOut, SelectOptionRequest` to the `app.schemas` import, and `from app.services import platform_matching, reference_data`):

```python
def _scoring_rld(db: Session, req: Request) -> dict | None:
    """Market-effective RLD profile, honouring a differentiated-device override."""
    rld = reference_data.variants_for(db, req.brand, req.market)
    if rld is None:
        return None
    if req.differentiated and req.device:
        rld = dict(rld)
        rld["device"] = req.device
    return rld


def _option_tables(db: Session, req: Request) -> dict[int, list[PlatformOptionRow]]:
    """{1,2,3} -> per-SKU row at that rank, mirroring the legacy app's _option_tables."""
    rld = _scoring_rld(db, req)
    platforms = db.query(PlatformSheet).all()
    ranked_by_sku = {
        row.strength: platform_matching.rank_platforms_for_sku(row.cartridge, rld, platforms)
        for row in req.sku_rows
    }
    tables: dict[int, list[PlatformOptionRow]] = {1: [], 2: [], 3: []}
    for opt in range(3):
        for row in req.sku_rows:
            ranked = ranked_by_sku[row.strength]
            item = ranked[opt] if opt < len(ranked) else None
            p = item["platform"] if item else None
            tables[opt + 1].append(PlatformOptionRow(
                sku=row.strength, cartridge=row.cartridge,
                platform=p.variant if p else None,
                cls=p.cls if p else None, sub=(p.sub or None) if p else None,
                resolution=p.resolution if p else None, lockout=p.lockout if p else None,
                mech=p.mech if p else None,
                band=item["band"] if item else "n/a",
                pct=item["pct"] if item else None,
                fallback=bool(item and item["fallback"]),
                visc_limited=bool(item and item["visc_limited"]),
            ))
    return tables


@router.get("/{request_id}/platform-options", response_model=PlatformOptionsOut)
def get_platform_options(request_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    req = _owned_request_or_404(db, request_id, current_user)
    if not req.sku_rows:
        raise HTTPException(422, "Add at least one SKU on step 1 before viewing platform options")
    tables = _option_tables(db, req)
    return PlatformOptionsOut(options={str(k): v for k, v in tables.items()})


@router.post("/{request_id}/select-option", response_model=RequestDetailOut)
def select_option(request_id: int, payload: SelectOptionRequest, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)
    req.chosen_option = payload.chosen_option
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_requests.py -v`
Expected: PASS for every test except `..._cascades_reset...` and `..._returns_409_when_not_draft` (still waiting on Task 10's `/services` and `/submit`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_requests.py
git commit -m "feat(backend): GET platform-options and POST select-option endpoints"
```

---

### Task 10: `PUT /requests/{id}/services` (severity + pricing) + `POST /requests/{id}/submit`

**Files:**
- Modify: `backend/app/routers/requests.py`
- Modify: `backend/tests/test_requests.py`

**Interfaces:**
- Consumes: `_option_tables` (Task 9), `ServicePricing` model (Task 2), `ServicesUpdate`/`ServiceSelectionIn` (Task 5).
- Produces: `PUT /requests/{id}/services` → `RequestDetailOut`; `POST /requests/{id}/submit` → `RequestDetailOut`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_requests.py`:

```python
@pytest.fixture
def seed_service_pricing(client):
    from app.db import get_db
    from app.models import ServicePricing
    db = next(app.dependency_overrides[get_db]())
    db.add(ServicePricing(key="PKG", payload={"minor": 200, "moderate": 250, "major": 350}))
    db.add(ServicePricing(key="ADD_DV", payload={"value": 50}))
    db.add(ServicePricing(key="TIMELINE", payload={"minor": 3, "moderate": 6, "major": 9}))
    db.add(ServicePricing(key="SERVICES", payload={"standard_dv": 200, "threshold": 2110, "ifu": 1110, "human_factor": 400000}))
    db.commit()
    db.close()


def test_update_services_computes_minor_severity_pricing(
    client, seed_reference_product, seed_platform_sheet, seed_service_pricing,
):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]

    resp = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"}, json={
        "selections": [{"sku_row_id": sku_id, "standard_dv": True, "threshold": True}],
        "comment": "Bracket into one DV.", "urgency": "Level 1 · call back today",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "minor"          # Neo (torsion-spring pen) is a Close match, not moderate/fallback
    assert body["timeline_months"] == 3
    assert body["total"] == 200_000 + 2110       # 1 DV package (minor lead, no extra SKUs) + 1 threshold
    assert body["comment"] == "Bracket into one DV."


def test_update_services_escalates_severity_for_moderate_platform(
    client, seed_reference_product, seed_service_pricing,
):
    from app.db import get_db
    from app.models import PlatformSheet
    db = next(app.dependency_overrides[get_db]())
    db.add(PlatformSheet(variant="Maxim (Reusable)", family="Maxim", cls="Pen Injector", sub="Reusable",
                          resolution="Fixed Dose – 80 IU", lockout="Yes", carts=["3 mL"],
                          mech="Pulley", color="#2F6E97", moderate=True))
    db.commit()
    db.close()

    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]

    resp = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
                       json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    assert resp.json()["severity"] == "moderate"


def test_update_services_409_before_option_selected(client, seed_reference_product, seed_service_pricing):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    sku_id = created["sku_rows"][0]["id"]
    resp = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
                       json={"selections": [{"sku_row_id": sku_id}]})
    assert resp.status_code == 409


def test_submit_requires_option_and_services(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_submit_flips_status_and_locks_further_edits(
    client, seed_reference_product, seed_platform_sheet, seed_service_pricing,
):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})

    resp = client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "Awaiting assignment"

    locked = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
                         json={"selections": []})
    assert locked.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest backend/tests/test_requests.py -v -k "update_services or submit"`
Expected: FAIL — 405 on both routes.

- [ ] **Step 3: Add the endpoints**

Add to `backend/app/routers/requests.py` (add `ServicePricing` to the `app.models` import, and `ServicesUpdate` to the `app.schemas` import):

```python
@router.put("/{request_id}/services", response_model=RequestDetailOut)
def update_services(request_id: int, payload: ServicesUpdate, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)
    if req.chosen_option is None:
        raise HTTPException(409, "Select a platform option before configuring services")

    sku_row_ids = {r.id for r in req.sku_rows}
    for sel in payload.selections:
        if sel.sku_row_id not in sku_row_ids:
            raise HTTPException(422, f"sku_row_id {sel.sku_row_id} does not belong to this request")

    chosen_rows = _option_tables(db, req)[req.chosen_option]
    has_fallback = any(row.fallback for row in chosen_rows)
    chosen_platforms = {row.platform for row in chosen_rows if row.platform}
    moderate_variants = {
        p.variant for p in db.query(PlatformSheet).filter(PlatformSheet.moderate.is_(True),
                                                            PlatformSheet.variant.in_(chosen_platforms))
    } if chosen_platforms else set()
    severity = "moderate" if (has_fallback or moderate_variants) else "minor"

    pricing = {row.key: row.payload for row in db.query(ServicePricing).all()}
    pkg, add_dv, timeline, services_cost = (
        pricing["PKG"], pricing["ADD_DV"]["value"], pricing["TIMELINE"], pricing["SERVICES"],
    )

    db.query(ServiceSelection).filter(ServiceSelection.sku_row_id.in_(sku_row_ids)).delete(synchronize_session=False)
    db.flush()
    for sel in payload.selections:
        db.add(ServiceSelection(sku_row_id=sel.sku_row_id, standard_dv=sel.standard_dv,
                                 threshold=sel.threshold, ifu=sel.ifu, human_factor=sel.human_factor))

    n_dv = sum(1 for sel in payload.selections if sel.standard_dv)
    lead = pkg[severity]
    dv_usd = (lead + add_dv * max(0, n_dv - 1)) * 1000 if n_dv else 0
    thr = sum(1 for sel in payload.selections if sel.threshold) * services_cost["threshold"]
    ifu = sum(1 for sel in payload.selections if sel.ifu) * services_cost["ifu"]
    hf = sum(1 for sel in payload.selections if sel.human_factor) * services_cost["human_factor"]

    req.severity = severity
    req.timeline_months = timeline[severity]
    req.comment = payload.comment
    req.urgency = payload.urgency
    req.total = dv_usd + thr + ifu + hf

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


@router.post("/{request_id}/submit", response_model=RequestDetailOut)
def submit_request(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)
    has_selections = any(row.service_selections for row in req.sku_rows)
    if req.chosen_option is None or not has_selections:
        raise HTTPException(422, "Select a platform option and configure services before submitting")
    req.status = "Awaiting assignment"
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)
```

- [ ] **Step 4: Run the full backend suite**

Run: `PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' backend/.venv/bin/pytest -v` (from `backend/`)
Expected: PASS, all tests including every deferred assertion from Tasks 8–9.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/requests.py backend/tests/test_requests.py
git commit -m "feat(backend): PUT services (severity + pricing) and POST submit endpoints"
```

---

## Frontend

### Task 11: `api.ts` — types and calls for the wizard endpoints

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `ReferenceProduct`, `SkuRow`, `ServiceSelection`, `RequestDetail`, `PlatformOptionRow`, `PlatformOptions` types; `listReferenceProducts`, `getRequestDetail`, `updateRequestStep1`, `getPlatformOptions`, `selectOption`, `updateServices`, `submitRequest` functions; extends `createRequest`'s body type and `RequestRow` type with the new flat fields.

- [ ] **Step 1: Extend types and `createRequest`/`RequestRow`**

In `frontend/lib/api.ts`, replace the `RequestRow` type and `createRequest` signature:

```typescript
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
  viscosity_val: number | null;
  differentiated: boolean;
  chosen_option: number | null;
  severity: string | null;
  timeline_months: number | null;
  comment: string | null;
  urgency: string | null;
};

export type SkuRow = { id: number; strength: string; cartridge: string; fill_ml: number };
export type ServiceSelection = {
  id: number;
  sku_row_id: number;
  standard_dv: boolean;
  threshold: boolean;
  ifu: boolean;
  human_factor: boolean;
};
export type RequestDetail = RequestRow & { sku_rows: SkuRow[]; service_selections: ServiceSelection[] };

export type ReferenceProduct = {
  brand: string;
  molecule: string;
  device: string;
  strengths: string[];
  visc_val: number;
  visc_ref: string;
  cartridge: string;
};

export type PlatformOptionRow = {
  sku: string;
  cartridge: string;
  platform: string | null;
  cls: string | null;
  sub: string | null;
  resolution: string | null;
  lockout: string | null;
  mech: string | null;
  band: string;
  pct: number | null;
  fallback: boolean;
  visc_limited: boolean;
};
export type PlatformOptions = { options: Record<"1" | "2" | "3", PlatformOptionRow[]> };

export async function createRequest(
  token: string,
  body: {
    brand: string;
    market: string;
    strengths?: string[];
    viscosity_val?: number | null;
    device?: string | null;
    differentiated?: boolean;
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't submit that request — try again.");
  }
  return resp.json();
}
```

- [ ] **Step 2: Add the wizard functions**

Append to `frontend/lib/api.ts` (after `listRequests`):

```typescript
export async function listReferenceProducts(token: string): Promise<ReferenceProduct[]> {
  const resp = await fetch(`/api/reference-products`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load reference products — try again.");
  return resp.json();
}

export async function getRequestDetail(token: string, id: number): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load that request — try again.");
  return resp.json();
}

export async function updateRequestStep1(
  token: string,
  id: number,
  body: {
    brand: string;
    market: string;
    strengths: string[];
    viscosity_val: number | null;
    device: string | null;
    differentiated: boolean;
    sku_rows: { strength: string; cartridge: string; fill_ml: number }[];
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save that step — try again.");
  return resp.json();
}

export async function getPlatformOptions(token: string, id: number): Promise<PlatformOptions> {
  const resp = await fetch(`/api/requests/${id}/platform-options`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load platform options — try again.");
  return resp.json();
}

export async function selectOption(token: string, id: number, chosenOption: number): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/select-option`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ chosen_option: chosenOption }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't select that option — try again.");
  return resp.json();
}

export async function updateServices(
  token: string,
  id: number,
  body: {
    selections: { sku_row_id: number; standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }[];
    comment: string;
    urgency: string;
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/services`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save your service selections — try again.");
  return resp.json();
}

export async function submitRequest(token: string, id: number): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/submit`, { method: "POST", headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't submit that request — try again.");
  return resp.json();
}
```

`authHeaders` is already defined above `listKams` in this file — Task's new functions sit after it, so no reordering needed as long as they're appended below that definition (they already are, since `listRequests`/`listKams` etc. are below it).

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run build`
Expected: build succeeds (this task only adds exports; nothing consumes the new body shape yet, so no type errors from callers).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): API client types and calls for the request wizard"
```

---

### Task 12: `/requests` — draft-and-submitted list with a "New request" button

**Files:**
- Modify: `frontend/app/requests/page.tsx`

**Interfaces:**
- Consumes: `listRequests`, `createRequest` (Task 11 signature change), `RequestRow`.
- Produces: rewritten `/requests` page — no inline form; a "New request" button (brand+market only) that creates a Draft and redirects to `/requests/[id]`; the table gains a Continue/View action per row.

- [ ] **Step 1: Rewrite the page**

Replace `frontend/app/requests/page.tsx` in full:

```tsx
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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

const MARKETS = [
  { value: "US", label: "US" },
  { value: "EU", label: "EU" },
  { value: "Canada", label: "Canada" },
];

export default function RequestsPage() {
  const { token, user } = useRoleGuard("Customer");
  const router = useRouter();
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewForm, setShowNewForm] = useState(false);
  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) return;
    listRequests(token)
      .then(setRequests)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : "We couldn't load your requests — try again.")
      )
      .finally(() => setLoading(false));
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBannerError("");
    const errors: Record<string, string> = {};
    if (!brand.trim()) errors.brand = "Enter a brand.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      const created = await createRequest(token, { brand, market });
      router.push(`/requests/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors);
      } else {
        setBannerError("We couldn't start that request — try again.");
      }
      setSubmitting(false);
    }
  }

  if (!token) return null;

  return (
    <>
      <Header userName={user?.name} role={user?.role} />
      <main className="mx-auto flex max-w-4xl flex-col gap-8 px-4 py-8 sm:px-6">
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h1 className="font-display text-lg font-semibold text-forest-900">Your requests</h1>
            {!showNewForm && <Button onClick={() => setShowNewForm(true)}>+ New request</Button>}
          </div>

          {showNewForm && (
            <Card className="mb-6">
              <form onSubmit={handleCreate} className="flex flex-col gap-4 sm:flex-row sm:items-end" noValidate>
                <div className="flex-1">
                  <TextField label="Brand" name="brand" value={brand} onChange={setBrand} error={fieldErrors.brand} />
                </div>
                <div className="w-full sm:w-40">
                  <SelectField label="Market" name="market" value={market} onChange={setMarket} options={MARKETS} />
                </div>
                <Button type="submit" loading={submitting}>
                  {submitting ? "Starting…" : "Start request"}
                </Button>
              </form>
              {bannerError && (
                <div className="mt-4">
                  <Banner message={bannerError} onDismiss={() => setBannerError("")} />
                </div>
              )}
            </Card>
          )}

          <Card padding="p-0">
            {loadError ? (
              <div className="p-6">
                <Banner message={loadError} onDismiss={() => setLoadError("")} />
              </div>
            ) : !loading && requests.length === 0 ? (
              <EmptyState message="No requests yet — start your first one above." />
            ) : (
              <>
                <table className="hidden w-full text-left sm:table">
                  <thead>
                    <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                      <th className="px-4 py-3 font-medium">ID</th>
                      <th className="px-4 py-3 font-medium">Brand</th>
                      <th className="px-4 py-3 font-medium">Market</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <>
                        <SkeletonRow />
                        <SkeletonRow />
                        <SkeletonRow />
                      </>
                    ) : (
                      requests.map((r) => (
                        <tr key={r.id} className="border-b border-ink-700/5 last:border-0">
                          <td className="px-4 py-3 font-mono text-sm text-ink-700/70">{r.id}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.brand}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.market}</td>
                          <td className="px-4 py-3">
                            <StatusChip status={r.status} />
                          </td>
                          <td className="px-4 py-3 text-right">
                            <Button variant="secondary" onClick={() => router.push(`/requests/${r.id}`)}>
                              {r.status === "Draft" ? "Continue" : "View"}
                            </Button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>

                <div className="divide-y divide-ink-700/5 sm:hidden">
                  {loading ? (
                    <>
                      <MobileSkeletonCard />
                      <MobileSkeletonCard />
                      <MobileSkeletonCard />
                    </>
                  ) : (
                    requests.map((r) => (
                      <button
                        key={r.id}
                        onClick={() => router.push(`/requests/${r.id}`)}
                        className="flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm font-medium text-ink-700">{r.brand}</span>
                          <span className="font-mono text-xs text-ink-700/70">#{r.id}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm text-ink-700/70">{r.market}</span>
                          <StatusChip status={r.status} />
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </>
            )}
          </Card>
        </section>
      </main>
    </>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/requests/page.tsx
git commit -m "feat(frontend): requests list gains New-request button and Continue/View action"
```

---

### Task 13: `/requests/[id]` wizard shell + Step 1 (request form)

**Files:**
- Create: `frontend/app/requests/[id]/page.tsx`

**Interfaces:**
- Consumes: `getRequestDetail`, `updateRequestStep1`, `listReferenceProducts` (Task 11); `useRoleGuard` (existing).
- Produces: the wizard page component, step-1 view fully wired; steps 2–3 stubbed as placeholders replaced by Tasks 14–15.

- [ ] **Step 1: Write the page with step 1 implemented and steps 2/3 as pass-through placeholders**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  ReferenceProduct,
  RequestDetail,
  getRequestDetail,
  listReferenceProducts,
  updateRequestStep1,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Header } from "@/components/Header";
import { Card } from "@/components/Card";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/SelectField";
import { TextField } from "@/components/TextField";
import { Skeleton } from "@/components/Skeleton";

const MARKETS = [
  { value: "US", label: "US" },
  { value: "EU", label: "EU" },
  { value: "Canada", label: "Canada" },
];
const CART_SIZES = ["1.5 mL", "3 mL", "1 mL PFS", "3 mL PFS", "1 mL Bespoke"];
const STEPS = [
  { key: "form", label: "1 · Request" },
  { key: "options", label: "2 · Platform options" },
  { key: "cost", label: "3 · Cost & deal" },
] as const;
type StepKey = (typeof STEPS)[number]["key"];

type SkuDraft = { strength: string; cartridge: string; fill_ml: number };

export default function RequestWizardPage() {
  const { token, user } = useRoleGuard("Customer");
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const requestId = Number(params.id);

  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [refProducts, setRefProducts] = useState<ReferenceProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [step, setStep] = useState<StepKey>("form");

  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");
  const [strengths, setStrengths] = useState<string[]>([]);
  const [skuRows, setSkuRows] = useState<SkuDraft[]>([]);
  const [viscosityVal, setViscosityVal] = useState<number | "">("");
  const [differentiated, setDifferentiated] = useState(false);
  const [device, setDevice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    if (!token || Number.isNaN(requestId)) return;
    Promise.all([getRequestDetail(token, requestId), listReferenceProducts(token)])
      .then(([req, products]) => {
        setDetail(req);
        setRefProducts(products);
        setBrand(req.brand);
        setMarket(req.market);
        setStrengths(req.sku_rows.map((r) => r.strength));
        setSkuRows(req.sku_rows.map((r) => ({ strength: r.strength, cartridge: r.cartridge, fill_ml: r.fill_ml })));
        setViscosityVal(req.viscosity_val ?? "");
        setDifferentiated(req.differentiated);
        setDevice(req.device);
        if (req.chosen_option != null && req.status === "Draft") setStep("options");
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setLoadError(err instanceof ApiError ? err.message : "We couldn't load this request — try again.");
        }
      })
      .finally(() => setLoading(false));
  }, [token, requestId]);

  const currentRef = refProducts.find((p) => p.brand === brand) ?? null;
  const isDraft = detail?.status === "Draft";

  function reconcileRowsForStrengths(next: string[]) {
    setStrengths(next);
    setSkuRows((prev) => {
      const existing = new Map(prev.map((r) => [r.strength, r]));
      return next.map((s) => {
        if (existing.has(s)) return existing.get(s)!;
        const cart = currentRef?.cartridge ?? "3 mL";
        return { strength: s, cartridge: cart, fill_ml: 1.5 };
      });
    });
  }

  function handleBrandChange(nextBrand: string) {
    setBrand(nextBrand);
    const ref = refProducts.find((p) => p.brand === nextBrand);
    reconcileRowsForStrengths(ref ? [...ref.strengths] : []);
    setDevice(ref?.device ?? null);
    setDifferentiated(false);
    setViscosityVal("");
  }

  async function saveStep1(): Promise<boolean> {
    if (!token) return false;
    setSaveError("");
    setSaving(true);
    try {
      const updated = await updateRequestStep1(token, requestId, {
        brand,
        market,
        strengths,
        viscosity_val: viscosityVal === "" ? null : Number(viscosityVal),
        device,
        differentiated,
        sku_rows: skuRows,
      });
      setDetail(updated);
      return true;
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "We couldn't save this step — try again.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleContinueToOptions() {
    if (await saveStep1()) setStep("options");
  }

  if (!token) return null;
  if (notFound) {
    return (
      <>
        <Header userName={user?.name} role={user?.role} />
        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
          <Banner message="That request doesn't exist or isn't yours." onDismiss={() => router.push("/requests")} />
        </main>
      </>
    );
  }

  return (
    <>
      <Header userName={user?.name} role={user?.role} />
      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6">
        <nav className="flex gap-2 rounded-full bg-sand-50 p-1" aria-label="Wizard steps">
          {STEPS.map((s) => (
            <button
              key={s.key}
              disabled={!isDraft && s.key !== "form"}
              onClick={() => isDraft && setStep(s.key)}
              className={`flex-1 rounded-full px-3 py-2 font-body text-sm transition-colors ${
                step === s.key ? "bg-white font-medium text-forest-900 shadow-sm" : "text-ink-700/60"
              }`}
            >
              {s.label}
            </button>
          ))}
        </nav>

        {loading ? (
          <Skeleton className="h-64 w-full" />
        ) : loadError ? (
          <Banner message={loadError} onDismiss={() => setLoadError("")} />
        ) : (
          <>
            {!isDraft && (
              <Banner
                message="This request has been submitted — it's read-only. Cost editing and negotiation are handled by your assigned Shaily KAM."
                onDismiss={() => {}}
              />
            )}

            {step === "form" && (
              <Card className="flex flex-col gap-6">
                <div>
                  <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Reference product</h2>
                  <div className="flex flex-col gap-4 sm:flex-row">
                    <div className="flex-1">
                      <SelectField
                        label="Reference product brand"
                        name="brand"
                        value={brand}
                        onChange={isDraft ? handleBrandChange : () => {}}
                        options={refProducts.map((p) => ({ value: p.brand, label: p.brand }))}
                      />
                    </div>
                    <div className="w-full sm:w-40">
                      <SelectField
                        label="Target market"
                        name="market"
                        value={market}
                        onChange={isDraft ? (v) => setMarket(v) : () => {}}
                        options={MARKETS}
                      />
                    </div>
                  </div>
                  {currentRef && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      ✓ Recognised — <b>{currentRef.molecule}</b> · device auto-set to <b>{currentRef.device}</b>.
                    </p>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">Strength(s) / SKUs</h2>
                  <div className="flex flex-wrap gap-2">
                    {(currentRef?.strengths ?? []).map((s) => (
                      <label
                        key={s}
                        className={`cursor-pointer rounded-full border px-3 py-1.5 font-body text-sm ${
                          strengths.includes(s)
                            ? "border-forest-600 bg-forest-600/10 text-forest-900"
                            : "border-ink-700/15 text-ink-700/70"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="sr-only"
                          disabled={!isDraft}
                          checked={strengths.includes(s)}
                          onChange={(e) => {
                            const next = e.target.checked ? [...strengths, s] : strengths.filter((x) => x !== s);
                            reconcileRowsForStrengths(next);
                          }}
                        />
                        {s}
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">Product viscosity</h2>
                  <div className="flex items-end gap-3">
                    <div className="w-40">
                      <TextField
                        label="Viscosity (cP)"
                        name="viscosity"
                        type="number"
                        value={viscosityVal === "" ? "" : String(viscosityVal)}
                        onChange={(v) => setViscosityVal(v === "" ? "" : Number(v))}
                      />
                    </div>
                    {isDraft && currentRef && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => setViscosityVal(currentRef.visc_val)}
                      >
                        ＋ Need assistance
                      </Button>
                    )}
                  </div>
                  {currentRef?.visc_ref && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">📄 Literature reference: {currentRef.visc_ref}</p>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">Device type</h2>
                  <label className="flex items-center gap-2 font-body text-sm text-ink-700">
                    <input
                      type="checkbox"
                      disabled={!isDraft}
                      checked={differentiated}
                      onChange={(e) => setDifferentiated(e.target.checked)}
                    />
                    Differentiated formulation (override auto-selected device)
                  </label>
                  {differentiated ? (
                    <div className="mt-2 w-56">
                      <SelectField
                        label="Device type"
                        name="device"
                        value={device ?? ""}
                        onChange={(v) => setDevice(v)}
                        options={[
                          { value: "Pen Injector", label: "Pen Injector" },
                          { value: "Auto-Injector", label: "Auto-Injector" },
                          { value: "On-Body", label: "On-Body" },
                        ]}
                      />
                    </div>
                  ) : (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      Device: {currentRef?.device ?? "—"} · auto from reference product
                    </p>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">
                    Cartridge & fill — one row per SKU
                  </h2>
                  {skuRows.length === 0 ? (
                    <p className="font-body text-sm text-ink-700/70">Select at least one strength above.</p>
                  ) : (
                    <table className="w-full text-left">
                      <thead>
                        <tr className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                          <th className="py-1.5">Strength</th>
                          <th className="py-1.5">Cartridge</th>
                          <th className="py-1.5">Fill (mL)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {skuRows.map((row, i) => (
                          <tr key={row.strength} className="border-t border-ink-700/5">
                            <td className="py-1.5 font-body text-sm text-ink-700">{row.strength}</td>
                            <td className="py-1.5">
                              <select
                                disabled={!isDraft}
                                value={row.cartridge}
                                onChange={(e) => {
                                  const next = [...skuRows];
                                  next[i] = { ...row, cartridge: e.target.value };
                                  setSkuRows(next);
                                }}
                                className="rounded-lg border border-ink-700/15 px-2 py-1 font-body text-sm"
                              >
                                {CART_SIZES.map((c) => (
                                  <option key={c} value={c}>
                                    {c}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="py-1.5">
                              <input
                                type="number"
                                step={0.1}
                                min={0.1}
                                disabled={!isDraft}
                                value={row.fill_ml}
                                onChange={(e) => {
                                  const next = [...skuRows];
                                  next[i] = { ...row, fill_ml: Number(e.target.value) };
                                  setSkuRows(next);
                                }}
                                className="w-24 rounded-lg border border-ink-700/15 px-2 py-1 font-body text-sm"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {saveError && <Banner message={saveError} onDismiss={() => setSaveError("")} />}

                {isDraft && (
                  <div>
                    <Button
                      onClick={handleContinueToOptions}
                      loading={saving}
                      disabled={strengths.length === 0 || skuRows.length === 0}
                    >
                      {saving ? "Saving…" : "Find platform options →"}
                    </Button>
                  </div>
                )}
              </Card>
            )}

            {step === "options" && detail && (
              <PlaceholderStepOptions />
            )}
            {step === "cost" && detail && (
              <PlaceholderStepCost />
            )}
          </>
        )}
      </main>
    </>
  );
}

function PlaceholderStepOptions() {
  return <Card>Step 2 lands in a later task.</Card>;
}
function PlaceholderStepCost() {
  return <Card>Step 3 lands in a later task.</Card>;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run build`
Expected: succeeds. If `Skeleton` isn't exported as a default single-block component (only `SkeletonRow`/`MobileSkeletonCard` were seen in `requests/page.tsx`), check `frontend/components/Skeleton.tsx` for its actual export name and adjust the import — use whatever block-level skeleton it exports (e.g. `Skeleton` or `SkeletonBlock`); if none exists, replace the `<Skeleton className="h-64 w-full" />` usage with a plain `<div className="h-64 w-full animate-pulse rounded-2xl bg-sand-50" />`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/requests/\[id\]/page.tsx
git commit -m "feat(frontend): request wizard shell and step 1 (request form)"
```

---

### Task 14: Step 2 — platform options

**Files:**
- Modify: `frontend/app/requests/[id]/page.tsx`

**Interfaces:**
- Consumes: `getPlatformOptions`, `selectOption` (Task 11).
- Produces: replaces `PlaceholderStepOptions` with the real option tables and selection flow.

- [ ] **Step 1: Replace the placeholder**

In `frontend/app/requests/[id]/page.tsx`, add to the imports:

```tsx
import { PlatformOptions, getPlatformOptions, selectOption } from "@/lib/api";
```

Add state near the other `useState` calls in `RequestWizardPage`:

```tsx
  const [options, setOptions] = useState<PlatformOptions | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState("");
  const [selecting, setSelecting] = useState(false);
```

Add an effect that loads options whenever `step` becomes `"options"`:

```tsx
  useEffect(() => {
    if (step !== "options" || !token || !detail) return;
    setOptionsLoading(true);
    setOptionsError("");
    getPlatformOptions(token, requestId)
      .then(setOptions)
      .catch((err) => setOptionsError(err instanceof ApiError ? err.message : "We couldn't load platform options — try again."))
      .finally(() => setOptionsLoading(false));
  }, [step, token, detail, requestId]);

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

Replace the `PlaceholderStepOptions` function and its call site — pass props instead:

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

Remove the old `PlaceholderStepOptions` function and `PlaceholderStepCost`'s sibling reference stays (Task 15 replaces it). Add the new component at the bottom of the file, replacing `PlaceholderStepOptions`:

```tsx
function StepOptions({
  options,
  loading,
  error,
  onDismissError,
  chosenOption,
  isDraft,
  selecting,
  onSelect,
}: {
  options: PlatformOptions | null;
  loading: boolean;
  error: string;
  onDismissError: () => void;
  chosenOption: number | null;
  isDraft: boolean;
  selecting: boolean;
  onSelect: (n: 1 | 2 | 3) => void;
}) {
  if (loading) return <Card>Loading platform options…</Card>;
  if (error) return <Banner message={error} onDismiss={onDismissError} />;
  if (!options) return null;

  return (
    <div className="flex flex-col gap-6">
      <p className="font-body text-sm text-ink-700/70">
        Each SKU is matched to cartridge-compatible Shaily platforms and ranked by device-mechanism closeness to the
        reference product. Three option sets are proposed — pick the one to take forward.
      </p>
      {([1, 2, 3] as const).map((n) => {
        const rows = options.options[String(n) as "1" | "2" | "3"];
        const selected = chosenOption === n;
        return (
          <Card key={n} className={selected ? "border-forest-600" : ""}>
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded-full bg-sand-50 px-3 py-1 font-body text-xs font-medium text-ink-700">
                Option {n}
              </span>
              {selected && <span className="font-body text-xs font-medium text-forest-600">✓ selected</span>}
            </div>
            <table className="w-full text-left">
              <thead>
                <tr className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                  <th className="py-1.5">SKU</th>
                  <th className="py-1.5">Platform</th>
                  <th className="py-1.5">Type</th>
                  <th className="py-1.5">Mechanism match</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.sku} className="border-t border-ink-700/5">
                    <td className="py-1.5 font-body text-sm text-ink-700">{row.sku}</td>
                    <td className="py-1.5 font-body text-sm text-ink-700">{row.platform ?? "—"}</td>
                    <td className="py-1.5 font-body text-sm text-ink-700">
                      {row.cls ?? "—"}
                      {row.sub ? ` · ${row.sub}` : ""}
                    </td>
                    <td className="py-1.5 font-body text-sm text-ink-700">
                      {row.band === "n/a" ? "—" : `${row.band} · ${row.pct}%`}
                      {row.fallback ? " ⚠ fallback" : ""}
                      {row.visc_limited ? " · visc-limited" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {isDraft && (
              <div className="mt-3">
                <Button variant={selected ? "primary" : "secondary"} loading={selecting} onClick={() => onSelect(n)}>
                  Select Option {n} →
                </Button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/requests/\[id\]/page.tsx
git commit -m "feat(frontend): request wizard step 2 — platform options"
```

---

### Task 15: Step 3 — cost & deal, submit, and the read-only submitted view

**Files:**
- Modify: `frontend/app/requests/[id]/page.tsx`

**Interfaces:**
- Consumes: `updateServices`, `submitRequest` (Task 11).
- Produces: replaces `PlaceholderStepCost` with per-SKU service checkboxes, live-computed total, comment/urgency, submit action; a non-Draft request renders all three steps read-only via the existing `isDraft` branches already wired in Tasks 13–14.

- [ ] **Step 1: Replace the placeholder**

Add to the imports:

```tsx
import { updateServices, submitRequest } from "@/lib/api";
```

Add state:

```tsx
  const [serviceRows, setServiceRows] = useState<
    Record<number, { standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }>
  >({});
  const [comment, setComment] = useState("");
  const [urgency, setUrgency] = useState("Level 1 · call back today");
  const [savingServices, setSavingServices] = useState(false);
  const [servicesError, setServicesError] = useState("");
  const [submittingRequest, setSubmittingRequest] = useState(false);
  const [submitBanner, setSubmitBanner] = useState("");
```

Add an effect that seeds `serviceRows` from `detail` whenever step 3 is entered or `detail` refreshes:

```tsx
  useEffect(() => {
    if (!detail) return;
    const bySkuId = new Map(detail.service_selections.map((s) => [s.sku_row_id, s]));
    const seeded: typeof serviceRows = {};
    for (const row of detail.sku_rows) {
      const existing = bySkuId.get(row.id);
      seeded[row.id] = existing
        ? { standard_dv: existing.standard_dv, threshold: existing.threshold, ifu: existing.ifu, human_factor: existing.human_factor }
        : { standard_dv: true, threshold: false, ifu: false, human_factor: false };
    }
    setServiceRows(seeded);
    setComment(detail.comment ?? "");
    setUrgency(detail.urgency ?? "Level 1 · call back today");
  }, [detail]);

  const PRICES = { standard_dv_lead: { minor: 200, moderate: 250, major: 350 }, add_dv: 50, threshold: 2110, ifu: 1110, human_factor: 400000 };

  function estimateTotal(): number {
    if (!detail) return 0;
    const sev = (detail.severity as "minor" | "moderate" | "major" | null) ?? "minor";
    const rows = Object.values(serviceRows);
    const nDv = rows.filter((r) => r.standard_dv).length;
    const lead = PRICES.standard_dv_lead[sev];
    const dv = nDv ? (lead + PRICES.add_dv * Math.max(0, nDv - 1)) * 1000 : 0;
    const thr = rows.filter((r) => r.threshold).length * PRICES.threshold;
    const ifu = rows.filter((r) => r.ifu).length * PRICES.ifu;
    const hf = rows.filter((r) => r.human_factor).length * PRICES.human_factor;
    return dv + thr + ifu + hf;
  }

  async function handleSaveServices(): Promise<boolean> {
    if (!token || !detail) return false;
    setServicesError("");
    setSavingServices(true);
    try {
      const updated = await updateServices(token, requestId, {
        selections: detail.sku_rows.map((row) => ({ sku_row_id: row.id, ...serviceRows[row.id] })),
        comment,
        urgency,
      });
      setDetail(updated);
      return true;
    } catch (err) {
      setServicesError(err instanceof ApiError ? err.message : "We couldn't save your service selections — try again.");
      return false;
    } finally {
      setSavingServices(false);
    }
  }

  async function handleSubmitRequest() {
    if (!(await handleSaveServices())) return;
    if (!token) return;
    setSubmittingRequest(true);
    try {
      await submitRequest(token, requestId);
      setSubmitBanner("Submitted to the Shaily BD desk. The BD Manager will assign a Key Account Manager.");
      setTimeout(() => router.push("/requests"), 1600);
    } catch (err) {
      setServicesError(err instanceof ApiError ? err.message : "We couldn't submit that request — try again.");
    } finally {
      setSubmittingRequest(false);
    }
  }
```

Replace the step-3 render block:

```tsx
            {step === "cost" && detail && (
              <StepCost
                detail={detail}
                serviceRows={serviceRows}
                setServiceRows={setServiceRows}
                comment={comment}
                setComment={setComment}
                urgency={urgency}
                setUrgency={setUrgency}
                isDraft={isDraft}
                estimatedTotal={estimateTotal()}
                error={servicesError}
                onDismissError={() => setServicesError("")}
                saving={savingServices}
                submitting={submittingRequest}
                submitBanner={submitBanner}
                onSubmit={handleSubmitRequest}
              />
            )}
```

Remove the now-unused `PlaceholderStepCost` function and add `StepCost` at the bottom of the file:

```tsx
function StepCost({
  detail,
  serviceRows,
  setServiceRows,
  comment,
  setComment,
  urgency,
  setUrgency,
  isDraft,
  estimatedTotal,
  error,
  onDismissError,
  saving,
  submitting,
  submitBanner,
  onSubmit,
}: {
  detail: RequestDetail;
  serviceRows: Record<number, { standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }>;
  setServiceRows: React.Dispatch<
    React.SetStateAction<Record<number, { standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }>>
  >;
  comment: string;
  setComment: (v: string) => void;
  urgency: string;
  setUrgency: (v: string) => void;
  isDraft: boolean;
  estimatedTotal: number;
  error: string;
  onDismissError: () => void;
  saving: boolean;
  submitting: boolean;
  submitBanner: string;
  onSubmit: () => void;
}) {
  function toggle(skuId: number, field: "standard_dv" | "threshold" | "ifu" | "human_factor") {
    setServiceRows((prev) => ({ ...prev, [skuId]: { ...prev[skuId], [field]: !prev[skuId][field] } }));
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h2 className="mb-3 font-display text-base font-semibold text-forest-900">Service selection — per SKU</h2>
        <table className="w-full text-left">
          <thead>
            <tr className="font-body text-xs uppercase tracking-wide text-ink-700/70">
              <th className="py-1.5">SKU</th>
              <th className="py-1.5">Standard DV</th>
              <th className="py-1.5">Threshold</th>
              <th className="py-1.5">IFU</th>
              <th className="py-1.5">Human Factor</th>
            </tr>
          </thead>
          <tbody>
            {detail.sku_rows.map((row) => {
              const sel = serviceRows[row.id];
              if (!sel) return null;
              return (
                <tr key={row.id} className="border-t border-ink-700/5">
                  <td className="py-1.5 font-body text-sm text-ink-700">{row.strength}</td>
                  {(["standard_dv", "threshold", "ifu", "human_factor"] as const).map((field) => (
                    <td key={field} className="py-1.5">
                      <input
                        type="checkbox"
                        disabled={!isDraft}
                        checked={sel[field]}
                        onChange={() => toggle(row.id, field)}
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Card>
        <h2 className="mb-3 font-display text-base font-semibold text-forest-900">Total package</h2>
        <p className="font-mono text-2xl text-forest-900">${estimatedTotal.toLocaleString()}</p>
        <p className="mt-1 font-body text-xs text-ink-700/70">
          Estimate updates as you tick services; the authoritative total is saved when you continue.
        </p>
      </Card>

      {isDraft && (
        <Card>
          <h2 className="mb-3 font-display text-base font-semibold text-forest-900">
            Submit this request to the Shaily BD desk
          </h2>
          <div className="mb-3">
            <label className="mb-1.5 block font-body text-sm font-medium text-ink-700" htmlFor="comment">
              Comment for the Shaily BD desk
            </label>
            <textarea
              id="comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="e.g. Bracket SKU 2–3 into one DV."
              className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700"
              rows={3}
            />
          </div>
          <div className="mb-4 w-72">
            <SelectField
              label="Urgency"
              name="urgency"
              value={urgency}
              onChange={setUrgency}
              options={[
                { value: "Level 1 · call back today", label: "Level 1 · call back today" },
                { value: "Level 2 · call back this week", label: "Level 2 · call back this week" },
              ]}
            />
          </div>
          {error && (
            <div className="mb-4">
              <Banner message={error} onDismiss={onDismissError} />
            </div>
          )}
          {submitBanner && (
            <div className="mb-4">
              <Banner message={submitBanner} onDismiss={() => {}} />
            </div>
          )}
          <Button onClick={onSubmit} loading={saving || submitting}>
            {saving || submitting ? "Submitting…" : "Submit request to Shaily BD"}
          </Button>
        </Card>
      )}
    </div>
  );
}
```

This file's imports need `React` in scope for the `React.Dispatch`/`React.SetStateAction` types — add `import type { Dispatch, SetStateAction } from "react";` and use `Dispatch<SetStateAction<...>>` instead if the project's TS config doesn't have the global `React` namespace auto-available (Next.js 14's default `tsconfig.json` does via the `next` types, so `React.Dispatch` typically resolves without an explicit import — verify via the build step below and adjust only if it errors).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run build`
Expected: succeeds. Fix any TS errors surfaced (most likely candidates: the `React.Dispatch` reference above, or a prop-type mismatch between `StepCost`'s props and the call site — align them exactly).

- [ ] **Step 3: Manual smoke walkthrough**

With the backend running (`docker-compose up -d --build` or local `uvicorn`) and frontend dev server up:
1. Log in as a `@pfizer.com`-style customer email.
2. `/requests` → "+ New request" → brand "Ozempic", market "US" → redirects to `/requests/{id}`.
3. Step 1: pick strengths, adjust a cartridge, click "Find platform options →".
4. Step 2: confirm three option tables render with bands/percentages; select Option 1.
5. Step 3: tick Threshold on one SKU, confirm the live total updates; add a comment; submit.
6. Confirm redirect to `/requests` shows the row as "Awaiting assignment" with a "View" action; opening it renders all three steps read-only.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/requests/\[id\]/page.tsx
git commit -m "feat(frontend): request wizard step 3 — cost & deal, submit, read-only submitted view"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** §4 data model → Tasks 1–2. §5 backend → Tasks 3–10 (one task per endpoint group, `platform_matching`/`reference_data` split out as their own testable services per spec's explicit call-out of both). §6 frontend → Tasks 11–15 (list page, wizard shell + 3 steps, read-only view folded into the same `isDraft` branches rather than a separate page, since spec §6 says it "reuses the same page/data-fetch"). §7 testing → unit tests on `platform_matching` (Task 3), happy-path/cascade/lock/ownership coverage across Tasks 7–10, `npm run build` + manual walkthrough (Task 15).
- **Deferred spec ambiguity resolved in "Implementation decisions" above**: base presentations storage, `GET /reference-products` shape, cartridge validation, and the sku_rows-replace/service_selections-FK interaction. Flagged there rather than left implicit so a reviewer can push back on any of the four independently.
- **Type consistency check**: `SkuRowOut`/`ServiceSelectionOut` (Task 5) match the frontend's `SkuRow`/`ServiceSelection` types (Task 11) field-for-field; `RequestDetailOut` (Task 5) matches `RequestDetail` (Task 11); `PlatformOptionsOut.options` keys (`"1"|"2"|"3"` strings, since JSON object keys are always strings) match `PlatformOptions.options`'s `Record<"1"|"2"|"3", ...>` type on the frontend.
