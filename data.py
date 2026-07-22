"""Domain data & engines for the Shaily DDCP Console (Streamlit build)."""
from __future__ import annotations

# ---- Brand palette ----
BRAND = {
    "blue": "#2F6E97", "blue_dk": "#234F70", "petal_blue": "#3D7CA6",
    "green": "#7DB343", "forest": "#2E7D46", "orange": "#E5883B", "gray": "#6D6E71",
    "bg": "#F5F8F8", "ink": "#0E1B24", "ink2": "#3A4C57", "muted": "#6B7C86",
    "line": "#DCE6E6", "surface": "#FFFFFF",
    "minor": "#2E7D46", "moderate": "#E5883B", "major": "#C0392B",
}

# ---- Reference products (public-literature derived) ----
REFERENCE_PRODUCTS = {
    "Ozempic":   dict(molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg", "0.5 mg", "1 mg", "2 mg"], visc_ref="DailyMed SmPC (NDC 0169-4181); aqueous GLP-1 solution"),
    "Wegovy":    dict(molecule="Semaglutide", device="Auto-Injector", dose="fixed", visc="water", visc_val=1.6, cartridge="1 mL PFS", strengths=["0.25 mg", "0.5 mg", "1 mg", "1.7 mg", "2.4 mg"], visc_ref="FDA label 215256; single-dose AI"),
    "Trulicity": dict(molecule="Dulaglutide", device="Auto-Injector", dose="fixed", visc="higher", visc_val=6.2, cartridge="1 mL PFS", strengths=["0.75 mg", "1.5 mg", "3 mg", "4.5 mg"], visc_ref="Lilly label; mAb fusion, elevated viscosity"),
    "Mounjaro":  dict(molecule="Tirzepatide", device="Auto-Injector", dose="fixed", visc="higher", visc_val=5.0, cartridge="1 mL PFS", strengths=["2.5 mg", "5 mg", "7.5 mg", "10 mg", "12.5 mg", "15 mg"], visc_ref="Lilly KwikPen literature"),
    "Victoza":   dict(molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.5, cartridge="3 mL", strengths=["0.6 mg", "1.2 mg", "1.8 mg"], visc_ref="EMA SmPC; multi-dose pen"),
    "Saxenda":   dict(molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.5, cartridge="3 mL", strengths=["0.6 mg", "1.2 mg", "1.8 mg", "2.4 mg", "3 mg"], visc_ref="EMA SmPC; weight-management pen"),
    "Toujeo":    dict(molecule="Insulin glargine U300", device="Pen Injector", dose="variable", visc="water", visc_val=1.8, cartridge="1.5 mL", strengths=["300 U/mL"], visc_ref="Sanofi label; basal insulin"),
    "Lantus":    dict(molecule="Insulin glargine", device="Pen Injector", dose="variable", visc="water", visc_val=1.7, cartridge="3 mL", strengths=["100 U/mL"], visc_ref="Sanofi label; basal insulin"),
    "Humira":    dict(molecule="Adalimumab", device="Auto-Injector", dose="fixed", visc="higher", visc_val=12.5, cartridge="1 mL PFS", strengths=["10 mg", "20 mg", "40 mg", "80 mg"], visc_ref="AbbVie label; high-viscosity mAb"),
    "Enbrel":    dict(molecule="Etanercept", device="Auto-Injector", dose="fixed", visc="higher", visc_val=9.0, cartridge="1 mL PFS", strengths=["25 mg", "50 mg"], visc_ref="Amgen label; mAb"),
    "Dupixent":  dict(molecule="Dupilumab", device="Auto-Injector", dose="fixed", visc="higher", visc_val=8.5, cartridge="3 mL PFS", strengths=["200 mg", "300 mg"], visc_ref="Regeneron label; mAb"),
}

CART_SIZES = ["1.5 mL", "3 mL", "1 mL PFS", "3 mL PFS", "1 mL Bespoke"]

# ---- Shaily platform sheet (authoritative) ----
# cls: Pen Injector | Autoinjector | On-Body ; carts: compatible cartridge sizes
PLATFORM_SHEET = [
    dict(family="Axiom",     variant="Axiom",              cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Push-Pull",    color="#8FBF52"),
    dict(family="Axiom Max", variant="Axiom Max",          cls="Pen Injector", sub="Disposable", resolution="Fixed – 80 IU",                      lockout="Yes", carts=["3 mL", "1.5 mL"],     mech="Push-Pull",    color="#E5883B"),
    dict(family="Protean",   variant="Protean P3",         cls="Pen Injector", sub="Disposable", resolution="Variable – 3 dose settings – 80 IU", lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean P5",         cls="Pen Injector", sub="Disposable", resolution="Variable – 5 dose settings – 80 IU", lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean P60",        cls="Pen Injector", sub="Disposable", resolution="Fixed – 60 IU",                      lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean PS1",        cls="Pen Injector", sub="Disposable", resolution="Fixed – only 1 dose",                lockout="Yes", carts=["1.5 mL"],              mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean PR60",       cls="Pen Injector", sub="Reusable",   resolution="Fixed – 60 IU",                      lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Neo",       variant="Neo (3 mL)",         cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Torsion Spring", color="#7DB343"),
    dict(family="Neo",       variant="Neo (1.5 mL)",       cls="Pen Injector", sub="Disposable", resolution="Variable Dose – 80 IU",              lockout="Yes", carts=["1.5 mL"],              mech="Torsion Spring", color="#7DB343"),
    dict(family="Harmony",   variant="Harmony HS1",        cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Clutch Pen",   color="#3D7CA6"),
    dict(family="Harmony",   variant="Harmony H2",         cls="Pen Injector", sub="Disposable", resolution="Variable Dose – 80 IU",              lockout="Yes", carts=["1.5 mL"],              mech="Clutch Pen",   color="#3D7CA6"),
    dict(family="Maxim",     variant="Maxim (Disposable)", cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Pulley",       color="#2F6E97"),
    dict(family="Maxim",     variant="Maxim (Reusable)",   cls="Pen Injector", sub="Reusable",   resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Pulley",       color="#2F6E97", moderate=True),
    dict(family="Tristan",   variant="Tristan",            cls="Autoinjector", sub="",           resolution="0.2 – 1 mL",                         lockout="N/A", carts=["1 mL PFS"],           mech="3-step AI",    color="#234F70"),
    dict(family="Toby",      variant="Toby",               cls="Autoinjector", sub="",           resolution="0.2 – 2.25 mL",                      lockout="N/A", carts=["1 mL PFS", "3 mL PFS"], mech="2-step AI",  color="#2E7D46"),
    dict(family="Safe-LAN",  variant="Safe LAN",           cls="Autoinjector", sub="",           resolution="0.5 mL",                             lockout="N/A", carts=["1 mL Bespoke"],       mech="2-step AI (high visc.)", color="#C0392B"),
    dict(family="Mira",      variant="Mira",               cls="On-Body",      sub="",           resolution="0.5 – 20 mL",                        lockout="N/A", carts=["1 mL Bespoke"],       mech="On-body device", color="#6D6E71"),
]


def platforms_for_cartridge(cart: str):
    """Compatible platforms for a cartridge size, in presentation order (Option 1..n)."""
    return [p for p in PLATFORM_SHEET if cart in p["carts"]]


# ---- Cost / timelines / services ----
PKG = {"minor": 200, "moderate": 250, "major": 350}   # K USD, governing DV
ADD_DV = 50
TIMELINE = {"minor": 3, "moderate": 6, "major": 9}
SEV_LABEL = {"minor": "Minor change", "moderate": "Moderate change", "major": "Major change"}
SEV_LOGIC = {
    "minor": "Minor tool modification + tool validation",
    "moderate": "Up to 2 tool modifications + tool validation",
    "major": "> 2 tool modifications + tool validation",
}
SERVICES = dict(standard_dv=200, threshold=2110, ifu=1110, human_factor=400000)  # USD (standard_dv in K)
STD_CONDITION_TESTS = [
    "Deliverable Volume (ISO 11608-1)", "Dose Accuracy — rear", "Dose Accuracy — middle",
    "Dose Accuracy — end", "Last-dose lock-out", "Injection force (ISO 11608-1)",
]


def commercial_fy(sub_fy: str, sub_q: str) -> str:
    y = int("".join(ch for ch in sub_fy if ch.isdigit()))
    q = int("".join(ch for ch in sub_q if ch.isdigit()) or "1")
    total = y * 4 + (q - 1) + 10
    return f"FY{total // 4} Q{(total % 4) + 1}"


MARKETS = ["US", "EU", "India", "Asia", "LATAM"]
FY_OPTIONS = [f"FY{y}" for y in range(26, 32)]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]

# ═══════════════════════════════════════════════════════════════════════════
# BD organisation & command-centre data (from the client org tables)
# ═══════════════════════════════════════════════════════════════════════════
BD_MANAGER = "Ms. Priya (BD Manager)"
REPS = ["Mr. MAH", "Mr. HEN", "Mr. MUK", "Mr. FED", "Ms. SUK"]
PLATFORM_COLS = ["Toby", "Neo", "Harmony", "Axiom", "Axiom Max", "Protean", "Tristan", "Mira", "Safe-LAN"]
CUSTOMERS = ["Auro", "DRL", "Sand", "Dem", "Shun", "Homo", "Chem", "McD", "Torr"]
REP_REGION = {"Mr. MAH": "India", "Mr. HEN": "Europe", "Mr. MUK": "Asia", "Mr. FED": "North America", "Ms. SUK": "Europe"}

# Quarter-wise expected business per rep ($M)
REP_QUARTERLY = {
    "Mr. MAH": {"Q1": 8, "Q2": 10, "Q3": 9, "Q4": 12},
    "Mr. HEN": {"Q1": 6, "Q2": 7, "Q3": 8, "Q4": 9},
    "Mr. MUK": {"Q1": 5, "Q2": 6, "Q3": 7, "Q4": 8},
    "Mr. FED": {"Q1": 7, "Q2": 6, "Q3": 9, "Q4": 10},
    "Ms. SUK": {"Q1": 4, "Q2": 5, "Q3": 6, "Q4": 7},
}
QUARTER_TARGET = {"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}
NEW_CUSTOMERS_QTR = {"Q1": 2, "Q2": 1, "Q3": 3, "Q4": 2}

# Rep × platform business ($M) — which rep drives which platform
REP_PLATFORM = {
    "Mr. MAH": {"Neo": 12, "Toby": 11},
    "Mr. HEN": {"Harmony": 9, "Axiom": 9},
    "Mr. MUK": {"Protean": 8, "Axiom Max": 6},
    "Mr. FED": {"Toby": 10, "Tristan": 10},
    "Ms. SUK": {"Mira": 7, "Safe-LAN": 7},
}
# Rep × customer (business partner) business ($M)
REP_CUSTOMER = {
    "Mr. MAH": {"Auro": 14, "McD": 9},
    "Mr. HEN": {"DRL": 11, "Chem": 7},
    "Mr. MUK": {"Sand": 8, "Torr": 6},
    "Mr. FED": {"Dem": 12, "Homo": 8},
    "Ms. SUK": {"Shun": 9, "Chem": 5},
}
# Expected production output per Shaily variant (million units) from combined demand
PRODUCTION = {"Toby": 21, "Neo": 34, "Harmony": 18, "Axiom": 12, "Axiom Max": 9,
              "Protean": 15, "Tristan": 7, "Mira": 4, "Safe-LAN": 6}

EVENTS = [
    dict(name="CPHI Worldwide", city="Frankfurt", date="Oct 2026", tag="Exhibiting"),
    dict(name="PDA Universe of Pre-filled Syringes", city="Vienna", date="Nov 2026", tag="Speaking"),
    dict(name="PODD — Drug Delivery Partnerships", city="Boston", date="Oct 2026", tag="Booth"),
    dict(name="DDL — Drug Delivery to the Lungs", city="Edinburgh", date="Dec 2026", tag="Attending"),
]

# Workforce view (individual reps) — promptness + call log
WORKFORCE = [
    dict(id="mah", name="Mr. MAH", region="India", promptness=92,
         calls=[("2026-07-20", "Auro — Neo 4-SKU sampling"), ("2026-07-15", "McD — Toby DV scope"), ("2026-07-08", "Auro — pricing review")]),
    dict(id="hen", name="Mr. HEN", region="Europe", promptness=85,
         calls=[("2026-07-19", "DRL — Harmony CRF walkthrough"), ("2026-07-09", "Chem — Axiom intro")]),
    dict(id="muk", name="Mr. MUK", region="Asia", promptness=88,
         calls=[("2026-07-17", "Sand — Protean fit"), ("2026-07-05", "Torr — Axiom Max enquiry")]),
    dict(id="fed", name="Mr. FED", region="North America", promptness=80,
         calls=[("2026-07-18", "Dem — Toby PFS review"), ("2026-07-12", "Homo — Tristan scoping")]),
    dict(id="suk", name="Ms. SUK", region="Europe", promptness=90,
         calls=[("2026-07-14", "Shun — Mira on-body demo"), ("2026-07-06", "Chem — Safe-LAN viscosity")]),
]


def relationship_score(w) -> int:
    recency = min(100, 60 + len(w["calls"]) * 8) if w["calls"] else 40
    return round(recency * 0.6 + w["promptness"] * 0.4)
