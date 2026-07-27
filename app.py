"""Shaily DDCP Partnership Console — Streamlit build.  Run: streamlit run app.py"""
# Requires data.py mechanism engine (rank_platforms_for_sku, mech_* profiles) — keep in sync.
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
    kam_id="mah", mgr_view="Command centre",
    kam_extra={}, kam_deleted=[], region_map=None, org_map=None,
    assignments={}, audit=[], schedule={},
)
for k, v in _defaults.items():
    ss.setdefault(k, v)
# mutable maps default to copies of the seed data (editable in-session)
if ss.region_map is None:
    ss.region_map = dict(D.REGION_KAM)
if ss.org_map is None:
    ss.org_map = dict(D.ORG_KAM)


@st.cache_resource
def shared_store():
    """Cross-session store shared by all users of this app instance — survives
    logout so a request submitted by a customer is visible to the BD Manager and
    KAM who log in separately. Resets on app reboot/redeploy. Phase-2 replaces
    this with the Supabase backend (durable + per-user auth)."""
    return {"requests": {}, "audit": []}


def audit_log(actor, action, detail):
    shared_store()["audit"].insert(0, dict(Date=_dt.date.today().isoformat(),
                                            Actor=actor, Action=action, Detail=detail))


def submit_request(user, budget):
    """Customer submits their request + preliminary budget into the shared store."""
    reqs = shared_store()["requests"]
    rid = (user.get("org") or user.get("email") or "req").strip().lower() or "req"
    reqs[rid] = dict(id=rid, customer=user.get("name", "—"), org=user.get("org") or "—",
                     region=user.get("region") or "—", market=ss.market, brand=ss.brand,
                     device=ss.device, sub=f"{ss.sub_fy} {ss.sub_q}",
                     sku_rows=[dict(r) for r in active_skus()], budget=budget,
                     status="Awaiting assignment", kam=None, date=_dt.date.today().isoformat())
    return rid


def all_kams():
    """Live KAM roster = seed KAMs minus deleted plus in-session added."""
    out = {k: v for k, v in D.KAMS.items() if k not in ss.kam_deleted}
    out.update(ss.kam_extra)
    return out


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
            '<div><div style="font-size:24px;color:#fff">9</div><div style="font-size:10px;color:#7FA6A3">PLATFORM FAMILIES</div></div>'
            '<div><div style="font-size:24px;color:#fff">&lt;3mo</div><div style="font-size:10px;color:#7FA6A3">FASTEST DV</div></div>'
            '<div><div style="font-size:24px;color:#fff">48h</div><div style="font-size:10px;color:#7FA6A3">COMPARATIVE PACK</div></div>'
            '</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="eyebrow">Access the console</div>', unsafe_allow_html=True)
        st.markdown("### Identify yourself to begin")
        name = st.text_input("Name", placeholder="e.g. Dr. Anaya Mehta")
        # Email drives role: a Shaily-domain sign-in is an internal user; anything
        # else is a customer. Org / region are no longer collected here — the BD
        # Manager tags routing inside the portal.
        email = st.text_input("Organization email", key="gate_email", placeholder="name@company.com")
        is_shaily = "@shaily." in email.lower()

        if is_shaily:
            role_options = ["Select your function…", "Key Account Manager", "BD Manager"]
            role_label = "Designation / Role · Shaily domain recognised"
        else:
            role_options = ["Select your function…", "R&D Packaging", "Supply Chain",
                            "Business Development", "Others — Specify"]
            role_label = "Designation / Role"
        role = st.selectbox(role_label, role_options)

        other = ""
        if role == "Others — Specify":
            other = st.text_input("Please specify your function", placeholder="e.g. Regulatory Affairs")

        phone = st.text_input("Contact number", placeholder="+91 / +1 …")
        agreed = st.checkbox("I accept the mutual Terms & Conditions and NDA.")
        with st.expander("Read the mutual NDA / Terms & Conditions"):
            st.markdown("**Mutual, two-way NDA** between Shaily Engineering Plastics Ltd. and the accessing "
                        "organisation. All exchanged information is confidential, used solely to progress the "
                        "programme, disclosed to no third party, and restricted to named users. No screenshots. "
                        "Indicative pricing is non-binding at R&D stage. Confidentiality survives five (5) years.")
        role_ok = role != "Select your function…" and (role != "Others — Specify" or len(other.strip()) > 1)
        ok = len(name) > 1 and role_ok and "@" in email and len(phone) > 5 and agreed
        if st.button("Agree & enter →", type="primary", use_container_width=True, disabled=not ok):
            final_role = other.strip() if role == "Others — Specify" else role
            ss.user = dict(name=name, role=final_role, email=email, phone=phone, org="", region="")
            ss.is_shaily = is_shaily
            if is_shaily and role == "BD Manager":
                ss.screen, ss.dash_tab = "dash", "BD Manager"
            elif is_shaily and role == "Key Account Manager":
                ss.screen, ss.dash_tab = "dash", "KAM"
            else:
                ss.screen = "form"
            st.rerun()
        st.caption("🔒 Session bound to your email · Watermarked · Mutual NDA · Shaily-domain sign-ins open the internal dashboard")


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
def _reset_for_rld():
    """Cascade fresh defaults for every RLD-dependent field when brand or market changes."""
    ref = D.variants_for(ss.brand, ss.market)
    ss.strengths = list(ref["strengths"]) if ref else []
    ss.sku_rows = None
    ss.device = ref["device"] if ref else None
    ss.differentiated = False
    ss.visc_val = None
    ss.visc_ref = ""
    ss.chosen_option = 1
    ss._form_ver = ss.get("_form_ver", 0) + 1   # bump → keyed widgets re-initialise


