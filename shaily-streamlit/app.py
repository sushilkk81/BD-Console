"""
Shaily DDCP Partnership Console — Streamlit build.
Runs: streamlit run app.py
"""
from __future__ import annotations
import datetime as _dt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data as D

st.set_page_config(page_title="Shaily DDCP Console", page_icon="🧬",
                   layout="wide", initial_sidebar_state="collapsed")

# ────────────────────────────────────────────────────────────────────────────
# Theme injection — suppress Streamlit chrome, apply the Shaily identity
# ────────────────────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root{ --blue:#2F6E97; --blue-dk:#234F70; --green:#7DB343; --forest:#2E7D46;
       --orange:#E5883B; --gray:#6D6E71; --ink:#0E1B24; --ink2:#3A4C57;
       --muted:#6B7C86; --line:#DCE6E6; --surface:#FFFFFF; --bg:#F5F8F8; }
/* kill default streamlit chrome */
#MainMenu, header[data-testid="stHeader"], footer, .stDeployButton, [data-testid="stToolbar"]{display:none!important;}
.stApp{background:radial-gradient(1100px 520px at 88% -8%, #EAF1F6 0%, rgba(234,241,246,0) 60%), var(--bg);}
.block-container{padding-top:1.1rem;padding-bottom:3rem;max-width:1180px;}
html, body, [class*="css"]{font-family:'Figtree','Segoe UI',system-ui,sans-serif;color:var(--ink);}
h1,h2,h3,h4{font-family:'Figtree',sans-serif;letter-spacing:-.01em;}
.mono, .kpi .v, .spec{font-family:'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums;}

/* Shaily header */
.shdr{display:flex;align-items:center;gap:13px;padding:6px 2px 16px;border-bottom:1px solid var(--line);margin-bottom:18px;}
.shdr .mk{width:38px;height:38px;border-radius:10px;background:#fff;border:1px solid var(--line);
          box-shadow:0 1px 3px rgba(14,27,36,.14);display:grid;place-items:center;}
.shdr .nm{font-weight:800;font-size:18px;letter-spacing:.02em;color:var(--gray);line-height:1;}
.shdr .sub{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);}
.shdr .who{margin-left:auto;font-size:12.5px;color:var(--ink2);text-align:right;}
.shdr .who b{color:var(--ink);} .shdr .lock{font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:var(--muted);}
.eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--blue-dk);}

/* cards */
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
      box-shadow:0 1px 2px rgba(14,27,36,.05),0 8px 28px -14px rgba(14,27,36,.16);margin-bottom:6px;}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:15px 17px;position:relative;overflow:hidden;
     box-shadow:0 1px 2px rgba(14,27,36,.05);}
.kpi:before{content:"";position:absolute;left:0;top:0;height:100%;width:4px;background:var(--kc,var(--blue));}
.kpi .v{font-size:25px;font-weight:600;letter-spacing:-.02em;color:var(--ink);}
.kpi .l{font-size:11.5px;color:var(--muted);margin-top:2px;}

/* platform card */
.pcard{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--pc,var(--line));
       border-radius:13px;padding:15px 17px;margin-bottom:2px;}
.pcard .pn{font-weight:700;font-size:16px;}
.pcard .pt{font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-top:2px;}
.pcard .pd{color:var(--ink2);font-size:13px;margin-top:7px;}
.pcard .tags{margin-top:9px;} .pcard .tag{display:inline-block;font-family:'IBM Plex Mono',monospace;font-size:10.5px;
       color:var(--ink2);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:2px 7px;margin:0 5px 5px 0;}
