# External reference-data lookup agents — design

## Context

The customer request wizard's reference-data engine (`backend/app/services/reference_data.py`)
is 100% static: `reference_products` and `reference_product_markets` are seeded once via
literal Python dicts in Alembic migration `0003_core_customer_flow.py`, with no runtime way to
add or edit rows. Several seeded citation fields are explicitly marked "to confirm." The
original docx change-request (see `Revision 1/New Changes.docx`) asked for three related but
distinct pieces of automation:

1. **Strength auto-population** — when a brand/market combination has no local data, search
   FDA.gov for the label and populate available strengths.
2. **Viscosity assistance** — replace the current "+ Need assistance" button's static copy
   (`currentRef.visc_val`, itself just the seeded value) with a real literature search
   producing a range and citations.
3. **Cartridge & fill volume matching** — ensure cartridge size and fill volume are correct
   per market, sourced from the same label data as (1), falling back to the brand's own
   manufacturer website when FDA has nothing for that market.

Per the user's guidance: FDA.gov is a free, always-available source and should be the primary
source for (1) and (3); viscosity genuinely needs a broader literature search since it's not
FDA-label data. This spec covers the backend subsystem that makes all three real.

## Confirmed facts (verified live)

- `https://api.fda.gov/drug/label.json?search=openfda.brand_name:"{brand}"+AND+openfda.route:"SUBCUTANEOUS"&limit=1`
  is free, requires no API key for this app's volume (240 req/min / 1,000 req/day anonymous;
  120,000/day with a free key), and returns structured SPL sections including
  `dosage_forms_and_strengths` — free text that contains strength + cartridge + fill volume
  together (e.g. "2 mg / 3 mL" pens, "0.5 mL" prefilled syringes).
- Viscosity is **not** present in FDA labels — confirmed absent from a real response. It
  genuinely needs a web/literature search, matching the user's own framing.
- `backend/app/config.py`'s `Settings` currently has no external-API fields, and the backend
  has no `httpx`/external-HTTP-call pattern anywhere. This is new infrastructure end to end.

## Decisions (confirmed with user)

- **Extraction/synthesis LLM:** Claude, via the Anthropic API (`claude-opus-5`).
- **Search provider** (viscosity literature search; brand-website fallback for cartridge/fill
  when FDA has nothing for a market): **Tavily** — single REST call, no SDK dependency needed.
- **Persistence:** a successful lookup is **upserted into the existing
  `reference_products` / `reference_product_markets` tables** — `variants_for` /
  `presentation_for` (the existing reference-data engine) are read unchanged; nothing about
  the core engine's contract changes.
- **Cache-first:** a lookup endpoint checks the DB for an existing row for that exact
  `(brand, market)` first and returns it immediately with **zero external calls** on a hit.
  Only a true first-time miss goes external.
- **Trigger:** on-demand button click (mirrors the existing "+ Need assistance" pattern), not
  automatic — external calls (FDA fetch + Claude, or Tavily + Claude) can take several
  seconds and cost money; automatic firing on every brand/market keystroke is not acceptable.
- **Graceful failure everywhere:** no API key configured, network failure, brand not found,
  or the LLM producing unusable output — all collapse to a normal `200 {found: false}`
  response, never a 4xx/5xx the frontend has to special-case. Internal errors are logged
  server-side only.
- **Viscosity `visc_val` must be a clean number to count as found** — if literature search
  can only produce a qualitative note (no defensible single figure), the endpoint reports
  `found: false` rather than a partial result. (This is the one place the user's answer
  diverged from my recommendation — chosen deliberately to keep the "found" contract simple:
  found means usable, not found means the customer types it in manually.)
- **New-brand base-row creation:** a strengths lookup for a never-seeded brand may create a
  full `ReferenceProduct` base row with placeholder values (`0`/`""`) for fields an FDA label
  can't supply (`visc_val`, `mech_drive`, `mech_dose`, `mech_label`, `ob_ref`, `ob_claims`) —
  those fill in later via a separate viscosity lookup or stay placeholder, same as any
  incomplete seeded row today.

## Architecture

### New module: `backend/app/services/external_lookup.py`

Owns every outbound call. `reference_data.py` and the request routers are untouched.

```python
def cartridge_for_fill(fill_ml: float) -> str:
    """Deterministic business rule, NOT delegated to the LLM: ≤1.5 mL → '1.5 mL' cartridge,
    else '3 mL'. The LLM only ever extracts raw fill_ml numbers + citation text."""

def fetch_fda_label(brand: str) -> dict | None:
    """Raw openFDA fetch. No API key. Never raises — returns None on any failure."""

def search_tavily(query: str) -> list[dict]:
    """Raw Tavily search via httpx. Returns [] on any failure or missing API key."""

class LookupService:
    """Thin seam so tests can substitute a fake via FastAPI dependency override,
    the same pattern this repo already uses for get_db/get_current_user."""

    def lookup_strengths(self, brand: str, market: str) -> StrengthLookupResult: ...
    def lookup_viscosity(self, brand: str, molecule: str | None) -> ViscosityLookupResult: ...

def get_lookup_service() -> LookupService:
    return LookupService(settings=get_settings())
```

- `lookup_strengths`: `fetch_fda_label` → if nothing found, `search_tavily` for the brand's
  manufacturer site as a fallback source → Claude extraction call (strict tool-forced JSON,
  not prose parsing) → `cartridge_for_fill` applied in Python to every extracted fill volume.
- `lookup_viscosity`: `search_tavily` for literature on the molecule/brand → Claude synthesis
  call → `found=True` only if a clean `visc_val` came back.