def screen_form():
    st.markdown('<div class="eyebrow">Step 01 · Customer request form</div>', unsafe_allow_html=True)
    st.markdown("## Tell us about the product")
    keys = list(D.REFERENCE_PRODUCTS.keys())
    ver = ss.get("_form_ver", 0)

    with st.container(border=True):
        section("Reference product")
        c1, c2 = st.columns(2)
        new_brand = c1.selectbox("Reference product brand name", keys, index=keys.index(ss.brand))
        mkt_idx = D.MARKETS.index(ss.market) if ss.market in D.MARKETS else 0
        new_market = c2.selectbox("Target market", D.MARKETS, index=mkt_idx)
        if new_brand != ss.brand or new_market != ss.market:   # brand/market changed → cascade fresh defaults
            ss.brand, ss.market = new_brand, new_market
            _reset_for_rld()
            st.rerun()
        ss.brand, ss.market = new_brand, new_market
        ref = D.variants_for(ss.brand, ss.market)
        if ref:
            st.caption(f"✓ Recognised — **{ref['molecule']}** · device auto-set to **{ref['device']}** for {ss.market}.")
            if ref.get("market_note"):
                st.caption(f"🌍 {ss.market}: {ref['market_note']}")
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
            rows = []
            for s in ss.strengths:
                if s in existing:
                    rows.append(existing[s])
                else:
                    cart, fill, _ = D.presentation_for(ss.brand, s, ss.market, default_cart)
                    rows.append(dict(Strength=s, Cartridge=cart, **{"Fill (mL)": fill}))
            df = pd.DataFrame(rows)
            edited = st.data_editor(
                df, use_container_width=True, hide_index=True, num_rows="fixed",
                column_config={
                    "Strength": st.column_config.TextColumn(disabled=True),
                    "Cartridge": st.column_config.SelectboxColumn(options=D.CART_SIZES, required=True),
                    "Fill (mL)": st.column_config.NumberColumn(min_value=0.0, step=0.1, format="%.2f mL"),
                }, key=f"sku_{ver}")
            ss.sku_rows = edited.to_dict("records")
            _, _, pref = D.presentation_for(ss.brand, ss.strengths[0], ss.market, default_cart)
            if pref:
                st.caption(f"📄 Presentation source: {pref} · label data verified as of {D.DATA_AS_OF}")
        else:
            st.info("Select at least one strength above to configure cartridge & fill per SKU.")

    ready = bool(ss.strengths and ss.sku_rows)
    if st.button("Find platform options →", type="primary", disabled=not ready):
        ss.screen = "options"; st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Platform options — SKU → Option 1 / 2 / 3 tables (no rank order)
