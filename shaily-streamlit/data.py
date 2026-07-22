"""Domain data & engines for the Shaily DDCP Console (ported from the prototype)."""
from __future__ import annotations

# ---- Brand palette ----
BRAND = {
    "blue": "#2F6E97", "blue_dk": "#234F70",
    "petal_blue": "#3D7CA6", "green": "#7DB343", "forest": "#2E7D46",
    "orange": "#E5883B", "gray": "#6D6E71",
    "bg": "#F5F8F8", "ink": "#0E1B24", "ink2": "#3A4C57", "muted": "#6B7C86",
    "line": "#DCE6E6", "surface": "#FFFFFF",
    "minor": "#2E7D46", "moderate": "#E5883B", "major": "#C0392B",
}

# ---- Reference products (public-literature derived) ----
REFERENCE_PRODUCTS = {
    "Ozempic":   dict(molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.4, container="3 mL cartridge · 1.5 mL fill", strengths=["0.25 mg", "0.5 mg", "1 mg", "2 mg"]),
    "Wegovy":    dict(molecule="Semaglutide", device="Auto-Injector", dose="fixed", visc="water", visc_val=1.6, container="1 mL cartridge · 0.5 mL fill", strengths=["0.25 mg", "0.5 mg", "1 mg", "1.7 mg", "2.4 mg"]),
    "Trulicity": dict(molecule="Dulaglutide", device="Auto-Injector", dose="fixed", visc="higher", visc_val=6.2, container="1 mL cartridge · 0.5 mL fill", strengths=["0.75 mg", "1.5 mg", "3 mg", "4.5 mg"]),
    "Mounjaro":  dict(molecule="Tirzepatide", device="Auto-Injector", dose="fixed", visc="higher", visc_val=5.0, container="1 mL cartridge · 0.5 mL fill", strengths=["2.5 mg", "5 mg", "7.5 mg", "10 mg", "12.5 mg", "15 mg"]),
    "Victoza":   dict(molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.5, container="3 mL cartridge · 3 mL fill", strengths=["0.6 mg", "1.2 mg", "1.8 mg"]),
    "Saxenda":   dict(molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.5, container="3 mL cartridge · 3 mL fill", strengths=["0.6 mg", "1.2 mg", "1.8 mg", "2.4 mg", "3 mg"]),
    "Toujeo":    dict(molecule="Insulin glargine U300", device="Pen Injector", dose="variable", visc="water", visc_val=1.8, container="1.5 mL cartridge · 1.5 mL fill", strengths=["300 U/mL"]),
    "Lantus":    dict(molecule="Insulin glargine", device="Pen Injector", dose="variable", visc="water", visc_val=1.7, container="3 mL cartridge · 3 mL fill", strengths=["100 U/mL"]),
    "Humira":    dict(molecule="Adalimumab", device="Auto-Injector", dose="fixed", visc="higher", visc_val=12.5, container="1 mL cartridge · 0.5 mL fill", strengths=["10 mg", "20 mg", "40 mg", "80 mg"]),
    "Enbrel":    dict(molecule="Etanercept", device="Auto-Injector", dose="fixed", visc="higher", visc_val=9.0, container="1 mL cartridge · 0.5 mL fill", strengths=["25 mg", "50 mg"]),
    "Dupixent":  dict(molecule="Dupilumab", device="Auto-Injector", dose="fixed", visc="higher", visc_val=8.5, container="3 mL cartridge · 3 mL fill", strengths=["200 mg", "300 mg"]),
}

