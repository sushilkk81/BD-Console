"""Shaily DDCP Partnership Console — Streamlit build.  Run: streamlit run app.py"""
from __future__ import annotations
import base64
import datetime as _dt
import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data as D

_HERE = os.path.dirname(os.path.abspath(__file__))
_LOGO_PNG = os.path.join(_HERE, "assets", "shaily-logo.png")

st.set_page_config(page_title="Shaily DDCP Console", page_icon="🧬",
                   layout="wide", initial_sidebar_state="collapsed")

# ────────────────────────────────────────────────────────────────────────────
# Theme
# ────────────────────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root{ --blue:#2F6E97; --blue-dk:#234F70; --green:#7DB343; --forest:#2E7D46;
       --orange:#E5883B; --gray:#6D6E71; --ink:#0E1B24; --ink2:#3A4C57;
       --muted:#6B7C86; --line:#DCE6E6; --surface:#FFFFFF; --bg:#F5F8F8; }
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"]{display:none!important;}
.stApp{background:radial-gradient(1100px 520px at 88% -8%, #EAF1F6 0%, rgba(234,241,246,0) 60%), var(--bg);}
.block-container{padding-top:1.1rem;padding-bottom:3rem;max-width:1200px;}
html, body, [class*="css"]{font-family:'Figtree','Segoe UI',system-ui,sans-serif;color:var(--ink);}
h1,h2,h3,h4{font-family:'Figtree',sans-serif;letter-spacing:-.01em;}
.mono,.kpi .v,.spec{font-family:'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums;}
.shdr{display:flex;align-items:center;gap:13px;padding:6px 2px 15px;border-bottom:1px solid var(--line);margin-bottom:16px;}
.shdr .mk{width:40px;height:40px;border-radius:10px;background:#fff;border:1px solid var(--line);box-shadow:0 1px 3px rgba(14,27,36,.14);display:grid;place-items:center;}
.shdr .nm{font-weight:800;font-size:18px;letter-spacing:.02em;color:var(--gray);line-height:1;}
.shdr .sub{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);}
.shdr .who{margin-left:auto;font-size:12.5px;color:var(--ink2);text-align:right;}
.shdr .who b{color:var(--ink);} .shdr .lock{font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:var(--muted);}
.eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--blue-dk);}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:17px 19px;box-shadow:0 1px 2px rgba(14,27,36,.05),0 8px 28px -14px rgba(14,27,36,.16);margin-bottom:6px;}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:15px 17px;position:relative;overflow:hidden;box-shadow:0 1px 2px rgba(14,27,36,.05);}
.kpi:before{content:"";position:absolute;left:0;top:0;height:100%;width:4px;background:var(--kc,var(--blue));}
.kpi .v{font-size:25px;font-weight:600;letter-spacing:-.02em;color:var(--ink);} .kpi .l{font-size:11.5px;color:var(--muted);margin-top:2px;}
.sub{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin:2px 0 12px;border-bottom:1px solid var(--line);padding-bottom:9px;}
.pill{font-family:'IBM Plex Mono',monospace;font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--ink2);}
.hl{border:1px solid var(--orange);background:#FBEEDD;border-radius:12px;padding:14px 16px;color:#8A5610;font-size:13px;}
.opttag{display:inline-block;font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;letter-spacing:.06em;
        color:#fff;background:var(--blue);border-radius:7px;padding:3px 10px;margin-bottom:8px;}
.opttag.o2{background:var(--forest);} .opttag.o3{background:var(--orange);}
/* Buttons & segmented control: blue, non-vanishing */
.stButton>button{font-weight:600;border-radius:10px;border:1px solid var(--line);background:#fff;color:var(--ink2);}
.stButton>button:hover{border-color:var(--blue);color:var(--blue-dk);background:#EAF1F6;}
.stButton>button[kind="primary"]{background:linear-gradient(150deg,var(--blue),var(--blue-dk));border:0;color:#fff;}
div[data-testid="stSegmentedControl"] button{border:1px solid var(--line)!important;background:#fff!important;color:var(--ink2)!important;font-weight:600;}
div[data-testid="stSegmentedControl"] button:hover{background:#EAF1F6!important;color:var(--blue-dk)!important;}
div[data-testid="stSegmentedControl"] button[aria-checked="true"]{background:var(--blue)!important;color:#fff!important;border-color:var(--blue)!important;}
.wm{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.05;overflow:hidden;}
.wm span{position:absolute;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#1b3a4b;transform:rotate(-30deg);white-space:nowrap;}
/* Light-widget safety net (real theme comes from .streamlit/config.toml) */
.stTextInput input,.stNumberInput input,.stTextArea textarea{background:#fff!important;color:#0E1B24!important;border:1px solid var(--line)!important;}
div[data-baseweb="select"]>div{background:#fff!important;color:#0E1B24!important;border-color:var(--line)!important;}
[data-baseweb="tag"]{background:var(--blue)!important;color:#fff!important;}
[data-baseweb="popover"] li{background:#fff!important;color:#0E1B24!important;}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] *{color:#3A4C57!important;}
label,.stMarkdown p{color:var(--ink2);}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Geometric Shaily "S" mark — fallback when the official PNG is not present.
SMARK = ('<svg viewBox="0 0 118 126" width="30" height="30">'
         '<path d="M6 6 H60 L38 44 H6 Z" fill="#8CC63F"/>'
         '<path d="M50 6 H100 a12 12 0 0 1 12 12 V44 H72 Z" fill="#2E7DA6"/>'
         '<path d="M6 82 H60 L38 120 H6 Z" fill="#EC6E39"/>'
         '<path d="M66 48 H112 V108 a12 12 0 0 1 -12 12 H80 L58 82 H66 Z" fill="#00693E"/></svg>')


def logo_block() -> str:
    """Use the official PNG (assets/shaily-logo.png) if present, else the S-mark SVG."""
    if os.path.exists(_LOGO_PNG):
        with open(_LOGO_PNG, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return (f'<img src="data:image/png;base64,{b64}" style="height:40px" alt="Shaily"/>'
                f'<span class="sub" style="margin-left:12px">Medical Device Unit · DDCP Console</span>')
    return (f'<span class="mk">{SMARK}</span>'
            f'<span><span class="nm">SHAILY</span><br>'
            f'<span class="sub">Medical Device Unit · DDCP Console</span></span>')

# ────────────────────────────────────────────────────────────────────────────
# State
# ────────────────────────────────────────────────────────────────────────────
ss = st.session_state
_defaults = dict(
    screen="gate", user=None, is_shaily=False, brand="Ozempic", strengths=[], market="US",
    sub_fy="FY26", sub_q="Q3", dossier_fy="FY27", visc_val=None, visc_ref="",
    device=None, differentiated=False, sku_rows=None, chosen_option=1,
    per_sku_services=None, access_role="Customer", wf_id="mah", dash_tab="BD Manager",
)
for k, v in _defaults.items():
    ss.setdefault(k, v)


def header():
    c_logo, c_title, c_who = st.columns([1.5, 3.6, 3.4], vertical_alignment="center")
    with c_logo:
        if os.path.exists(_LOGO_PNG):
            st.image(_LOGO_PNG, width=190)   # official logo (mark + wordmark)
        else:
            st.markdown(f'<div class="mk" style="width:42px;height:42px">{SMARK}</div>', unsafe_allow_html=True)
    with c_title:
        st.markdown('<div class="sub" style="border:none;margin:0;padding:0">Medical Device Unit · DDCP Console</div>',
                    unsafe_allow_html=True)
    with c_who:
        if ss.user:
            st.markdown(f'<div class="who" style="text-align:right"><b>{ss.user["name"]}</b> · {ss.user["role"]}'
                        f'<div class="lock">🔒 Closed group · watermarked · {ss.user["email"]}</div></div>',
                        unsafe_allow_html=True)
            lc = st.columns([2, 1])
            if lc[1].button("Log out", key="logout_btn", use_container_width=True):
                ss.clear()
                st.rerun()
    st.markdown('<hr style="margin:4px 0 14px;border:none;border-top:1px solid var(--line)">', unsafe_allow_html=True)


def watermark():
    if not ss.user:
        return
    stamp = f'{ss.user["name"]} · {ss.user["email"]} · CONFIDENTIAL'
    spans = "".join(f'<span style="top:{r*130+20}px;left:{c*360-40}px">{stamp}</span>'
                    for r in range(9) for c in range(5))
    st.markdown(f'<div class="wm">{spans}</div>', unsafe_allow_html=True)


def kpi(col, value, label, color):
    col.markdown(f'<div class="kpi" style="--kc:{color}"><div class="v mono">{value}</div>'
                 f'<div class="l">{label}</div></div>', unsafe_allow_html=True)


def section(t):
    st.markdown(f'<div class="sub">{t}</div>', unsafe_allow_html=True)


def brand_fig(fig, h=260, legend=False):
    fig.update_layout(height=h, margin=dict(l=6, r=6, t=8, b=6), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Figtree, sans-serif", color="#3A4C57", size=12),
                      showlegend=legend, legend=dict(orientation="h", y=-0.15))
    return fig


def active_skus():
    return [r for r in (ss.sku_rows or []) if r.get("Strength")]


# ────────────────────────────────────────────────────────────────────────────
# Gate  (role decides landing: Shaily → dashboard; pharma → request form)
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
            'requirement to a costed, signable device proposal.</p></div>'
            '<div style="display:flex;gap:26px;margin-top:26px;font-family:IBM Plex Mono,monospace;">'
            '<div><div style="font-size:24px;color:#fff">9</div><div style="font-size:10px;color:#7FA6A3">PLATFORM VARIANTS</div></div>'
            '<div><div style="font-size:24px;color:#fff">&lt;3mo</div><div style="font-size:10px;color:#7FA6A3">FASTEST DV</div></div>'
            '<div><div style="font-size:24px;color:#fff">48h</div><div style="font-size:10px;color:#7FA6A3">COMPARATIVE PACK</div></div>'
            '</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="eyebrow">Access the console</div>', unsafe_allow_html=True)
        st.markdown("### Identify yourself to begin")
        name = st.text_input("Full name", placeholder="e.g. Dr. Anaya Mehta")
        role = st.selectbox("Role", ["Select your function…", "Shaily — BD Manager", "Shaily — BD Workforce",
                                     "Pharma — Business Development", "Pharma — R&D / Formulation",
                                     "Pharma — Device / Packaging", "Pharma — Program Management"])
        c1, c2 = st.columns(2)
        email = c1.text_input("Work email", placeholder="name@company.com")
        phone = c2.text_input("Contact number", placeholder="+91 / +1 …")
        agreed = st.checkbox("I accept the mutual Terms & Conditions and NDA.")
        with st.expander("Read the mutual NDA / Terms & Conditions"):
            st.markdown("**Mutual, two-way NDA** between Shaily Engineering Plastics Ltd. and the accessing "
                        "organisation. All exchanged information is confidential, used solely to progress the "
                        "programme, disclosed to no third party, and restricted to named users. No screenshots. "
                        "Indicative pricing is non-binding at R&D stage. Confidentiality survives five (5) years.")
        ok = len(name) > 1 and role != "Select your function…" and "@" in email and len(phone) > 5 and agreed
        if st.button("Agree & enter →", type="primary", use_container_width=True, disabled=not ok):
            ss.user = dict(name=name, role=role, email=email, phone=phone)
            ss.is_shaily = role.startswith("Shaily")
            if "BD Manager" in role:
                ss.screen, ss.dash_tab = "dash", "BD Manager"
            elif "BD Workforce" in role:
                ss.screen, ss.dash_tab = "dash", "Workforce view"
            else:
                ss.screen = "form"
            st.rerun()
        st.caption("🔒 Session bound to your email · Watermarked · Mutual NDA · BD roles open the dashboard directly")


# ────────────────────────────────────────────────────────────────────────────
# Navigation
# ────────────────────────────────────────────────────────────────────────────
PHARMA_STEPS = [("form", "1 · Request"), ("options", "2 · Platform options"), ("cost", "3 · Cost & deal")]


def nav():
    # Shaily roles are locked to their own dashboard (no cross-view toggle).
    if ss.is_shaily:
        return
    # Pharma customer: request → options → cost (no access to internal BD dashboards).
    labels = [lbl for _, lbl in PHARMA_STEPS]
    cur = next((lbl for key, lbl in PHARMA_STEPS if key == ss.screen), labels[0])
    pick = st.segmented_control("nav", labels, default=cur, label_visibility="collapsed")
    for key, lbl in PHARMA_STEPS:
        if pick == lbl and ss.screen != key:
            ss.screen = key; st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Request form
# ────────────────────────────────────────────────────────────────────────────
def screen_form():
    st.markdown('<div class="eyebrow">Step 01 · Customer request form</div>', unsafe_allow_html=True)
    st.markdown("## Tell us about the product")
    ref = D.REFERENCE_PRODUCTS.get(ss.brand)

    with st.container(border=True):
        section("Reference product")
        c1, c2 = st.columns(2)
        ss.brand = c1.selectbox("Reference product brand name", list(D.REFERENCE_PRODUCTS.keys()),
                                index=list(D.REFERENCE_PRODUCTS.keys()).index(ss.brand))
        ref = D.REFERENCE_PRODUCTS.get(ss.brand)
        ss.market = c2.selectbox("Target market", D.MARKETS, index=D.MARKETS.index(ss.market))
        if ref:
            st.caption(f"✓ Recognised — **{ref['molecule']}** · device auto-set to **{ref['device']}**.")
        opts = ref["strengths"] if ref else []
        chosen = st.multiselect("Strength(s) / SKUs — dose strength as published", options=opts,
                                default=[s for s in (ss.strengths or opts) if s in opts]) if opts else \
            [s.strip() for s in st.text_input("Strengths (comma separated)", ", ".join(ss.strengths)).split(",") if s.strip()]
        ss.strengths = chosen

    with st.container(border=True):
        section("Product viscosity")
        c1, c2 = st.columns([2, 1])
        with c1:
            ss.visc_val = st.number_input("Viscosity (cP) — leave blank if unknown", min_value=0.0, step=0.5,
                                          value=float(ss.visc_val) if ss.visc_val else 0.0,
                                          help="+ / − adjusts the value.")
        with c2:
            st.write("")
            st.write("")
            if st.button("＋ Need assistance", use_container_width=True):
                if ref:
                    ss.visc_val = ref["visc_val"]
                    ss.visc_ref = ref["visc_ref"]
                    st.rerun()
        if ss.visc_ref:
            st.caption(f"📄 Literature reference: {ss.visc_ref}")

    with st.container(border=True):
        section("Device type & differentiated route")
        c1, c2 = st.columns([1, 1.4])
        ss.differentiated = c1.toggle("Differentiated formulation", value=ss.differentiated)
        auto_dev = ref["device"] if ref else "Pen Injector"
        if ss.differentiated:
            ss.device = c2.segmented_control("Device type", ["Pen Injector", "Auto-Injector", "On-Body"],
                                             default=ss.device or auto_dev)
        else:
            ss.device = auto_dev
            c2.markdown(f'<div style="margin-top:26px" class="pill">Device: {auto_dev} · auto from RLD</div>', unsafe_allow_html=True)

    with st.container(border=True):
        section("Cartridge & fill — one row per SKU (editable)")
        if ss.strengths:
            default_cart = ref["cartridge"] if ref else "3 mL"
            existing = {r["Strength"]: r for r in (ss.sku_rows or [])}
            rows = [existing.get(s, dict(Strength=s, Cartridge=default_cart, **{"Fill (mL)": 1.5})) for s in ss.strengths]
            df = pd.DataFrame(rows)
            edited = st.data_editor(
                df, use_container_width=True, hide_index=True, num_rows="fixed",
                column_config={
                    "Strength": st.column_config.TextColumn(disabled=True),
                    "Cartridge": st.column_config.SelectboxColumn(options=D.CART_SIZES, required=True),
                    "Fill (mL)": st.column_config.NumberColumn(min_value=0.0, step=0.1, format="%.2f mL"),
                }, key="sku_editor")
            ss.sku_rows = edited.to_dict("records")
        else:
            st.info("Select at least one strength above to configure cartridge & fill per SKU.")

    ready = bool(ss.strengths and ss.sku_rows)
    if st.button("Find platform options →", type="primary", disabled=not ready):
        ss.screen = "options"; st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Platform options — SKU → Option 1 / 2 / 3 tables (no rank order)
# ────────────────────────────────────────────────────────────────────────────
def _option_tables():
    """Return {option_index: DataFrame} mapping each SKU to its k-th compatible platform."""
    skus = active_skus()
    per_sku = {}
    for r in skus:
        comp = D.platforms_for_cartridge(r["Cartridge"])
        if ss.device and ss.device != "On-Body":
            want = "Autoinjector" if ss.device == "Auto-Injector" else ss.device
            comp = sorted(comp, key=lambda p: 0 if p["cls"] == want else 1)
        per_sku[r["Strength"]] = comp
    tables = {}
    for opt in range(3):
        rows = []
        for r in skus:
            comp = per_sku[r["Strength"]]
            p = comp[opt] if opt < len(comp) else None
            rows.append({
                "SKU": r["Strength"], "Cartridge": r["Cartridge"],
                "Platform": p["variant"] if p else "—",
                "Type": (f'{p["cls"]}' + (f' · {p["sub"]}' if p and p["sub"] else "")) if p else "—",
                "Resolution": p["resolution"] if p else "—",
                "Last-dose lockout": p["lockout"] if p else "—",
                "Mechanism": p["mech"] if p else "—",
            })
        tables[opt + 1] = pd.DataFrame(rows)
    return tables


def screen_options():
    if not active_skus():
        st.warning("Complete the request form first."); return
    st.markdown('<div class="eyebrow">Step 02 · Platform options</div>', unsafe_allow_html=True)
    st.markdown("## Mapped Shaily platforms for your SKUs")
    st.caption("Each SKU is matched to compatible Shaily platforms by cartridge size and device type. "
               "Three option sets are proposed — pick the one to take forward.")
    tables = _option_tables()
    for opt, cls in [(1, "o1"), (2, "o2"), (3, "o3")]:
        selected = ss.chosen_option == opt
        badge = f'<span class="opttag {cls}">Option {opt}</span>'
        if selected:
            badge += ' <span class="pill" style="color:var(--forest)">✓ selected</span>'
        st.markdown(badge, unsafe_allow_html=True)
        st.dataframe(tables[opt], use_container_width=True, hide_index=True)
        b = st.columns([1, 3])
        if b[0].button(f"Select Option {opt} →", key=f"select_opt_{opt}",
                       type="primary" if selected else "secondary", use_container_width=True):
            ss.chosen_option = opt
            ss.screen = "cost"
            st.rerun()
        st.write("")


# ────────────────────────────────────────────────────────────────────────────
# Cost & deal — per-SKU service selection
# ────────────────────────────────────────────────────────────────────────────
def screen_cost():
    skus = active_skus()
    if not skus:
        st.warning("Complete the request form first."); return
    tables = _option_tables()
    chosen = tables[ss.chosen_option]
    # severity: moderate if any chosen platform is a "moderate change" variant, else minor
    moderate = any(v.get("moderate") for v in D.PLATFORM_SHEET
                   if v["variant"] in set(chosen["Platform"]))
    sev = "moderate" if moderate else "minor"

    st.markdown('<div class="eyebrow">Step 03 · Tentative cost & deal</div>', unsafe_allow_html=True)
    st.markdown(f"## Costed DV package — Option {ss.chosen_option}")
    ss.access_role = st.segmented_control("Access mode", ["Customer", "BD (edit all costs)"],
                                          default=ss.access_role)
    is_bd = ss.access_role.startswith("BD")

    section("Service selection — per SKU")
    st.caption("Tick the services required against each SKU. Standard DV covers the platform design verification.")
    base = [{"SKU": r["Strength"], "Platform": chosen.loc[i, "Platform"], "Standard DV": True,
             "Threshold": False, "IFU": False, "Human Factor": False}
            for i, r in enumerate(skus)]
    svc = st.data_editor(pd.DataFrame(base), use_container_width=True, hide_index=True, num_rows="fixed",
                         column_config={
                             "SKU": st.column_config.TextColumn(disabled=True),
                             "Platform": st.column_config.TextColumn(disabled=True),
                             "Standard DV": st.column_config.CheckboxColumn(),
                             "Threshold": st.column_config.CheckboxColumn(help=f"${D.SERVICES['threshold']:,}/variant"),
                             "IFU": st.column_config.CheckboxColumn(help=f"${D.SERVICES['ifu']:,}/variant"),
                             "Human Factor": st.column_config.CheckboxColumn(help=f"${D.SERVICES['human_factor']:,}/variant"),
                         }, key="svc_editor")

    n_dv = int(svc["Standard DV"].sum())
    lead = D.PKG[sev]
    if is_bd:
        lead = st.number_input("Governing DV package (K USD)", min_value=0, value=int(lead), step=10)
    dv_usd = (lead + D.ADD_DV * max(0, n_dv - 1)) * 1000 if n_dv else 0
    thr = int(svc["Threshold"].sum()) * D.SERVICES["threshold"]
    ifu = int(svc["IFU"].sum()) * D.SERVICES["ifu"]
    hf = int(svc["Human Factor"].sum()) * D.SERVICES["human_factor"]
    total = dv_usd + thr + ifu + hf

    c1, c2 = st.columns([1.3, 1])
    with c1:
        with st.container(border=True):
            section("Standard-condition testing (ISO 11608)")
            st.write(" · ".join(D.STD_CONDITION_TESTS))
            section("Timeline")
            st.markdown(f'<div class="{"hl" if sev=="moderate" else "card"}">Governing change: '
                        f'<b>{D.SEV_LABEL[sev]}</b> — {D.SEV_LOGIC[sev]}. Standard timeline '
                        f'<b>{D.TIMELINE[sev]} months</b>.</div>', unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            section("Total package")
            def line(a, b):
                st.markdown(f'<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--line);font-size:13.5px">'
                            f'<span>{a}</span><span class="mono">{b}</span></div>', unsafe_allow_html=True)
            line(f"DV package ({n_dv} SKU)", f"${dv_usd:,.0f}")
            line(f"Threshold × {int(svc['Threshold'].sum())}", f"${thr:,.0f}")
            line(f"IFU × {int(svc['IFU'].sum())}", f"${ifu:,.0f}")
            line(f"Human factor × {int(svc['Human Factor'].sum())}", f"${hf:,.0f}")
            st.markdown(f'<div style="margin-top:12px;padding-top:12px;border-top:2px solid var(--ink);display:flex;'
                        f'justify-content:space-between;align-items:baseline"><b>Tentative package</b>'
                        f'<span class="mono" style="font-size:25px;color:var(--blue-dk)">${total:,.0f}</span></div>',
                        unsafe_allow_html=True)

    with st.container(border=True):
        section("Negotiate / discuss")
        st.text_area("Comment for the Shaily BD desk", key="neg_comment", placeholder="e.g. Bracket SKU 2–3 into one DV.")
        urg = st.segmented_control("Urgency", ["Level 1 · call back today", "Level 2 · call back this week"],
                                   default="Level 1 · call back today")
        if st.button("Send to Shaily BD", type="primary"):
            st.success(f"Sent · {urg}. A BD manager will follow up accordingly.")


# ────────────────────────────────────────────────────────────────────────────
# BD dashboards
# ────────────────────────────────────────────────────────────────────────────
def _heatmap(matrix_dict, rows, cols, title, colorscale):
    z = [[matrix_dict.get(r, {}).get(c, 0) for c in cols] for r in rows]
    fig = go.Figure(go.Heatmap(z=z, x=cols, y=rows, colorscale=colorscale, showscale=False,
                               text=[[v or "" for v in row] for row in z], texttemplate="%{text}",
                               textfont=dict(size=12), xgap=3, ygap=3))
    fig.update_xaxes(side="top", tickfont=dict(size=11))
    return brand_fig(fig, 240)


def screen_dash():
    # Role-locked: BD Manager sees the command centre; Workforce sees only their own view.
    if ss.user and "Workforce" in ss.user["role"]:
        dash_workforce()
    else:
        dash_manager()


def dash_manager():
    st.markdown('<div class="eyebrow">BD Manager · Command centre</div>', unsafe_allow_html=True)
    st.markdown("## Business against target, by quarter")
    annual_target = sum(D.QUARTER_TARGET.values())
    annual_expected = sum(sum(q.values()) for q in D.REP_QUARTERLY.values())
    new_cust = sum(D.NEW_CUSTOMERS_QTR.values())
    k = st.columns(4)
    kpi(k[0], f"${annual_target}M", "Annual target", "#3D7CA6")
    kpi(k[1], f"${annual_expected}M", "Expected pipeline", "#7DB343")
    kpi(k[2], f"{annual_expected/annual_target*100:.0f}%", "Target coverage", "#E5883B")
    kpi(k[3], new_cust, "New customers (FY)", "#2E7D46")

    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            section("Business vs target — by quarter")
            qs = D.QUARTERS
            expected = [sum(D.REP_QUARTERLY[r][q] for r in D.REPS) for q in qs]
            fig = go.Figure()
            fig.add_bar(x=qs, y=[D.QUARTER_TARGET[q] for q in qs], name="Target", marker_color="#C7D6D6")
            fig.add_bar(x=qs, y=expected, name="Expected", marker_color="#2F6E97",
                        text=[f"${v}M" for v in expected], textposition="outside")
            fig.update_layout(barmode="group")
            st.plotly_chart(brand_fig(fig, 260, legend=True), use_container_width=True)
    with c2:
        with st.container(border=True):
            section("New customers added — by quarter")
            fig = go.Figure(go.Bar(x=D.QUARTERS, y=[D.NEW_CUSTOMERS_QTR[q] for q in D.QUARTERS],
                                   marker_color="#7DB343", text=[D.NEW_CUSTOMERS_QTR[q] for q in D.QUARTERS],
                                   textposition="outside"))
            st.plotly_chart(brand_fig(fig, 260), use_container_width=True)

    with st.container(border=True):
        section("Expected production output per Shaily variant (million units)")
        items = sorted(D.PRODUCTION.items(), key=lambda kv: kv[1], reverse=True)
        fig = go.Figure(go.Bar(x=[k for k, _ in items], y=[v for _, v in items],
                               marker_color="#3D7CA6", text=[f"{v}M" for _, v in items], textposition="outside"))
        st.plotly_chart(brand_fig(fig, 280), use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        with st.container(border=True):
            section("BD representative × platform ($M)")
            st.plotly_chart(_heatmap(D.REP_PLATFORM, D.REPS, D.PLATFORM_COLS, "", "Blues"), use_container_width=True)
    with c4:
        with st.container(border=True):
            section("BD representative × business partner ($M)")
            st.plotly_chart(_heatmap(D.REP_CUSTOMER, D.REPS, D.CUSTOMERS, "", "Greens"), use_container_width=True)

    with st.container(border=True):
        section("Per-representative business — quarter-wise & annual ($M)")
        rows = []
        for r in D.REPS:
            q = D.REP_QUARTERLY[r]
            rows.append({"Representative": r, "Region": D.REP_REGION[r], **q, "Annual": sum(q.values())})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        fig = go.Figure()
        for q in D.QUARTERS:
            fig.add_bar(x=D.REPS, y=[D.REP_QUARTERLY[r][q] for r in D.REPS], name=q)
        fig.update_layout(barmode="stack", colorway=["#3D7CA6", "#7DB343", "#E5883B", "#2E7D46"])
        st.plotly_chart(brand_fig(fig, 260, legend=True), use_container_width=True)


def dash_workforce():
    st.markdown('<div class="eyebrow">Workforce · Individual performance</div>', unsafe_allow_html=True)
    st.markdown("## My engagements & customer relationships")
    names = {w["id"]: f'{w["name"]} — {w["region"]}' for w in D.WORKFORCE}
    ss.wf_id = st.selectbox("Signed-in representative", list(names.keys()),
                            format_func=lambda x: names[x], index=list(names.keys()).index(ss.wf_id))
    w = next(x for x in D.WORKFORCE if x["id"] == ss.wf_id)
    extra = ss.get("wf_calls_extra", {}).get(w["id"], [])
    calls = extra + w["calls"]
    rel = D.relationship_score(dict(w, calls=calls))
    k = st.columns(4)
    kpi(k[0], len(calls), "Calls logged", "#3D7CA6")
    kpi(k[1], f'${sum(D.REP_CUSTOMER.get(w["name"], {}).values())}M', "Opportunity created", "#7DB343")
    kpi(k[2], f'{w["promptness"]}%', "Promptness (Teams)", "#E5883B")
    kpi(k[3], rel, "Relationship score", "#2E7D46")

    st.write("")
    with st.container(border=True):
        section("Log a customer call")
        c1, c2 = st.columns(2)
        cust = c1.text_input("Customer", key="call_cust", placeholder="e.g. Auro")
        ctx = c2.text_input("Context (one line)", key="call_ctx", placeholder="e.g. Neo sampling for 4 SKUs")
        if st.button("Log call & update score", type="primary"):
            if ctx.strip():
                ss.setdefault("wf_calls_extra", {}).setdefault(w["id"], []).insert(
                    0, (_dt.date.today().isoformat(), (f"{cust} — " if cust.strip() else "") + ctx.strip()))
                st.rerun()
            else:
                st.warning("Add a one-line context to log the call.")
        st.caption("📎 Meetings auto-sync from Microsoft Teams in the production build.")

    with st.container(border=True):
        section("Call log")
        st.dataframe(pd.DataFrame([{"Date": d, "Context": c} for d, c in calls]),
                     use_container_width=True, hide_index=True)


# ────────────────────────────────────────────────────────────────────────────
# Router
# ────────────────────────────────────────────────────────────────────────────
watermark()
header()
if ss.screen == "gate":
    screen_gate()
else:
    nav()
    st.write("")
    if ss.is_shaily:
        screen_dash()
    else:
        {"form": screen_form, "options": screen_options, "cost": screen_cost,
         "dash": screen_dash}.get(ss.screen, screen_form)()

st.markdown('<div style="text-align:center;color:var(--muted);font-family:IBM Plex Mono,monospace;font-size:11px;'
            'margin-top:34px;letter-spacing:.05em">SHAILY ENGINEERING PLASTICS · MEDICAL DEVICE UNIT · DDCP CONSOLE · '
            'PHASE I · CONFIDENTIAL</div>', unsafe_allow_html=True)