# ────────────────────────────────────────────────────────────────────────────
def _scoring_rld():
    """Market-effective RLD profile for mechanism scoring, honouring a differentiated-device override."""
    rld = D.variants_for(ss.brand, ss.market)
    if rld is None:
        return None
    if ss.differentiated and ss.device:
        rld = dict(rld)
        rld["device"] = ss.device
    return rld


def _option_tables():
    """Return {option_index: DataFrame} mapping each SKU to its k-th mechanism-ranked platform."""
    skus = active_skus()
    rld = _scoring_rld()
    per_sku = {r["Strength"]: D.rank_platforms_for_sku(r["Cartridge"], rld) for r in skus}
    tables = {}
    for opt in range(3):
        rows = []
        for r in skus:
            ranked = per_sku[r["Strength"]]
            item = ranked[opt] if opt < len(ranked) else None
            p = item["platform"] if item else None
            if item and item["band"] != "n/a":
                match = f'{item["band"]} · {item["pct"]}%'
                if item["fallback"]:
                    match += " ⚠ fallback"
                if item.get("visc_limited"):
                    match += " · visc-limited"
            else:
                match = "—"
            rows.append({
                "SKU": r["Strength"], "Cartridge": r["Cartridge"],
                "Platform": p["variant"] if p else "—",
                "Type": (f'{p["cls"]}' + (f' · {p["sub"]}' if p and p["sub"] else "")) if p else "—",
                "Resolution": p["resolution"] if p else "—",
                "Last-dose lockout": p["lockout"] if p else "—",
                "Mechanism": p["mech"] if p else "—",
                "Mechanism match": match,
            })
        tables[opt + 1] = pd.DataFrame(rows)
    return tables


