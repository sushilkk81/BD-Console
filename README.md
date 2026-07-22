# Shaily DDCP Console — Streamlit

The DDCP Partnership Console (Phase 1) built in **Streamlit + Plotly**, themed to the
Shaily identity. Runs locally and deploys free to Streamlit Community Cloud.

## Run locally

```bash
cd shaily-streamlit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py            # opens http://localhost:8501
```

(Already verified here on Python 3.9 with Streamlit 1.50 — all screens run exception-free.)

## Deploy to Streamlit Community Cloud (free, ~2 min)

1. Push this **`shaily-streamlit/`** folder to a GitHub repo (its contents at the repo root,
   or keep the folder and point the app path at `shaily-streamlit/app.py`).
2. Go to **https://share.streamlit.io** → sign in with GitHub → **New app**.
3. Pick the repo/branch, set **Main file path** to `app.py`, and **Deploy**.
   Streamlit installs `requirements.txt` automatically and applies `.streamlit/config.toml`.
4. You get a `https://<app>.streamlit.app` URL. Under **Settings → Sharing**, restrict to
   invited emails for a confidential demo.

## What's in it

- **Access gate** — name/role/email/phone + mutual-NDA acceptance, watermarked session.
- **Request form** — reference-product select, market, SKU strengths (real published values),
  viscosity + container with **auto-populate showing the source document**, device type
  (auto from RLD, or differentiated override), submission FY/quarter + dossier FY.
- **Platform match** — the 7 real Shaily platforms, ranked with fit scores.
- **Mapping & timeline** — per-SKU container/fill/stopper table, change severity, 3/6/9-month
  timelines, **moderate-change highlighted distinctly**, SKU elimination.
- **Cost & service selection** — **BD (edit all) vs Customer (select services)** access,
  Standard DV, **matrix bracketing** (auto low+high variants, excluded list, ISO test set),
  Threshold ($2,110/var), IFU ($1,110/var), Human Factor ($0.4M/var), live total, negotiation
  with urgency levels.
- **BD dashboards** — Manager (KPIs, region/stage charts, engagement table with
  **commercial FY = submission + 2.5 yrs**, Orange Book IP panel, events, workforce roster)
  and Workforce (individual login, Teams-linked promptness, relationship score, **working call log**).

## Files

```
shaily-streamlit/
├── app.py                 # all screens + theme injection
├── data.py                # platforms, reference products, pricing, engines, demo data
├── requirements.txt
├── .streamlit/config.toml # brand theme
└── _verify.py             # headless AppTest check (dev only)
```

## Design note
Streamlit's default chrome (menu, footer, generic font) is suppressed via injected CSS and a
custom Shaily header, so it reads as a bespoke console rather than a data-science app. Some
prototype flourishes (animated hero, floating bubble selectors, pixel-exact watermark) are
approximated — that's the trade for Streamlit's fast build and one-click deploy.
