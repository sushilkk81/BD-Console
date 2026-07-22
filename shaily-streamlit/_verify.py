"""Headless verification: run each screen via Streamlit's AppTest and report exceptions."""
from streamlit.testing.v1 import AppTest

def run(screen, extra=None):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["user"] = dict(name="Priya Rao", role="Shaily — BD Manager",
                                    email="priya@shaily.com", phone="+911234567")
    at.session_state["screen"] = screen
    at.session_state["brand"] = "Ozempic"
    at.session_state["strengths"] = ["0.25 mg", "0.5 mg", "1 mg", "2 mg"]
    at.session_state["container"] = "3 mL cartridge · 1.5 mL fill"
    at.session_state["device"] = "Pen Injector"
    at.session_state["viscosity"] = "Like water"
    from data import PLATFORMS
    at.session_state["platform"] = PLATFORMS[0]
    at.session_state["severity"] = "moderate"
    if extra:
        for kk, vv in extra.items():
            at.session_state[kk] = vv
    at.run()
    err = str(at.exception) if at.exception else None
    print(f"[{screen:9}] exception: {err if err else 'none'}")
    return err

problems = []
# gate needs no user
at = AppTest.from_file("app.py", default_timeout=60); at.run()
print(f"[gate     ] exception: {at.exception if at.exception else 'none'}")
if at.exception: problems.append(("gate", at.exception))

for s in ["form", "recommend", "mapping", "cost", "dash"]:
    e = run(s)
    if e: problems.append((s, e))

# dashboard workforce tab + matrix cost
e = run("dash", {"dash_tab": "Workforce view"}); problems.append(("dash-wf", e)) if e else None
e = run("cost", {"dv_mode": "Matrix / bracketing", "access_role": "BD (edit all costs)"})
if e: problems.append(("cost-bd", e))

print("\nRESULT:", "ALL SCREENS OK ✅" if not problems else f"{len(problems)} PROBLEM(S) ❌ {problems}")