def screen_options():
    if not active_skus():
        st.warning("Complete the request form first."); return
    st.markdown('<div class="eyebrow">Step 02 · Platform options</div>', unsafe_allow_html=True)
    st.markdown("## Mapped Shaily platforms for your SKUs")
    st.caption("Each SKU is matched to cartridge-compatible Shaily platforms and ranked by device-mechanism "
               "closeness to the reference product. Three option sets are proposed — pick the one to take forward.")

    rld = _scoring_rld()
    if rld and rld.get("mech_label"):
        st.markdown(
            f'<div class="pill">Reference device mechanism: '
            f'<b>{rld["mech_label"]}</b> · {rld.get("mech_dose", "")} dose</div>',
            unsafe_allow_html=True)
        st.caption(f'Basis: {rld.get("ob_ref", "—")}')
        with st.expander("Orange Book device patents — mechanism basis"):
            st.write(f'**Reference:** {rld.get("ob_ref", "—")}')
            st.write("**Mechanism claims used to classify drive:**")
            for c in rld.get("ob_claims", []):
                st.write(f"- {c}")
        st.caption("Options are ranked by mechanism closeness to the reference device. "
                   "Rows flagged ⚠ fallback are cartridge-compatible but mechanistically divergent — "
                   "expect added device DV / human-factors burden.")
    else:
        st.info("No curated mechanism profile for this product — mapping falls back to cartridge-only ranking.")

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
    # severity: escalate to moderate for a "moderate change" platform OR a divergent (fallback) pick
    has_fallback = any("fallback" in str(m) for m in chosen["Mechanism match"])
    moderate = has_fallback or any(v.get("moderate") for v in D.PLATFORM_SHEET
                                   if v["variant"] in set(chosen["Platform"]))
    sev = "moderate" if moderate else "minor"

    st.markdown('<div class="eyebrow">Step 03 · Tentative cost & deal</div>', unsafe_allow_html=True)
    st.markdown(f"## Costed DV package — Option {ss.chosen_option}")
    st.caption("Select the services you need per SKU below. Cost editing and negotiation are handled by your assigned Shaily KAM.")
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
    dv_usd = (lead + D.ADD_DV * max(0, n_dv - 1)) * 1000 if n_dv else 0
    thr = int(svc["Threshold"].sum()) * D.SERVICES["threshold"]
    ifu = int(svc["IFU"].sum()) * D.SERVICES["ifu"]
    hf = int(svc["Human Factor"].sum()) * D.SERVICES["human_factor"]
    total = dv_usd + thr + ifu + hf
    # Share the customer's preliminary budget & selection with the assigned KAM.
    ss.customer_budget = dict(
        brand=ss.brand, market=ss.market, option=ss.chosen_option, access=ss.access_role,
        severity=sev, timeline=D.TIMELINE[sev], rows=svc.to_dict("records"),
        dv_usd=dv_usd, thr=thr, ifu=ifu, hf=hf, total=total, n_dv=n_dv,
        comment=ss.get("neg_comment", ""))

    c1, c2 = st.columns([1.3, 1])
    with c1:
        with st.container(border=True):
            section("Standard-condition testing (ISO 11608)")
            st.write(" · ".join(D.STD_CONDITION_TESTS))
            section("Timeline")
            st.markdown(f'<div class="{"hl" if sev=="moderate" else "card"}">Governing change: '
                        f'<b>{D.SEV_LABEL[sev]}</b> — {D.SEV_LOGIC[sev]}. Standard timeline '
                        f'<b>{D.TIMELINE[sev]} months</b>.</div>', unsafe_allow_html=True)
            if has_fallback:
                st.caption("⚠ Severity raised to moderate: this option includes a mechanistically divergent "
                           "(fallback) platform — added device design verification / human-factors expected.")
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
        section("Submit this request to the Shaily BD desk")
        st.text_area("Comment for the Shaily BD desk", key="neg_comment", placeholder="e.g. Bracket SKU 2–3 into one DV.")
        urg = st.segmented_control("Urgency", ["Level 1 · call back today", "Level 2 · call back this week"],
                                   default="Level 1 · call back today")
        org = (ss.user or {}).get("org") or ""
        if not org:
            st.caption("The Shaily BD Manager tags your organization and routes this request to the right KAM after submission.")
        if st.button("Submit request to Shaily BD", type="primary"):
            ss.customer_budget["comment"] = ss.get("neg_comment", "")
            rid = submit_request(ss.user or {}, ss.customer_budget)
            audit_log((ss.user or {}).get("name", "Customer"), "Request submitted",
                      f"{org or 'Customer'} · {ss.brand} · {n_dv} SKU · ${total:,.0f} · {urg}")
            st.success(f"Submitted to the Shaily BD desk ({urg}). The BD Manager will assign a Key Account Manager. "
                       f"Reference: {rid}")


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
    # Role-locked: KAM sees only their own workspace; BD Manager sees the command centre + KAM admin.
    role = ss.user["role"] if ss.user else ""
    if "Key Account Manager" in role or "KAM" in role:
        kam_workspace()
    else:
        manager_home()


def manager_home():
    ss.mgr_view = st.segmented_control("mgr", ["Command centre", "KAM & assignments"],
                                       default=ss.mgr_view, label_visibility="collapsed")
    if ss.mgr_view == "KAM & assignments":
        manager_kam_admin()
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


