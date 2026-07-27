"""Headless verification of KAM module + existing screens via AppTest."""
from streamlit.testing.v1 import AppTest
import data as D

SKUS = ["0.25 mg", "0.5 mg", "1 mg", "2 mg"]
SKU_ROWS = [dict(Strength=s, Cartridge="3 mL", **{"Fill (mL)": 1.5}) for s in SKUS]


def run(screen, role, shaily, **extra):
    at = AppTest.from_file("app.py", default_timeout=90)
    at.session_state["user"] = dict(name="Tester", role=role, email="t@x.com", phone="+91999999")
    at.session_state["is_shaily"] = shaily
    at.session_state["screen"] = screen
    at.session_state["brand"] = "Ozempic"
    at.session_state["strengths"] = SKUS
    at.session_state["sku_rows"] = SKU_ROWS
    at.session_state["device"] = "Pen Injector"
    at.session_state["chosen_option"] = 1
    for k, v in extra.items():
        at.session_state[k] = v
    at.run()
    e = str(at.exception) if at.exception else None
    print(f"[{screen:8} {role.split('—')[-1].strip()[:22]:22}] {'none' if not e else e}")
    return e


problems = []
at = AppTest.from_file("app.py", default_timeout=90); at.run()
print(f"[gate] {'none' if not at.exception else at.exception}")
if at.exception: problems.append("gate")

for s, role in [("form", "Pharma — R&D / Formulation"), ("options", "Pharma — R&D / Formulation"),
                ("cost", "Pharma — R&D / Formulation")]:
    if run(s, role, False): problems.append(s)
if run("dash", "Shaily — BD Manager", True, mgr_view="Command centre"): problems.append("mgr-cmd")
if run("dash", "Shaily — BD Manager", True, mgr_view="KAM & assignments"): problems.append("mgr-kam")
if run("dash", "Shaily — Key Account Manager (KAM)", True, kam_id="mah"): problems.append("kam")

# logic checks
print("resolve Pfizer/Europe :", D.resolve_kam("Pfizer", "Europe"))      # org override -> mah
print("resolve <none>/India(S):", D.resolve_kam("XYZ", "India (South Region)"))  # region -> mah
print("resolve SANDOX        :", D.resolve_kam("SANDOX", "Europe"))       # org -> muk
print("KAMs:", [v["name"] for v in D.KAMS.values()])
print("Deliverables:", len(D.DELIVERABLES))
print("\nRESULT:", "ALL OK ✅" if not problems else f"PROBLEMS ❌ {problems}")