.pcard .score{float:right;font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:600;color:var(--blue-dk);}
.best{display:inline-block;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;
      color:var(--blue-dk);background:#E7EFF5;padding:2px 8px;border-radius:20px;font-weight:600;margin-left:8px;}

/* severity chips */
.sev{display:inline-block;font-weight:600;font-size:12px;padding:4px 11px;border-radius:20px;}
.sev-minor{color:var(--forest);background:#E7F1E9;} .sev-moderate{color:var(--orange);background:#FBEEDD;}
.sev-major{color:#C0392B;background:#F9E4E1;}
.hl{border:1px solid var(--orange);background:#FBEEDD;border-radius:12px;padding:14px 16px;color:#8A5610;font-size:13px;}

/* section label */
.sub{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);
     margin:2px 0 12px;border-bottom:1px solid var(--line);padding-bottom:9px;}
.pill{font-family:'IBM Plex Mono',monospace;font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--ink2);}

/* nav buttons row: make Streamlit buttons look segmented */
div[data-testid="stHorizontalBlock"] .stButton>button{border-radius:9px;}
.stButton>button{font-weight:600;border-radius:10px;border:1px solid var(--line);}
.stButton>button[kind="primary"]{background:linear-gradient(150deg,var(--blue),var(--blue-dk));border:0;}

/* confidential watermark */
.wm{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.05;overflow:hidden;}
.wm span{position:absolute;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#1b3a4b;
         transform:rotate(-30deg);white-space:nowrap;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

PINWHEEL = ('<svg viewBox="0 0 48 48" width="30" height="30"><g transform="translate(24,24)">'
            '<rect x="-4.5" y="-19" width="9" height="15" rx="4.5" fill="#3D7CA6" transform="rotate(22)"/>'
            '<rect x="-4.5" y="-19" width="9" height="15" rx="4.5" fill="#7DB343" transform="rotate(112)"/>'
            '<rect x="-4.5" y="-19" width="9" height="15" rx="4.5" fill="#2E7D46" transform="rotate(202)"/>'
            '<rect x="-4.5" y="-19" width="9" height="15" rx="4.5" fill="#E5883B" transform="rotate(292)"/></g></svg>')

# ────────────────────────────────────────────────────────────────────────────
# Session state
# ────────────────────────────────────────────────────────────────────────────
ss = st.session_state
_defaults = dict(
    screen="gate", user=None, brand="Ozempic", strengths=[], market="US",
    sub_fy="FY26", sub_q="Q3", dossier_fy="FY27", viscosity="Like water", visc_val=None,
    visc_src="", container="", cont_src="", device=None, differentiated=False,
    platform=None, deviation=False, dropped=set(), severity=None, lead_override=None,
    access_role="Customer (select services)", dv_mode="Matrix / bracketing",
    svc_threshold=[], svc_ifu=[], svc_hf=[], wf_id="aw", wf_calls_extra={}, dash_tab="BD Manager",
)
for k, v in _defaults.items():
    ss.setdefault(k, v)


def goto(screen):
    ss.screen = screen


def header():
    who = ""
    if ss.user:
        who = (f'<div class="who"><b>{ss.user["name"]}</b> · {ss.user["role"]}'
               f'<div class="lock">🔒 Closed group · watermarked · {ss.user["email"]}</div></div>')
    st.markdown(
        f'<div class="shdr"><span class="mk">{PINWHEEL}</span>'
        f'<span><span class="nm">SHAILY</span><br><span class="sub">Medical Device Unit · DDCP Console</span></span>'
        f'{who}</div>', unsafe_allow_html=True)


def watermark():
    if not ss.user:
        return
    stamp = f'{ss.user["name"]} · {ss.user["email"]} · CONFIDENTIAL'
    spans = "".join(
        f'<span style="top:{r*130+20}px;left:{c*360-40}px">{stamp}</span>'
        for r in range(9) for c in range(5))
    st.markdown(f'<div class="wm">{spans}</div>', unsafe_allow_html=True)


def kpi(col, value, label, color):
    col.markdown(f'<div class="kpi" style="--kc:{color}"><div class="v mono">{value}</div>'
                 f'<div class="l">{label}</div></div>', unsafe_allow_html=True)


def section(t):
    st.markdown(f'<div class="sub">{t}</div>', unsafe_allow_html=True)


def brand_fig(fig, h=260):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Figtree, sans-serif", color="#3A4C57", size=12),
                      showlegend=False)
    return fig


# ────────────────────────────────────────────────────────────────────────────
# Screen: access gate
# ────────────────────────────────────────────────────────────────────────────
def screen_gate():
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        st.markdown(
            '<div class="card" style="background:linear-gradient(160deg,#0E1B24,#12303A 55%,#0A5651);color:#EAF2F1;'
            'border:0;min-height:430px;display:flex;flex-direction:column;justify-content:space-between;padding:34px;">'
            '<div><div class="eyebrow" style="color:#7FB3D6">Drug-Device Combination Product · Partnership Console</div>'
            '<h1 style="color:#fff;font-size:38px;line-height:1.05;margin:14px 0 0;">A <span style="color:#7FB3D6">head start</span><br>'
            'on the right device<br>partnership.</h1>'
            '<p style="color:#A9C3C1;margin-top:14px;max-width:40ch;">Engage Shaily early and move together — from first '
            'requirement to a costed, signable device proposal, before the programme clock starts.</p></div>'
            '<div style="display:flex;gap:26px;margin-top:26px;font-family:IBM Plex Mono,monospace;">'
            '<div><div style="font-size:24px;color:#fff">7</div><div style="font-size:10px;color:#7FA6A3;letter-spacing:.1em">DEVICE PLATFORMS</div></div>'
            '<div><div style="font-size:24px;color:#fff">&lt;3mo</div><div style="font-size:10px;color:#7FA6A3;letter-spacing:.1em">FASTEST DV ROUTE</div></div>'
            '<div><div style="font-size:24px;color:#fff">48h</div><div style="font-size:10px;color:#7FA6A3;letter-spacing:.1em">COMPARATIVE PACK</div></div>'
            '</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="eyebrow">Access the console</div>', unsafe_allow_html=True)
        st.markdown("### Identify yourself to begin")
        st.caption("Introduce yourself to open a secure, watermarked collaboration workspace with the Shaily BD desk.")
        name = st.text_input("Full name", placeholder="e.g. Dr. Anaya Mehta")
        role = st.selectbox("Role", ["Select your function…", "Pharma — Business Development",
                                     "Pharma — R&D / Formulation", "Pharma — Device / Packaging",
                                     "Pharma — Program Management", "Shaily — BD Manager", "Shaily — BD Workforce"])
        c1, c2 = st.columns(2)
        email = c1.text_input("Work email", placeholder="name@company.com")
        phone = c2.text_input("Contact number", placeholder="+91 / +1 …")
        agreed = st.checkbox("I accept the mutual Terms & Conditions and Non-Disclosure Agreement.")
        with st.expander("Read the mutual NDA / Terms & Conditions"):
            st.markdown(
                "**Mutual, two-way NDA** between Shaily Engineering Plastics Ltd. and the accessing organisation. "
                "All exchanged information — products, strengths, formulation data, device selections, timelines and "
                "pricing — is confidential, used solely to progress the device programme, disclosed to no third party, "
                "and restricted to named users. No screenshots or reproduction. Indicative pricing is non-binding at "
                "R&D stage. Confidentiality survives five (5) years. *(Demonstration text — final terms issued by Shaily Legal.)*")
        ok = len(name) > 1 and role != "Select your function…" and "@" in email and len(phone) > 5 and agreed
        if st.button("Agree & enter the workspace →", type="primary", use_container_width=True, disabled=not ok):
            ss.user = dict(name=name, role=role, email=email, phone=phone)
            goto("form")
            st.rerun()
        st.caption("🔒 Session bound to your email · Dynamically watermarked · Mutual NDA")

    # landing collage
    st.markdown("<br>", unsafe_allow_html=True)
    section("Shaily platform variants · seven self-injection platforms")
    cols = st.columns(4)
    for i, p in enumerate(D.PLATFORMS):
        with cols[i % 4]:
            tag = "Auto-Injector" if p["type"] == "Auto-Injector" else "Pen"
            st.markdown(
                f'<div class="card" style="text-align:center;min-height:150px;">'
                f'<div class="pill" style="color:{p["color"]}">{tag}</div>'
                f'<div style="font-size:34px;margin:8px 0">💉</div>'
                f'<div style="font-weight:700;font-size:13.5px">{p["name"]}</div>'
                f'<div style="font-size:11px;color:var(--muted);margin-top:3px">{" · ".join(p["tags"][:2])}</div></div>',
                unsafe_allow_html=True)

    section("How the programme runs · three phases")
    p1, p2, p3 = st.columns(3)
    phases = [
        (p1, "Phase 1", "Define & agree", ["User Requirement Specification", "Agreement", "Primary container compatibility"], "#3D7CA6"),
        (p2, "Phase 2", "De-risk & verify", ["Risk Assessment — D/A/P-FMEA", "Design Verification Package"], "#7DB343"),
        (p3, "Phase 3", "Submit", ["DHF submission", "DMF submission"], "#E5883B"),
    ]
    for col, num, title, steps, c in phases:
        items = "".join(f'<div style="padding:7px 0;border-top:1px dashed var(--line);font-size:12.5px">{s}</div>' for s in steps)
        col.markdown(f'<div class="card" style="border-top:4px solid {c}">'
                     f'<div class="eyebrow" style="color:{c}">{num}</div>'
                     f'<div style="font-weight:700;font-size:16px;margin:4px 0 8px">{title}</div>{items}</div>',
                     unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Console navigation
# ────────────────────────────────────────────────────────────────────────────
CONSOLE_STEPS = [("form", "1 · Request"), ("recommend", "2 · Platforms"),
                 ("mapping", "3 · Mapping"), ("cost", "4 · Cost & deal")]


def console_nav():
    cols = st.columns([1, 1, 1, 1, 0.2, 1.3])
    for i, (key, label) in enumerate(CONSOLE_STEPS):
        typ = "primary" if ss.screen == key else "secondary"
        if cols[i].button(label, key=f"nav_{key}", use_container_width=True, type=typ):
            goto(key); st.rerun()
    typ = "primary" if ss.screen == "dash" else "secondary"
    if cols[5].button("📊 BD Dashboards", key="nav_dash", use_container_width=True, type=typ):
        goto("dash"); st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Screen: request form
# ────────────────────────────────────────────────────────────────────────────
def screen_form():
    st.markdown('<div class="eyebrow">Step 01 · Customer request form</div>', unsafe_allow_html=True)
    st.markdown("## Tell us about the product")
    st.caption("Fill what you know. Anything not yet locked — viscosity, container, device type — can be auto-populated "
               "from public literature and is marked with its source.")

    ref = D.REFERENCE_PRODUCTS.get(ss.brand)
    with st.container(border=True):
        section("Reference product")
        c1, c2 = st.columns([1, 1])
        ss.brand = c1.selectbox("Reference product brand name", list(D.REFERENCE_PRODUCTS.keys()),
                                index=list(D.REFERENCE_PRODUCTS.keys()).index(ss.brand))
        ref = D.REFERENCE_PRODUCTS.get(ss.brand)
        ss.market = c2.selectbox("Target market", D.MARKETS, index=D.MARKETS.index(ss.market))
        if ref:
            st.caption(f"✓ Recognised — **{ref['molecule']}**. Device auto-set to **{ref['device']}**. "
                       f"Strengths and container can be auto-filled from literature.")
        # strengths / SKUs
        opts = ref["strengths"] if ref else []
        default = ss.strengths or opts
        ss.strengths = st.multiselect("Strength(s) / SKUs — dose strength as published (fill volume added by Shaily)",
                                      options=opts, default=[s for s in default if s in opts]) if opts else \
            [s.strip() for s in st.text_input("Strengths (comma separated)", ", ".join(ss.strengths)).split(",") if s.strip()]

    with st.container(border=True):
        section("Fill, container & device")
        c1, c2 = st.columns(2)
        with c1:
            ss.viscosity = st.radio("Viscosity", ["Like water", "Higher"],
                                    index=0 if ss.viscosity == "Like water" else 1, horizontal=True)
            if ss.viscosity == "Higher":
                ss.visc_val = st.number_input("Actual viscosity (cP)", min_value=0.0, step=0.5,
                                              value=float(ss.visc_val or (ref["visc_val"] if ref else 8.0)))
            if st.button("Auto-populate viscosity from literature", key="auto_visc"):
                if ref:
                    ss.viscosity = "Higher" if ref["visc"] == "higher" else "Like water"
                    ss.visc_val = ref["visc_val"]
                    ss.visc_src = f"DailyMed SmPC / published rheology data for {ss.brand} ({ref['molecule']})"
                st.rerun()
            if ss.visc_src:
                st.caption(f"*Auto-populated · source: {ss.visc_src}. Verify before submission.*")
        with c2:
            cont_opts = ["— select / auto-populate —"] + D.CONTAINER_OPTIONS
            cur = ss.container if ss.container in D.CONTAINER_OPTIONS else "— select / auto-populate —"
            ss.container = st.selectbox("Primary container configuration", cont_opts, index=cont_opts.index(cur))
            if ss.container == "— select / auto-populate —":
                ss.container = ""
            if st.button("Auto-populate container (deep search)", key="auto_cont"):
                if ref:
                    ss.container = ref["container"]
                    ss.cont_src = f"NDC / DailyMed + EMA packaging record for {ss.brand}"
                st.rerun()
            if ss.cont_src and ss.container:
                st.caption(f"*Auto-populated · sources (top 3): {ss.cont_src}; FDA Orange Book; ClinicalTrials.gov. Editable by BD or customer.*")

        c3, c4 = st.columns(2)
        ss.differentiated = c3.toggle("Differentiated formulation (override device type)", value=ss.differentiated)
        auto_dev = ref["device"] if ref else "Pen Injector"
        if ss.differentiated:
            ss.device = c4.radio("Device type", ["Pen Injector", "Auto-Injector"],
                                 index=0 if (ss.device or auto_dev) == "Pen Injector" else 1, horizontal=True)
        else:
            ss.device = auto_dev
            c4.markdown(f'<div style="margin-top:26px" class="pill">Device: {auto_dev} · auto from RLD</div>',
                        unsafe_allow_html=True)

    with st.container(border=True):
        section("Programme timing")
        c1, c2, c3 = st.columns(3)
        ss.sub_fy = c1.selectbox("Submission-batch FY", D.FY_OPTIONS, index=D.FY_OPTIONS.index(ss.sub_fy))
        ss.sub_q = c2.selectbox("Submission quarter", D.QUARTERS, index=D.QUARTERS.index(ss.sub_q))
        ss.dossier_fy = c3.selectbox("Dossier submission FY", D.FY_OPTIONS, index=D.FY_OPTIONS.index(ss.dossier_fy))

    disabled = not (ss.strengths and ss.container and ss.device)
    if disabled:
        st.info("Select at least one strength, a container (or auto-populate it), and a device type to continue.")
    if st.button("Match device platforms →", type="primary", disabled=disabled):
        goto("recommend"); st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Screen: recommendations
# ────────────────────────────────────────────────────────────────────────────
def screen_recommend():
    st.markdown('<div class="eyebrow">Step 02 · Platform match</div>', unsafe_allow_html=True)
    st.markdown("## Shaily platforms, ranked for your brief")
    ref = D.REFERENCE_PRODUCTS.get(ss.brand)
    visc = "higher" if ss.viscosity == "Higher" else "water"
    ranked = D.rank_platforms(ss.device, ss.container, visc, ref["dose"] if ref else None)

    for idx, (p, score, reasons) in enumerate(ranked):
        best = '<span class="best">Best fit</span>' if idx == 0 else ""
        tags = "".join(f'<span class="tag">{t}</span>' for t in p["tags"])
        c1, c2 = st.columns([5, 1])
        c1.markdown(
            f'<div class="pcard" style="--pc:{p["color"]}"><span class="score">{score}</span>'
            f'<div class="pn">{p["name"]}{best}</div>'
            f'<div class="pt">{p["type"]} · {p["dose"]} dose · rank {idx+1:02d}</div>'
            f'<div class="pd">{p["desc"]}</div><div class="tags">{tags}</div></div>', unsafe_allow_html=True)
        with c2:
            st.write("")
            if st.button("Select", key=f"pick_{p['id']}", use_container_width=True,
                         type="primary" if ss.platform and ss.platform["id"] == p["id"] else "secondary"):
                ss.platform = p
                ss.deviation = idx != 0
                ss.dropped = set()
                st.rerun()

    if ss.platform:
        if ss.deviation:
            st.markdown(f'<div class="hl">You deviated from the top-ranked <b>{ranked[0][0]["name"]}</b> to '
                        f'<b>{ss.platform["name"]}</b>. Tooling impact and timeline are mapped on the next step.</div>',
                        unsafe_allow_html=True)
        if st.button("Map SKUs & timeline →", type="primary"):
            goto("mapping"); st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Screen: mapping & timeline
# ────────────────────────────────────────────────────────────────────────────
def _severity():
    visc = "higher" if ss.viscosity == "Higher" else "water"
    return D.severity_for(ss.platform, ss.device, ss.container, visc, ss.deviation)


def screen_mapping():
    if not ss.platform:
        st.warning("Pick a platform first."); return
    sev, mods, drivers = _severity()
    ss.severity = sev
    st.markdown('<div class="eyebrow">Step 03 · Mapping & timeline</div>', unsafe_allow_html=True)
    st.markdown(f"## {ss.platform['name']} — SKU mapping")

    stop = D.STOPPERS.get(ss.container, list(D.STOPPERS.values())[0])
    fill = ss.container.split("·")[1].strip() if "·" in ss.container else "—"
    cart = ss.container.split("·")[0].strip()

    active = [s for i, s in enumerate(ss.strengths) if i not in ss.dropped]
    rows = [dict((("SKU", f"SKU {i+1:02d}"), ("Strength", s), ("Container", cart), ("Fill", fill),
                  ("Stopper A", stop["a"]), ("Stopper B", stop["b"]), ("Dims", stop["dims"]),
                  ("Change", D.SEV_LABEL[sev]))) for i, s in enumerate(active)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # SKU elimination (Modify)
    with st.expander("Modify SKUs — eliminate a strength"):
        for i, s in enumerate(ss.strengths):
            keep = st.checkbox(f"Include {s}", value=i not in ss.dropped, key=f"keep_{i}")
            if keep and i in ss.dropped:
                ss.dropped.discard(i)
            elif not keep and i not in ss.dropped:
                ss.dropped.add(i)

    section("Standard development timelines — driven by tooling change")
    tcols = st.columns(3)
    for col, s in zip(tcols, ["minor", "moderate", "major"]):
        governing = s == sev
        border = {"minor": "#2E7D46", "moderate": "#E5883B", "major": "#C0392B"}[s]
        ring = "box-shadow:0 0 0 2px var(--blue);" if governing else ""
        gov = '<div class="pill" style="margin-top:8px;color:var(--blue-dk)">◆ Governing route</div>' if governing else ""
        col.markdown(f'<div class="card" style="border-top:3px solid {border};{ring}">'
                     f'<div class="mono" style="font-size:28px;color:{border}">{D.TIMELINE[s]}<span style="font-size:13px">mo</span></div>'
                     f'<div style="font-weight:600;margin-top:2px">{D.SEV_LABEL[s]}</div>'
                     f'<div style="font-size:12px;color:var(--ink2);margin-top:5px">{D.SEV_LOGIC[s]}</div>{gov}</div>',
                     unsafe_allow_html=True)

    # moderate-change distinct highlight (per brief)
    if sev == "moderate":
        st.markdown('<div class="hl" style="margin-top:14px"><b>Moderate change flagged.</b> Up to two tool modifications '
                    f'followed by tool validation — drivers: {", ".join(drivers)}. Standard timeline 6 months; DV package 250K USD/SKU.</div>',
                    unsafe_allow_html=True)

    if st.button("Proceed to cost →", type="primary"):
        goto("cost"); st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Screen: cost & service selection
# ────────────────────────────────────────────────────────────────────────────
def screen_cost():
    if not ss.platform or not ss.severity:
        st.warning("Complete mapping first."); return
    sev = ss.severity
    active = [s for i, s in enumerate(ss.strengths) if i not in ss.dropped]
    n = len(active)
    st.markdown('<div class="eyebrow">Step 04 · Tentative cost & deal</div>', unsafe_allow_html=True)
    st.markdown("## Costed DV package")

    ss.access_role = st.radio("Access mode", ["Customer (select services)", "BD (edit all costs)"],
                              index=0 if ss.access_role.startswith("Customer") else 1, horizontal=True)
    is_bd = ss.access_role.startswith("BD")

    left, right = st.columns([1.4, 1])
    # --- service selection ---
    with left:
        with st.container(border=True):
            section("Product design-verification approach")
            std_dv = D.PKG[sev]
            if is_bd:
                std_dv = st.number_input("Governing DV package (K USD)", min_value=0, value=int(ss.lead_override or D.PKG[sev]), step=10)
                ss.lead_override = std_dv
            else:
                st.markdown(f'<div class="card">Standard platform DV · **{D.SEV_LABEL[sev]}** — '
                            f'<span class="mono">${std_dv}K USD</span></div>', unsafe_allow_html=True)

            ss.dv_mode = st.radio("Deliverable-volume DV strategy", ["Individual DV per SKU", "Matrix / bracketing"],
                                  index=0 if ss.dv_mode.startswith("Individual") else 1, horizontal=True)
            if ss.dv_mode.startswith("Matrix") and n >= 2:
                low, high = active[0], active[-1]
                excluded = active[1:-1]
                dv_cost = std_dv + D.ADD_DV  # bracket = 2 variants (low + high)
                st.markdown(
                    f'<div class="card"><b>Matrix bracketing map</b><br>'
                    f'<span class="mono">◄ {low}</span> &nbsp;⟷&nbsp; <span class="mono">{high} ►</span> '
                    f'— 2 bracket variants verified (low + high deliverable volume).<br>'
                    f'<span style="color:var(--muted);font-size:12.5px">Excluded (covered by bracket): '
                    f'{", ".join(excluded) if excluded else "none"}</span></div>', unsafe_allow_html=True)
                st.caption("Standard-condition testing (ISO 11608): " + " · ".join(D.STD_CONDITION_TESTS))
            else:
                dv_cost = std_dv + D.ADD_DV * max(0, n - 1)
                st.caption(f"Individual DV: governing package + {max(0,n-1)} × ${D.ADD_DV}K bracketed SKUs.")

        with st.container(border=True):
            section("Other service selections")
            ss.svc_threshold = st.multiselect(f"Threshold analysis — ${D.SERVICES['threshold']:,}/variant", active, default=ss.svc_threshold)
            ss.svc_ifu = st.multiselect(f"IFU per variant — ${D.SERVICES['ifu']:,}/variant", active, default=ss.svc_ifu)
            ss.svc_hf = st.multiselect(f"Human factor — ${D.SERVICES['human_factor']:,}/variant (excl. RLD cost)", active, default=ss.svc_hf)

    # --- totals ---
    dv_usd = dv_cost * 1000
    thr = len(ss.svc_threshold) * D.SERVICES["threshold"]
    ifu = len(ss.svc_ifu) * D.SERVICES["ifu"]
    hf = len(ss.svc_hf) * D.SERVICES["human_factor"]
    total = dv_usd + thr + ifu + hf
    with right:
        with st.container(border=True):
            section("Total package")
            def line(a, b):
                st.markdown(f'<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--line);font-size:13.5px">'
                            f'<span>{a}</span><span class="mono">{b}</span></div>', unsafe_allow_html=True)
            line(f"DV package ({ss.dv_mode.split(' ')[0]})", f"${dv_usd:,.0f}")
            line(f"Threshold × {len(ss.svc_threshold)}", f"${thr:,.0f}")
            line(f"IFU × {len(ss.svc_ifu)}", f"${ifu:,.0f}")
            line(f"Human factor × {len(ss.svc_hf)}", f"${hf:,.0f}")
            st.markdown(f'<div style="margin-top:12px;padding-top:12px;border-top:2px solid var(--ink);display:flex;'
                        f'justify-content:space-between;align-items:baseline"><b>Tentative package</b>'
                        f'<span class="mono" style="font-size:26px;color:var(--blue-dk)">${total:,.0f}</span></div>',
                        unsafe_allow_html=True)
            st.caption(f"{n} active SKU(s) · {D.TIMELINE[sev]}-month governing timeline · fully customizable")

        with st.container(border=True):
            section("Negotiate / discuss")
            st.text_area("Comment for the Shaily BD desk", key="neg_comment",
                         placeholder="e.g. Can we bracket SKU 2–3 into one DV? Target 220K all-in.")
            urg = st.radio("Urgency", ["Level 1 · call back today", "Level 2 · call back this week"], index=0)
            if st.button("Send to Shaily BD", type="primary", use_container_width=True):
                st.success(f"Sent · {urg}. A BD manager will follow up accordingly.")

    st.caption("💡 Comparative cost & device-performance assessment is a special request — auto-populated within 48 h in the production build.")


# ────────────────────────────────────────────────────────────────────────────
# Screen: BD dashboards
# ────────────────────────────────────────────────────────────────────────────
def screen_dash():
    ss.dash_tab = st.radio("Dashboard", ["BD Manager", "Workforce view"],
                           index=0 if ss.dash_tab == "BD Manager" else 1, horizontal=True, label_visibility="collapsed")
    if ss.dash_tab == "BD Manager":
        dash_manager()
    else:
        dash_workforce()


def dash_manager():
    st.markdown('<div class="eyebrow">BD Manager · Portfolio overview</div>', unsafe_allow_html=True)
    st.markdown("## Pipeline & commercial opportunity")
    total_opp = sum(e["opp_m"] for e in D.ENGAGEMENTS)
    weighted = sum(e["opp_m"] * D.STAGE_PROB[e["stage"]] for e in D.ENGAGEMENTS)
    avg_prompt = round(sum(w["promptness"] for w in D.WORKFORCE) / len(D.WORKFORCE))
    k = st.columns(4)
    kpi(k[0], len(D.ENGAGEMENTS), "Active engagements", "#3D7CA6")
    kpi(k[1], f"${total_opp}M", "Pipeline opportunity", "#7DB343")
    kpi(k[2], f"${weighted:.1f}M", "Weighted (stage-adj.)", "#E5883B")
    kpi(k[3], f"{avg_prompt}%", "Avg promptness", "#2E7D46")

    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            section("Engagements by region")
            by_region = {}
            for w in D.WORKFORCE:
                by_region[w["region"]] = by_region.get(w["region"], 0) + w["engagements"]
            fig = go.Figure(go.Bar(x=list(by_region.values()), y=list(by_region.keys()), orientation="h",
                                   marker_color=[D.REGION_COLOR.get(r, "#3D7CA6") for r in by_region],
                                   text=list(by_region.values()), textposition="outside"))
            fig.update_xaxes(visible=False)
            st.plotly_chart(brand_fig(fig, 240), use_container_width=True)
    with c2:
        with st.container(border=True):
            section("Pipeline by stage")
            by_stage = {}
            for e in D.ENGAGEMENTS:
                by_stage[e["stage"]] = by_stage.get(e["stage"], 0) + 1
            labels = [s for s in D.STAGE_ORDER if s in by_stage]
            fig = go.Figure(go.Pie(labels=labels, values=[by_stage[s] for s in labels], hole=0.62,
                                   marker_colors=[D.STAGE_COLOR[s] for s in labels], sort=False))
            fig.update_traces(textinfo="value")
            st.plotly_chart(brand_fig(fig, 240), use_container_width=True)

    with st.container(border=True):
        section("Customer engagements & commercial opportunity")
        df = pd.DataFrame([dict(Customer=e["customer"], Product=e["product"], SKUs=e["skus"],
                                Platform=e["platform"], Opportunity=f"${e['opp_m']}M", Volume=f"{e['volume_m']} Mn",
                                Submission=f"{e['sub_fy']} {e['sub_q']}",
                                **{"Commercial FY": D.commercial_fy(e["sub_fy"], e["sub_q"])},
                                Market=e["market"], Stage=e["stage"], Owner=e["owner"]) for e in D.ENGAGEMENTS])
        st.dataframe(df, use_container_width=True, hide_index=True)

    c3, c4 = st.columns(2)
    with c3:
        with st.container(border=True):
            section("IP landscape — Orange Book (market entry)")
            for m in sorted({e["market"] for e in D.ENGAGEMENTS}):
                ip = D.IP_LANDSCAPE.get(m, dict(patents="—", earliest="—", note=""))
                st.markdown(f'<div style="display:flex;gap:12px;padding:9px 0;border-top:1px solid var(--line)">'
                            f'<div style="text-align:center;min-width:42px"><div class="mono" style="font-size:19px;color:#C0392B">{ip["patents"]}</div>'
                            f'<div style="font-size:9px;color:var(--muted)">PATENTS</div></div>'
                            f'<div><b>{m} · earliest entry {ip["earliest"]}</b>'
                            f'<div style="font-size:12px;color:var(--muted)">{ip["note"]}</div></div></div>', unsafe_allow_html=True)
            st.caption("🔎 Orange Book patent landscape auto-evaluated per target market in the background.")
    with c4:
        with st.container(border=True):
            section("Industry events")
            for ev in D.EVENTS:
                st.markdown(f'<div style="display:flex;gap:12px;align-items:center;padding:9px 0;border-top:1px solid var(--line)">'
                            f'<div class="pill" style="min-width:64px;text-align:center">{ev["date"]}</div>'
                            f'<div><b>{ev["name"]}</b><div style="font-size:12px;color:var(--muted)">{ev["city"]}</div></div>'
                            f'<div style="margin-left:auto;color:var(--orange);font-size:11px;font-family:IBM Plex Mono,monospace">{ev["tag"]}</div></div>',
                            unsafe_allow_html=True)

    with st.container(border=True):
        section("Regional workforce roster")
        rcols = st.columns(4)
        for i, w in enumerate(D.WORKFORCE):
            with rcols[i % 4]:
                st.markdown(f'<div class="card" style="margin-bottom:10px"><div style="font-weight:700">{w["name"]}</div>'
                            f'<div class="pill">{w["region"]}</div>'
                            f'<div style="display:flex;gap:16px;margin-top:8px;font-size:11.5px;color:var(--muted)">'
                            f'<div>Engag.<div class="mono" style="font-size:15px;color:var(--ink)">{w["engagements"]}</div></div>'
                            f'<div>Prompt<div class="mono" style="font-size:15px;color:var(--ink)">{w["promptness"]}%</div></div></div></div>',
                            unsafe_allow_html=True)


def dash_workforce():
    st.markdown('<div class="eyebrow">Workforce · Individual performance</div>', unsafe_allow_html=True)
    st.markdown("## My engagements & customer relationships")
    names = {w["id"]: f'{w["name"]} — {w["region"]}' for w in D.WORKFORCE}
    ss.wf_id = st.selectbox("Signed-in representative", list(names.keys()),
                            format_func=lambda x: names[x], index=list(names.keys()).index(ss.wf_id))
    w = next(x for x in D.WORKFORCE if x["id"] == ss.wf_id)
    calls = ss.wf_calls_extra.get(w["id"], []) + w["calls"]
    w_eff = dict(w, calls=calls)
    rel = D.relationship_score(w_eff)
    k = st.columns(4)
    kpi(k[0], w["engagements"], "Customer engagements", "#3D7CA6")
    kpi(k[1], f"${w['engagements']*2.4:.1f}M", "Opportunity created", "#7DB343")
    kpi(k[2], f"{w['promptness']}%", "Promptness (Teams)", "#E5883B")
    kpi(k[3], rel, "Relationship score", "#2E7D46")

    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            section("Calls logged (recent weeks)")
            weeks = ["W-5", "W-4", "W-3", "W-2", "W-1", "This wk"]
            vals = [0, 0, 0, 0, 0, 0]
            for i in range(min(len(calls), 6)):
                vals[5 - i] += 1
            fig = go.Figure(go.Bar(x=weeks, y=vals, marker_color="#3D7CA6"))
            fig.update_yaxes(visible=False)
            st.plotly_chart(brand_fig(fig, 230), use_container_width=True)
    with c2:
        with st.container(border=True):
            section("Log a customer call")
            cust = st.text_input("Customer", key="call_cust", placeholder="e.g. Aurora Biologics")
            ctx = st.text_input("Context (one line)", key="call_ctx", placeholder="e.g. Discussed Neo sampling for 4 SKUs")
            if st.button("Log call & update score", type="primary"):
                if ctx.strip():
                    ss.wf_calls_extra.setdefault(w["id"], []).insert(
                        0, (_dt.date.today().isoformat(), (f"{cust} — " if cust.strip() else "") + ctx.strip()))
                    st.rerun()
                else:
                    st.warning("Add a one-line context to log the call.")
            st.caption("📎 Meetings auto-sync from Microsoft Teams in the production build.")

    with st.container(border=True):
        section("Call log & relationship score")
        if calls:
            st.dataframe(pd.DataFrame([{"Date": d, "Context": c} for d, c in calls]),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("No calls logged yet.")


# ────────────────────────────────────────────────────────────────────────────
# Router
# ────────────────────────────────────────────────────────────────────────────
watermark()
header()

if ss.screen == "gate":
    screen_gate()
else:
    console_nav()
    st.write("")
    {"form": screen_form, "recommend": screen_recommend, "mapping": screen_mapping,
     "cost": screen_cost, "dash": screen_dash}.get(ss.screen, screen_form)()

st.markdown('<div style="text-align:center;color:var(--muted);font-family:IBM Plex Mono,monospace;font-size:11px;'
            'margin-top:34px;letter-spacing:.05em">SHAILY ENGINEERING PLASTICS · MEDICAL DEVICE UNIT · DDCP CONSOLE · '
            'PHASE I · CONFIDENTIAL</div>', unsafe_allow_html=True)
