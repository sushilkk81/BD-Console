"""Headless verification: run each screen via AppTest and report exceptions."""
from streamlit.testing.v1 import AppTest
import data as D

SKUS = ["0.25 mg", "0.5 mg", "1 mg", "2 mg"]
SKU_ROWS = [dict(Strength=s, Cartridge="3 mL", **{"Fill (mL)": 1.5}) for s in SKUS]


def base(at, shaily=False, dash_tab="BD Manager"):
    at.session_state["user"] = dict(name="Priya Rao", role="Shaily — BD Manager",
                                    email="priya@shaily.com", phone="+911234567")
    at.session_state["is_shaily"] = shaily
    at.session_state["dash_tab"] = dash_tab
    at.session_state["brand"] = "Ozempic"
    at.session_state["strengths"] = SKUS
    at.session_state["sku_rows"] = SKU_ROWS
    at.session_state["device"] = "Pen Injector"
    at.session_state["chosen_option"] = 1


def run(screen, **kw):
    at = AppTest.from_file("app.py", default_timeout=90)
    base(at, **kw)
    at.session_state["screen"] = screen
    at.run()
    e = str(at.exception) if at.exception else None
    print(f"[{screen:9}{'/'+kw.get('dash_tab','') if kw else '':13}] {'none' if not e else e}")
    return e


problems = []
at = AppTest.from_file("app.py", default_timeout=90); at.run()
print(f"[gate      ] {'none' if not at.exception else at.exception}")
if at.exception: problems.append(("gate", at.exception))

for s in ["form", "options", "cost"]:
    if run(s, shaily=False):
        problems.append((s, "err"))
if run("dash", shaily=True, dash_tab="BD Manager"): problems.append(("dash-mgr", "err"))
if run("dash", shaily=True, dash_tab="Workforce view"): problems.append(("dash-wf", "err"))

# sanity on the mapping engine
from data import platforms_for_cartridge
print("3 mL compatible:", [p["variant"] for p in platforms_for_cartridge("3 mL")][:4])
print("1 mL PFS compatible:", [p["variant"] for p in platforms_for_cartridge("1 mL PFS")])
print("\nRESULT:", "ALL OK ✅" if not problems else f"{len(problems)} PROBLEM(S) ❌ {problems}")