# ---- Shaily platform range (shaily.com/healthcare/platform-devices) ----
PLATFORMS = [
    dict(id="neo", name="ShailyPen Neo™", type="Pen Injector", dose="variable", color="#7DB343",
         containers=["3 mL cartridge · 1.5 mL fill", "3 mL cartridge · 3 mL fill", "1.5 mL cartridge · 1.5 mL fill"], max_visc="higher",
         desc="Spring-driven variable- or fixed-dose pen — the launch platform for GLP-1 self-medication in 1.5 & 3 mL cartridges.",
         tags=["Spring-driven", "Variable / fixed", "GLP-1", "1.5 & 3 mL"]),
    dict(id="harmony2", name="ShailyPen Harmony® 2", type="Pen Injector", dose="variable", color="#3D7CA6",
         containers=["1.5 mL cartridge · 1.5 mL fill", "3 mL cartridge · 1.5 mL fill", "3 mL cartridge · 3 mL fill"], max_visc="water",
         desc="Cost-effective spring-driven pen for chronic therapy — supports 1.5 & 3 mL cartridges with fine dose resolution.",
         tags=["Spring-driven", "Fine resolution", "1.5 & 3 mL", "Chronic"]),
    dict(id="maxim", name="ShailyPen Maxim™", type="Pen Injector", dose="variable", color="#2F6E97",
         containers=["3 mL cartridge · 3 mL fill", "3 mL cartridge · 1.5 mL fill"], max_visc="higher",
         desc="80-unit reusable or disposable pen for high-capacity chronic dosing — insulin and GLP-1 programmes.",
         tags=["80-unit", "Reusable / disposable", "High capacity", "Insulin · GLP-1"]),
    dict(id="protean", name="ShailyPen Protean®", type="Pen Injector", dose="variable", color="#5FA0C4",
         containers=["3 mL cartridge · 3 mL fill", "3 mL cartridge · 1.5 mL fill"], max_visc="water",
         desc="Versatile disposable & reusable pen delivering insulin (0–60 U), liraglutide and abaloparatide.",
         tags=["Disposable & reusable", "0–60 U", "Insulin", "Peptides"]),
    dict(id="axiom", name="ShailyPen Axiom™", type="Pen Injector", dose="fixed", color="#8FBF52",
         containers=["1.5 mL cartridge · 1.5 mL fill", "3 mL cartridge · 1.5 mL fill"], max_visc="water",
         desc="Non-priming fixed-dose pen developed for hormonal therapies — Teriparatide, PTH and FSH.",
         tags=["Fixed dose", "Non-priming", "Hormonal", "Teriparatide · PTH"]),
    dict(id="axiommax", name="ShailyPen Axiom Max™", type="Pen Injector", dose="fixed", color="#E5883B",
         containers=["3 mL cartridge · 1.5 mL fill", "1 mL cartridge · 0.5 mL fill"], max_visc="higher",
         desc="Fixed-dose pen engineered for GLP-1 self-injection with larger deliverable volumes.",
         tags=["Fixed dose", "GLP-1", "Larger volume"]),
    dict(id="toby", name="Shaily AI Toby™", type="Auto-Injector", dose="fixed", color="#2E7D46",
         containers=["1 mL cartridge · 0.5 mL fill"], max_visc="higher",
         desc="Two-step auto-injector for fixed-dose prefilled formats — the AI platform for biologics and high-viscosity mAbs.",
         tags=["Auto-injector", "Two-step", "Prefilled", "High viscosity"]),
]

CONTAINER_OPTIONS = [
    "1.5 mL cartridge · 1.5 mL fill",
    "3 mL cartridge · 1.5 mL fill",
    "3 mL cartridge · 3 mL fill",
    "1 mL cartridge · 0.5 mL fill",
]

STOPPERS = {
    "1 mL cartridge · 0.5 mL fill":   dict(dims="Ø6.85 mm", cartridge="Ø8.65 × 45 mm", a="West 4023/50 FluroTec", b="Datwyler Omniflex FM457"),
    "1.5 mL cartridge · 1.5 mL fill": dict(dims="Ø9.55 mm", cartridge="Ø9.70 × 47 mm", a="West 4432/50 FluroTec", b="Datwyler Omniflex FM257"),
    "3 mL cartridge · 1.5 mL fill":   dict(dims="Ø10.85 mm", cartridge="Ø10.85 × 64 mm", a="West 4432/50 FluroTec", b="Datwyler Omniflex FM257"),
    "3 mL cartridge · 3 mL fill":     dict(dims="Ø10.85 mm", cartridge="Ø10.85 × 64 mm", a="West 4432/50 FluroTec", b="Datwyler Omniflex FM257"),
}

MARKETS = ["US", "EU", "India", "Asia", "LATAM"]
FY_OPTIONS = [f"FY{y}" for y in range(26, 32)]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]