def manager_kam_admin():
    kams = all_kams()
    st.markdown('<div class="eyebrow">BD Manager · KAM &amp; assignments</div>', unsafe_allow_html=True)
    st.markdown("## Key Account Managers & query routing")

    with st.container(border=True):
        section("KAM roster")
        rows = []
        for kid, k in kams.items():
            regs = [r for r, kk in ss.region_map.items() if kk == kid]
            orgs = [o for o, kk in ss.org_map.items() if kk == kid]
            rows.append({"KAM": k["name"], "Login": k.get("login", ""),
                         "Regions": ", ".join(regs) or "—", "Organizations": ", ".join(orgs) or "—"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        a, b = st.columns(2)
        with a:
            st.markdown("**Add a KAM**")
            nn = st.text_input("Name", key="add_kam_name", placeholder="e.g. Ms. ROY")
            nl = st.text_input("Login email", key="add_kam_login", placeholder="roy@shaily.com")
            if st.button("＋ Add KAM", key="add_kam_btn") and nn.strip():
                kid = (nn.strip().lower().replace(" ", "").replace(".", "") or "kam")[:8]
                ss.kam_extra[kid] = dict(id=kid, name=nn.strip(), login=nl.strip())
                audit_log(ss.user["name"], "KAM added", nn.strip()); st.rerun()
        with b:
            st.markdown("**Remove a KAM**")
            pick = st.selectbox("KAM", list(kams.keys()), format_func=lambda k: kams[k]["name"], key="del_kam_pick")
            if st.button("🗑 Delete KAM", key="del_kam_btn"):
                if pick in ss.kam_extra: del ss.kam_extra[pick]
                else: ss.kam_deleted.append(pick)
                audit_log(ss.user["name"], "KAM removed", kams[pick]["name"]); st.rerun()

    with st.container(border=True):
        section("Link KAM to region / organization")
        ko = list(kams.keys())
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Region → KAM**")
            for reg in D.KAM_REGIONS:
                cur = ss.region_map.get(reg)
                ss.region_map[reg] = st.selectbox(reg, ko, index=ko.index(cur) if cur in ko else 0,
                                                   format_func=lambda k: kams[k]["name"], key=f"reg_{reg}")
        with c2:
            st.markdown("**Organization → KAM (override)**")
            for org in list(ss.org_map.keys()):
                cur = ss.org_map.get(org)
                ss.org_map[org] = st.selectbox(org, ko, index=ko.index(cur) if cur in ko else 0,
                                               format_func=lambda k: kams[k]["name"], key=f"org_{org}")
            no = st.text_input("Add organization", key="add_org_name", placeholder="e.g. Cipla")
            nk = st.selectbox("Assign to", ko, format_func=lambda k: kams[k]["name"], key="add_org_kam")
            if st.button("＋ Add organization link", key="add_org_btn") and no.strip():
                ss.org_map[no.strip()] = nk
                audit_log(ss.user["name"], "Org linked", f"{no.strip()} → {kams[nk]['name']}"); st.rerun()

    with st.container(border=True):
        section("Incoming customer requests — assign a KAM")
        reqs = shared_store()["requests"]
        if not reqs:
            st.caption("No customer requests submitted yet. A customer submits theirs from the Cost & deal step — it "
                       "appears here and survives their logout (shared across all sessions of this app).")
        ko = list(kams.keys())
        for rid, r in list(reqs.items()):
            kid, basis = D.resolve_kam(r["org"], r["region"], ss.region_map, ss.org_map)
            b = r.get("budget") or {}
            cols = st.columns([3, 2, 2, 3])
            cols[0].markdown(f"**{r['org']}** · {r['region']}<br><span style='color:#6B7C86;font-size:12px'>{r['date']} · {r['customer']} · {r['brand']}</span>", unsafe_allow_html=True)
            cols[1].caption(f"{len(r.get('sku_rows', []))} SKU · ${b.get('total', 0):,.0f}")
            cols[2].markdown(f"Suggested<br>**{kams.get(kid, {}).get('name', '—')}**<br><span style='font-size:11px;color:#6B7C86'>by {basis or '—'}</span>", unsafe_allow_html=True)
            with cols[3]:
                if r.get("kam"):
                    st.success(f"Assigned → {kams.get(r['kam'], {}).get('name', '?')}")
                else:
                    di = ko.index(kid) if kid in ko else 0
                    ac = st.selectbox("Assign to", ko, index=di, format_func=lambda k: kams[k]["name"], key=f"asg_{rid}")
                    if st.button("Assign KAM", key=f"assign_{rid}"):
                        r["kam"] = ac
                        r["status"] = f"Assigned to {kams.get(ac, {}).get('name', '?')}"
                        audit_log(ss.user["name"], "KAM assigned", f"{kams.get(ac, {}).get('name', '?')} → {r['org']} ({r['brand']})")
                        st.rerun()

    with st.container(border=True):
        section("Audit trail")
        audit = shared_store()["audit"]
        if audit:
            st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)
        else:
            st.caption("No activity yet — submit a request or assign a KAM to populate the trail.")


def kam_workspace():
    kams = all_kams()
    if ss.kam_id not in kams:
        ss.kam_id = list(kams)[0]
    st.markdown('<div class="eyebrow">Key Account Manager · Workspace</div>', unsafe_allow_html=True)
    ss.kam_id = st.selectbox("Signed-in KAM (simulated individual login)", list(kams.keys()),
                             format_func=lambda k: f"{kams[k]['name']} · {kams[k].get('login', '')}",
                             index=list(kams.keys()).index(ss.kam_id))
    me = ss.kam_id
    st.markdown(f"## Welcome, {kams[me]['name']}")
    st.caption("You see only the organizations and responses routed to you.")

    reqs = shared_store()["requests"]
    mine = [r for r in reqs.values() if r.get("kam") == me]
    regs = [r for r, kk in ss.region_map.items() if kk == me]
    orgs = [o for o, kk in ss.org_map.items() if kk == me]
    k = st.columns(3)
    kpi(k[0], len(mine), "Assigned requests", "#3D7CA6")
    kpi(k[1], len(regs), "Regions covered", "#7DB343")
    kpi(k[2], len(orgs), "Named organizations", "#E5883B")

    st.write("")
    with st.container(border=True):
        section("My assigned customer requests")
        if mine:
            st.dataframe(pd.DataFrame([{"Organization": r["org"], "Region": r["region"], "Date": r["date"],
                                        "Reference": r["brand"], "SKUs": len(r.get("sku_rows", [])),
                                        "Budget": f"${(r.get('budget') or {}).get('total', 0):,.0f}",
                                        "Status": r["status"]} for r in mine]),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("No customer requests assigned to you yet — the BD Manager assigns them from the inbox. "
                       "(Demo path: submit a request as a customer, then assign it as the BD Manager.)")

    if not mine:
        return

    labels = {r["id"]: f"{r['org']} · {r['brand']}" for r in mine}
    active_id = st.selectbox("Working on request", list(labels.keys()),
                             format_func=lambda x: labels[x], key="kam_active_req")
    req = next(r for r in mine if r["id"] == active_id)

    with st.container(border=True):
        section("Customer request form (read-only)")
        rows = req.get("sku_rows", [])
        if rows:
            st.dataframe(pd.DataFrame([{"SKU": r.get("Strength"), "Cartridge": r.get("Cartridge"),
                                        "Fill (mL)": r.get("Fill (mL)")} for r in rows]),
                         use_container_width=True, hide_index=True)
        st.caption(f"Reference: {req['brand']} · market {req.get('market', '—')} · "
                   f"device {req.get('device') or '—'} · submission {req.get('sub', '—')}")

    with st.container(border=True):
        section("Customer's preliminary budget & selected services")
        cb = req.get("budget") or {}
        if cb:
            kk = st.columns(4)
            kpi(kk[0], f"${cb['total']:,.0f}", "Preliminary budget", "#2F6E97")
            kpi(kk[1], f"{cb['n_dv']} SKU", f"DV · {D.SEV_LABEL[cb['severity']]}", "#7DB343")
            kpi(kk[2], f"{cb['timeline']} mo", "Standard timeline", "#E5883B")
            kpi(kk[3], f"Option {cb['option']}", "customer selection", "#2E7D46")
            st.markdown("**Per-SKU service selection (as chosen by the customer)**")
            st.dataframe(pd.DataFrame(cb["rows"]), use_container_width=True, hide_index=True)
            st.caption(f"DV package ${cb['dv_usd']:,.0f}  ·  Threshold ${cb['thr']:,.0f}  ·  "
                       f"IFU ${cb['ifu']:,.0f}  ·  Human factor ${cb['hf']:,.0f}")
            if cb.get("comment"):
                st.info(f"💬 Customer note: {cb['comment']}")

            st.markdown("**Cost adjustment for negotiation (KAM / BD Manager only)**")
            n = cb["n_dv"]
            cur_lead = int(cb["dv_usd"] / 1000 - D.ADD_DV * max(0, n - 1)) if n else D.PKG[cb["severity"]]
            ac1, ac2 = st.columns([1, 2])
            kam_lead = ac1.number_input("Revised governing DV (K USD)", min_value=0, value=cur_lead, step=10, key="kam_lead")
            rev_dv = (kam_lead + D.ADD_DV * max(0, n - 1)) * 1000 if n else 0
            rev_total = rev_dv + cb["thr"] + cb["ifu"] + cb["hf"]
            ac2.markdown(f"<div style='margin-top:26px'>Revised total <b style='color:#234F70;font-size:17px'>"
                         f"${rev_total:,.0f}</b> &nbsp;<span style='color:#6B7C86'>(customer saw ${cb['total']:,.0f})</span></div>",
                         unsafe_allow_html=True)

            st.markdown("**Your recommendation to the BD Manager for final costing**")
            rc1, rc2 = st.columns([3, 1])
            rec = rc1.text_input("Recommendation", key="kam_rec", label_visibility="collapsed",
                                 placeholder="e.g. Recommend 5% concession on DV for the 4-SKU bracket")
            if rc2.button("Push to BD Manager", key="kam_push") and rec.strip():
                req["recommendation"] = rec.strip(); req["rev_total"] = rev_total
                req["status"] = "Recommendation with BD Manager"
                audit_log(kams[me]["name"], "Recommendation pushed",
                          f"{req['org']}: {rec.strip()} (revised ${rev_total:,.0f})")
                st.success("Sent to BD Manager for approval.")
        else:
            st.caption("This request has no budget attached.")

    with st.container(border=True):
        section("Deliverable & pre-requisite schedule")
        st.caption("Set the FY quarter and confirm responsibility. KAM items carry an upload; component drawings expand "
                   "to the three components with revision tracking and change control.")
        for i, d in enumerate(D.DELIVERABLES):
            with st.container(border=True):
                top = st.columns([4, 2, 2])
                top[0].markdown(f"**{d['item']}**")
                key = f"dl_{i}"
                top[1].selectbox("FY quarter", ["— select —"] + D.FY_QUARTERS, key=f"{key}_fq", label_visibility="collapsed")
                rc = "#2F6E97" if d["resp"] == "KAM" else "#2E7D46"
                top[2].markdown(f"<div style='margin-top:5px'><span class='pill' style='color:{rc}'>Responsibility · {d['resp']}</span></div>", unsafe_allow_html=True)
                if d.get("query"):
                    st.text_input("Issue faced", key=f"{key}_issue", placeholder="Describe the functionality failure")
                    st.caption("Query date auto-stamped · Responsibility: Customer")
                elif d.get("components"):
                    for c in d["components"]:
                        cc = st.columns([3, 1, 2])
                        cc[0].markdown(f"• {c}")
                        cc[1].text_input("Rev", key=f"{key}_{c}_rev", placeholder="Rev 00", label_visibility="collapsed")
                        cc[2].file_uploader("＋ drawing", key=f"{key}_{c}_file", label_visibility="collapsed")
                    st.text_input("Change-control reference", key=f"{key}_cc", placeholder="Change control ref (if any)")
                    if st.button("Post drawings & notify customer", key=f"{key}_notify"):
                        audit_log(kams[me]["name"], "Drawings posted", f"{d['item']} — customer notified")
                        st.success("Posted. Customer receives a notification with revisions & change-control.")
                elif d.get("upload"):
                    u = st.columns([3, 1])
                    u[0].file_uploader("＋ upload package", key=f"{key}_file", label_visibility="collapsed")
                    if u[1].button("Notify", key=f"{key}_notify"):
                        audit_log(kams[me]["name"], "Deliverable posted", d["item"])
                        st.success("Uploaded & customer notified.")
        if st.button("Push final cost & schedule to customer", type="primary", key="push_schedule"):
            audit_log(kams[me]["name"], "Schedule pushed", "Final cost & deliverable schedule sent to customer")
            st.success("Final cost structure and deliverable schedule pushed to the customer.")


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
