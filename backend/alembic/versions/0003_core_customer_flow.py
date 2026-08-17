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
    for col in ["urgency", "comment", "timeline_months", "severity", "chosen_option", "differentiated", "viscosity_val"]:
        op.drop_column("requests", col)
