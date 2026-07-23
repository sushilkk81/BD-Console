"""Standalone checks for the curated device-mechanism engine (no Streamlit)."""
import data as D

# --- Task 1: profiles + signatures ---
neo3 = next(p for p in D.PLATFORM_SHEET if p["variant"] == "Neo (3 mL)")
sig = D.platform_signature(neo3)
assert sig["archetype"] == "peninjector", sig
assert sig["drive"] == D.DRIVE_TORSION, sig
assert sig["dose"] == "fixed", sig

prot = next(p for p in D.PLATFORM_SHEET if p["variant"] == "Protean P3")
assert D.platform_signature(prot)["drive"] == D.DRIVE_MANUAL

toby = next(p for p in D.PLATFORM_SHEET if p["variant"] == "Toby")
tsig = D.platform_signature(toby)
assert tsig["archetype"] == "autoinjector" and tsig["drive"] == D.DRIVE_SPRING_AI
assert tsig["dose"] == "na"

for brand in ["Ozempic", "Saxenda", "Toujeo", "Humira", "Trulicity"]:
    r = D.REFERENCE_PRODUCTS[brand]
    assert r["mech_drive"] and r["mech_dose"] in ("fixed", "variable")
    assert r["mech_label"] and r["ob_ref"] and r["ob_claims"]

oz = D.REFERENCE_PRODUCTS["Ozempic"]
assert oz["mech_drive"] == D.DRIVE_TORSION and oz["mech_dose"] == "variable"
sax = D.REFERENCE_PRODUCTS["Saxenda"]
assert sax["mech_drive"] == D.DRIVE_TORSION
touj = D.REFERENCE_PRODUCTS["Toujeo"]
assert touj["mech_drive"] == D.DRIVE_MANUAL

print("task1 signatures + profiles: OK")

# --- Task 2: similarity scoring ---
def _score(brand, variant):
    p = next(pp for pp in D.PLATFORM_SHEET if pp["variant"] == variant)
    return D.mechanism_similarity(D.REFERENCE_PRODUCTS[brand], p)

s_neo, b_neo, _ = _score("Ozempic", "Neo (3 mL)")      # torsion vs torsion, dose differs
assert abs(s_neo - 0.80) < 1e-9 and b_neo == "Close", (s_neo, b_neo)

s_p3, b_p3, _ = _score("Ozempic", "Protean P3")        # torsion vs manual(0.2), dose match
assert abs(s_p3 - 0.76) < 1e-9 and b_p3 == "Similar", (s_p3, b_p3)
assert s_neo > s_p3

s_h2, b_h2, _ = _score("Toujeo", "Harmony H2")         # manual vs manual, variable vs variable
assert abs(s_h2 - 1.0) < 1e-9 and b_h2 == "Close", (s_h2, b_h2)

s_sl, b_sl, _ = _score("Humira", "Safe LAN")           # spring_ai_hv match, dose fixed vs na(0.5)
assert abs(s_sl - 0.90) < 1e-9 and b_sl == "Close", (s_sl, b_sl)

s_mira, b_mira, _ = _score("Humira", "Mira")           # AI vs On-Body → divergent
assert b_mira == "Divergent", (s_mira, b_mira)

print("task2 similarity: OK")

# --- Task 3: ranking (hard filter + fallback) ---
# Ozempic (torsion, 3 mL): Neo ranks above geared Protean; Neo is Close
r = D.rank_platforms_for_sku("3 mL", D.REFERENCE_PRODUCTS["Ozempic"])
names = [x["platform"]["variant"] for x in r]
assert names.index("Neo (3 mL)") < names.index("Protean P3"), names
assert r[0]["band"] == "Close" and r[0]["pct"] == 80

# Toujeo (manual, 1.5 mL): manual/geared pens Close, above torsion Neo(1.5 mL)
r2 = {x["platform"]["variant"]: x for x in D.rank_platforms_for_sku("1.5 mL", D.REFERENCE_PRODUCTS["Toujeo"])}
assert r2["Axiom Max"]["band"] == "Close"
assert r2["Neo (1.5 mL)"]["score"] < r2["Axiom Max"]["score"]

# Humira high-visc bespoke: Safe LAN Close & first; Mira divergent fallback
r3 = D.rank_platforms_for_sku("1 mL Bespoke", D.REFERENCE_PRODUCTS["Humira"])
assert r3[0]["platform"]["variant"] == "Safe LAN" and r3[0]["band"] == "Close"
mira = next(x for x in r3 if x["platform"]["variant"] == "Mira")
assert mira["fallback"] is True and mira["band"] == "Divergent"