# ---- Pricing / timelines / severity ----
PKG = {"minor": 200, "moderate": 250, "major": 350}   # K USD, governing DV
ADD_DV = 50                                            # K USD per additional bracketed SKU
TIMELINE = {"minor": 3, "moderate": 6, "major": 9}     # months
SEV_LABEL = {"minor": "Minor change", "moderate": "Moderate change", "major": "Major change"}
SEV_LOGIC = {
    "minor": "Minor tool modification + tool validation",
    "moderate": "Up to 2 tool modifications + tool validation",
    "major": "> 2 tool modifications + tool validation",
}
SERVICES = dict(standard_dv=200, threshold=2110, ifu=1110, human_factor=400000)  # USD (standard_dv in K)

STD_CONDITION_TESTS = [
    "Deliverable Volume (ISO 11608-1)",
    "Dose Accuracy — rear portion",
    "Dose Accuracy — middle portion",
    "Dose Accuracy — end portion",
    "Last-dose lock-out",
    "Injection force (ISO 11608-1)",
]


def score_platform(p, device, container, viscosity, ref_dose=None):
    s, reasons = 0, []
    if p["type"] == device:
        s += 42; reasons.append("device type")
    if container in p["containers"]:
        s += 26; reasons.append("container fit")
    elif any(c.split(" cartridge")[0] == container.split(" cartridge")[0] for c in p["containers"]):
        s += 13; reasons.append("cartridge size")
    if viscosity == "water" or p["max_visc"] == "higher":
        s += 20
        if viscosity == "higher":
            reasons.append("high-viscosity drive")
    if ref_dose and ref_dose == p["dose"]:
        s += 12; reasons.append("dose mode")
    elif not ref_dose:
        s += 6
    return min(99, s), reasons


def rank_platforms(device, container, viscosity, ref_dose=None):
    scored = [(p, *score_platform(p, device, container, viscosity, ref_dose)) for p in PLATFORMS]
    return sorted(scored, key=lambda t: t[1], reverse=True)


def severity_for(platform, device, container, viscosity, deviation):
    mods, drivers = 0, []
    if platform["type"] != device:
        mods += 2; drivers.append("device-format change")
    if container not in platform["containers"]:
        size_match = any(c.split(" cartridge")[0] == container.split(" cartridge")[0] for c in platform["containers"])
        if size_match:
            mods += 1; drivers.append("fill-volume tooling")
        else:
            mods += 2; drivers.append("cartridge-format tooling")
    if viscosity == "higher" and platform["max_visc"] != "higher":
        mods += 1; drivers.append("drive-spring uprate")
    if deviation and mods == 0:
        mods += 1; drivers.append("plunger/interface tuning")
    sev = "minor" if mods <= 1 else "moderate" if mods == 2 else "major"
    return sev, max(mods, 1), drivers


def commercial_fy(sub_fy: str, sub_q: str) -> str:
    """Commercial realisation FY = submission FY + 2.5 years (10 quarters)."""
    y = int("".join(ch for ch in sub_fy if ch.isdigit()))
    q = int("".join(ch for ch in sub_q if ch.isdigit()) or "1")
    total = y * 4 + (q - 1) + 10
    return f"FY{total // 4} Q{(total % 4) + 1}"


# ---- BD dashboard demo data ----
WORKFORCE = [
    dict(id="jd", name="James Doyle", region="North America", engagements=6, promptness=80,
         calls=[("2026-07-18", "Aurora — reviewed Neo sampling for 4 SKUs"), ("2026-07-12", "Kyowa — AI Toby DV scope call"), ("2026-07-03", "Aurora — commercial pricing pushback")]),
    dict(id="sk", name="Sofia Klein", region="Europe", engagements=8, promptness=85,
         calls=[("2026-07-19", "Medreich — Harmony 2 CRF walkthrough"), ("2026-07-09", "Elis Pharma — intro & platform overview")]),
    dict(id="aw", name="Aarav Wagh", region="India", engagements=9, promptness=92,
         calls=[("2026-07-20", "Sun Devices — Neo 5-SKU matrix DV"), ("2026-07-15", "Sun Devices — HF study scoping"), ("2026-07-08", "Cipla — early enquiry"), ("2026-07-01", "Sun Devices — sample dispatch")]),
    dict(id="mj", name="Mei Jing", region="Asia", engagements=7, promptness=88,
         calls=[("2026-07-17", "Zhejiang Hisun — Maxim insulin fit"), ("2026-07-05", "Hisun — cartridge compatibility")]),
    dict(id="ra", name="Rahul Anand", region="India", engagements=5, promptness=78,
         calls=[("2026-07-16", "Alkem — AI Toby for dulaglutide")]),
    dict(id="er", name="Elena Rossi", region="Europe", engagements=6, promptness=90,
         calls=[("2026-07-14", "Adriatic Bio — Neo vs Harmony trade-off"), ("2026-07-06", "Adriatic Bio — timeline review")]),
    dict(id="kt", name="Kenji Tan", region="Asia", engagements=4, promptness=83,
         calls=[("2026-07-11", "Tanabe — exploratory GLP-1 device")]),
]