- Every public method wraps its body in `try/except Exception`, logs at `WARNING` with
  brand/market context, and returns a `found=False` result — nothing propagates as an
  unhandled exception into the router.
- All `httpx` calls get an explicit ~8–10s timeout — this runs in the request path.
- No key configured → short-circuit to `found=False` before any network call (fast, free).

### Settings (`backend/app/config.py`)

```python
anthropic_api_key: str = ""
tavily_api_key: str = ""
```

Both optional; an unset key degrades to `found: false`, not a 503 — matches the
graceful-everywhere contract above.

### Schemas (`backend/app/schemas.py`)

```python
class ReferenceStrengthLookupIn(BaseModel):
    brand: str
    market: str

class LookedUpStrength(BaseModel):
    strength: str
    cartridge: str
    fill_ml: float

class ReferenceStrengthLookupOut(BaseModel):
    found: bool
    brand: str
    molecule: Optional[str] = None
    device: Optional[str] = None
    strengths: list[LookedUpStrength] = []
    citation: Optional[str] = None

class ReferenceViscosityLookupIn(BaseModel):
    brand: str
    molecule: Optional[str] = None

class ReferenceViscosityLookupOut(BaseModel):
    found: bool
    brand: str
    visc_val: Optional[float] = None
    citation: Optional[str] = None
```

### Router: `backend/app/routers/reference_lookup.py`

- `POST /reference-lookup/strengths` — cache-first: `variants_for`/direct row lookup against
  `(brand, market)` first; on hit, return immediately (matches existing seeded-row shape). On
  miss, call `LookupService.lookup_strengths`; on `found=True`, upsert:
  - `ReferenceProduct` base row if `brand` doesn't exist yet (placeholders for
    viscosity/mechanism fields, per the decision above).
  - `ReferenceProductMarket(brand, market)` override row's `presentations`/`pres_ref` only —
    never overwrite an existing base row's fields from a single market's label fetch, since
    the base row is shared across all markets.
  - Upsert via `try: add/commit except IntegrityError: rollback, fetch existing, update` —
    portable across SQLite (tests) and Postgres (prod), matching this repo's plain-ORM style
    rather than dialect-specific `ON CONFLICT` syntax.
- `POST /reference-lookup/viscosity` — cache-first against `ReferenceProduct.visc_val`
  (nonzero → hit); on miss, call `LookupService.lookup_viscosity`; on `found=True`, upsert
  `ReferenceProduct.visc_val`/`visc_ref` (base row only — viscosity is a molecule property,
  not market-specific; `ReferenceProductMarket` has no `visc_val` column).
- **Auth:** plain `Depends(get_current_user)`, not the draft-ownership pattern
  `_owned_draft_or_404` — these endpoints are keyed only on `(brand, market)`, not on a
  specific `Request` row, matching the existing `GET /reference-products` endpoint's auth
  level. Any authenticated role can call them.
- Neither endpoint writes `SkuRow`s directly — the frontend, on `found: true`, refreshes its
  local reference-product list and the *existing* `create_request`/`update_request_step1`
  flow (unchanged) picks up the newly-upserted DB rows the next time it runs.

### Dependencies (`backend/requirements.txt`)

- `httpx` — already present, no change.
- `anthropic` — new.

## Frontend integration

- New `lib/api.ts` functions: `lookupStrengths(token, brand, market)`,
  `lookupViscosity(token, brand, molecule)`.
- Wizard step 1 (`app/requests/[id]/page.tsx`):
  - Reference-product brand field gains a "🔍 Look up live" trigger next to it (loading
    state, disabled while in flight) that calls `lookupStrengths` and merges a `found: true`
    result into the local `refProducts` list, so `currentRef` populates exactly as if the
    brand had been seeded — populates the strength chips and, transitively, the cartridge/fill
    table via the existing `presentation_for`-backed create/update flow.
  - The existing "+ Need assistance" viscosity button's `onClick` changes from copying
    `currentRef.visc_val` to calling `lookupViscosity`; on `found: true`, displays the value
    with its citation in italics with a leading asterisk (matching the docx's formatting
    ask) instead of silently filling the field — the customer still confirms/edits the number.
  - On `found: false` from either lookup, show a small inline "No data found — enter
    manually" message rather than an error banner (this is an expected, non-error outcome).
- No changes needed to `create_request`/`update_request_step1` call sites — they already read
  whatever's in the DB via the unchanged `reference_data.py` engine.

## Testing strategy

- `cartridge_for_fill` — pure function, direct unit tests (1.5 → "1.5 mL", 1.51 → "3 mL",
  boundary cases).
- Router tests use `app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService(...)`,
  exactly parallel to this repo's existing `get_db` override pattern — no real HTTP calls in
  CI, no `unittest.mock.patch` on `httpx`/`anthropic` internals.
- Cases to cover: cache-hit short-circuits before any lookup call; `found=True` upserts
  correct rows (new brand vs. existing brand + new market override); `found=False` (no
  key configured, and lookup-service miss) both return 200; concurrent-lookup upsert doesn't
  raise (IntegrityError path).

## Explicitly out of scope

- Market-agency integrations beyond the US (EMA, Health Canada, etc.) — FDA is used as the
  best-effort primary source for every market per the user's framing ("brand specific website
  if available" covers the rest); this is not a claim that FDA data is authoritative for
  non-US markets.
- Any UI for manually editing/curating reference-product data — out of scope for this slice,
  unchanged from today (Alembic migration is still the only manual-edit path).