# Unknown RLD → cartridge-only, band n/a
r4 = D.rank_platforms_for_sku("3 mL", None)
assert r4 and all(x["band"] == "n/a" and x["pct"] is None for x in r4)

print("task3 ranking: OK")

# --- Task 4: per-SKU presentation (cartridge x fill) from labels ---
assert D.presentation_for("Ozempic", "0.25 mg")[:2] == ("1.5 mL", 1.5)
assert D.presentation_for("Ozempic", "0.5 mg")[:2] == ("1.5 mL", 1.5)
assert D.presentation_for("Ozempic", "1 mg")[:2] == ("3 mL", 3.0)      # the reported bug
assert D.presentation_for("Ozempic", "2 mg")[:2] == ("3 mL", 3.0)      # the reported bug
assert D.presentation_for("Wegovy", "1 mg")[1] == 0.5
assert D.presentation_for("Wegovy", "2.4 mg")[1] == 0.75
assert D.presentation_for("Humira", "40 mg")[1] == 0.4                  # citrate-free
assert D.presentation_for("Humira", "80 mg")[1] == 0.8
assert D.presentation_for("Enbrel", "25 mg")[1] == 0.5
assert D.presentation_for("Dupixent", "300 mg")[1] == 2.0
# unknown → safe fallback
assert D.presentation_for("Nonesuch", "9 mg")[:2] == ("3 mL", 1.5)

# every RLD strength has a curated presentation with a valid cartridge + citation
for brand, r in D.REFERENCE_PRODUCTS.items():
    p = D.PRESENTATIONS.get(brand, {})
    assert p.get("_ref"), brand
    for s in r["strengths"]:
        assert s in p, (brand, s)
        cart, fill = p[s]
        assert cart in D.CART_SIZES and fill > 0, (brand, s, cart, fill)

print("task4 presentations: OK")

# --- Task 5: market-aware variants (US / EU / Canada) ---
assert D.MARKETS == ["US", "EU", "Canada"], D.MARKETS

# Wegovy: US single-dose AI vs EU/Canada FlexTouch torsion pen
wus = D.variants_for("Wegovy", "US")
assert wus["device"] == "Auto-Injector" and wus["mech_drive"] == D.DRIVE_SPRING_ONE
assert wus["market_note"] == ""
for mkt in ("EU", "Canada"):
    w = D.variants_for("Wegovy", mkt)
    assert w["device"] == "Pen Injector" and w["mech_drive"] == D.DRIVE_TORSION, (mkt, w["mech_drive"])
    assert w["market_note"]

# Mounjaro: US single-dose AI vs EU/Canada KwikPen manual pen
mus = D.variants_for("Mounjaro", "US")
assert mus["device"] == "Auto-Injector" and mus["mech_drive"] == D.DRIVE_SPRING_AI
for mkt in ("EU", "Canada"):
    m = D.variants_for("Mounjaro", mkt)
    assert m["device"] == "Pen Injector" and m["mech_drive"] == D.DRIVE_MANUAL and m["mech_dose"] == "fixed"

# Non-divergent product identical across markets
assert D.variants_for("Ozempic", "EU")["device"] == D.variants_for("Ozempic", "US")["device"]
assert D.variants_for("Ozempic", "Canada")["market_note"] == ""

# Market-aware presentations
assert D.presentation_for("Wegovy", "0.25 mg", "US")[:2] == ("1 mL PFS", 0.5)
assert D.presentation_for("Wegovy", "0.25 mg", "EU")[:2] == ("1.5 mL", 1.5)
assert D.presentation_for("Wegovy", "2.4 mg", "Canada")[:2] == ("1.5 mL", 1.5)
assert D.presentation_for("Mounjaro", "5 mg", "US")[:2] == ("1 mL PFS", 0.5)
assert D.presentation_for("Mounjaro", "5 mg", "EU")[:2] == ("3 mL", 2.4)

# Market flips the mechanism mapping: EU Wegovy (torsion pen, 1.5 mL) → Neo torsion is Close & top
eu_rank = D.rank_platforms_for_sku("1.5 mL", D.variants_for("Wegovy", "EU"))
assert eu_rank[0]["platform"]["variant"] == "Neo (1.5 mL)" and eu_rank[0]["band"] == "Close", eu_rank[0]
# US Wegovy (single-dose AI, 1 mL PFS) maps to auto-injectors instead
us_rank = D.rank_platforms_for_sku("1 mL PFS", D.variants_for("Wegovy", "US"))
assert us_rank[0]["platform"]["cls"] == "Autoinjector", us_rank[0]["platform"]["variant"]

print("task5 market variants: OK")