ENGAGEMENTS = [
    dict(customer="Sun Devices", product="Tirzepatide (Mounjaro ref)", skus=5, platform="ShailyPen Neo™", opp_m=40, volume_m=11.0, sub_fy="FY27", sub_q="Q2", market="US", stage="Sampling", owner="Aarav Wagh"),
    dict(customer="Kyowa Pharma", product="Adalimumab (Humira ref)", skus=2, platform="Shaily AI Toby™", opp_m=31, volume_m=8.0, sub_fy="FY27", sub_q="Q1", market="US", stage="NDA", owner="James Doyle"),
    dict(customer="Aurora Biologics", product="Semaglutide (Ozempic ref)", skus=4, platform="ShailyPen Neo™", opp_m=24, volume_m=6.5, sub_fy="FY26", sub_q="Q3", market="US", stage="Proposal", owner="James Doyle"),
    dict(customer="Alkem Labs", product="Dulaglutide (Trulicity ref)", skus=3, platform="Shaily AI Toby™", opp_m=18, volume_m=4.4, sub_fy="FY27", sub_q="Q3", market="India", stage="CRF", owner="Rahul Anand"),
    dict(customer="Medreich Generics", product="Liraglutide (Victoza ref)", skus=3, platform="ShailyPen Harmony® 2", opp_m=12, volume_m=3.2, sub_fy="FY26", sub_q="Q4", market="EU", stage="CRF", owner="Sofia Klein"),
    dict(customer="Zhejiang Hisun", product="Insulin glargine (Lantus ref)", skus=2, platform="ShailyPen Maxim™", opp_m=9, volume_m=5.0, sub_fy="FY26", sub_q="Q2", market="Asia", stage="Proposal", owner="Mei Jing"),
]

EVENTS = [
    dict(name="CPHI Worldwide", city="Frankfurt", date="Oct 2026", tag="Exhibiting"),
    dict(name="PDA Universe of Pre-filled Syringes", city="Vienna", date="Nov 2026", tag="Speaking"),
    dict(name="PODD — Drug Delivery Partnerships", city="Boston", date="Oct 2026", tag="Booth"),
    dict(name="DDL — Drug Delivery to the Lungs", city="Edinburgh", date="Dec 2026", tag="Attending"),
]

IP_LANDSCAPE = {
    "US": dict(patents=6, earliest="FY31", note="2 formulation + 4 device patents in the Orange Book; earliest generic entry FY31."),
    "EU": dict(patents=4, earliest="FY30", note="SPC protection extends to FY30 in major EU states."),
    "India": dict(patents=1, earliest="FY27", note="Limited product-patent coverage; near-term entry feasible."),
    "Asia": dict(patents=2, earliest="FY28", note="Market-specific filings; moderate barrier to entry."),
    "LATAM": dict(patents=1, earliest="FY28", note="Sparse device-patent coverage; entry feasible mid-term."),
}

STAGE_ORDER = ["Sampling", "CRF", "Proposal", "NDA", "Won"]
STAGE_PROB = {"Sampling": 0.2, "CRF": 0.4, "Proposal": 0.6, "NDA": 0.8, "Won": 1.0}
STAGE_COLOR = {"Sampling": "#5FA0C4", "CRF": "#3D7CA6", "Proposal": "#E5883B", "NDA": "#7DB343", "Won": "#2E7D46"}
REGION_COLOR = {"North America": "#3D7CA6", "Europe": "#2E7D46", "India": "#E5883B", "Asia": "#7DB343"}


def relationship_score(w) -> int:
    recency = min(100, 60 + len(w["calls"]) * 8) if w["calls"] else 40
    return round(recency * 0.6 + w["promptness"] * 0.4)
