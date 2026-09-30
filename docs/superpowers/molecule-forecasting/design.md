# Molecule market intelligence & sales volume forecasting

Ten-year Base and Upside volume projections attached to a BD request: annual treated
patients, finished-product dosage units, packs, contained API mass, our obtainable
business volume, and optional revenue.

This is an evidence-backed forecasting tool. It does not reproduce IQVIA or Newport
coverage and does not claim to. Three kinds of number are kept apart everywhere:
**observed** source data, **user assumptions**, and **modelled** estimates derived from
the two.

## Decisions taken before implementation

The original request specified a few things that did not fit this repository. Each was
resolved with the requester before any code was written:

| Specified | Built | Why |
|---|---|---|
| `SQLModel MoleculeForecastParameter` | SQLAlchemy 2.0 Declarative on the existing `Base` | The repo has no SQLModel dependency. A second declarative base would mean two metadata objects for Alembic to reconcile. |
| `deal_id` foreign key | `request_id INTEGER → requests.id` | There is no `deals` table. `requests` is the pipeline entity, and its `id` is `sa.Integer` — matched exactly. `BIGINT` is used for population/count columns, where it belongs. |
| `APIRouter(prefix="/api/forecast")` | `APIRouter(prefix="/forecast")` | `frontend/app/api/[...path]/route.ts` strips a leading `/api` before proxying, so every backend router here is mounted without it. This yields the client URL `/api/forecast/...` exactly as specified; `/api/forecast` on the backend would have produced `/api/api/forecast/...`. |

## Stages

`source acquisition → identity/unit validation → assumption review → deterministic
calculation → persistence/display`, one module per stage. Ingestion never writes into a
reviewed parameter set: observations are stored beside the request, and adopting one is
a separate, explicit save by a person.

## Layout

```
backend/app/forecasting_engine/
  core/math_engine.py        pure NumPy/SciPy; no I/O, no clock, no randomness
  core/units.py              the unit/mode vocabulary that prevents incompatible aggregation
  models/db_models.py        three tables on the app's existing Base
  api/routes.py              APIRouter(prefix="/forecast")
  api/schemas.py             Pydantic v2, extra="forbid", finite-only
  services/forecast_service.py   authorize → load → calculate → persist
  services/source_cache.py       bounded per-process TTL cache for source searches
  services/sources/base.py       SourceAdapter protocol + Observation
  services/sources/cms_part_d.py CMS Medicare Part D: live API + official-download ingest
  services/sources/tabular_import.py  validated CSV/JSON import and manual entry
backend/alembic/versions/0008_molecule_forecasting.py
frontend/components/ForecastPanel.tsx   mounted on the request detail page, cost & deal step
```

## Mathematics

```
adoption(t)  = expit(ramp_speed * (t - inflection_year))      t = years since launch
epidemiology:  patients_s(t)       = N * peak_share_s * adoption(t)
observed:      market_units(t)     = reference_units * (1 + g) ** (calendar_year - reference_year)
               business_units_s(t) = market_units(t) * peak_capture_share_s * adoption(t)
```

`peak_share` is the **asymptote**, not a value attained by year 10: at
`t == inflection_year` adoption is exactly 0.5 and it approaches 1 only as t grows. This
is a plain logistic uptake curve, **not** Bass diffusion. Patient figures are **annual
treated patients**, never cumulative unique patients.

Calendar alignment: the response always carries exactly 10 values, covering
`forecast_start_year … +9`. For each calendar year, `t = year - launch_year + 1`; where
`t <= 0` the year precedes launch and every derived business volume is exactly `0`.
Forecasts are conditional on launch; any probability-of-success adjustment is returned as
a separate series and never folded into the base or upside arrays.

Conversions apply only when their inputs exist — otherwise the metric is `null`, never
`0`:

```
dosage_units = patients * units_per_patient_per_year
packs        = dosage_units / units_per_pack
api_kg       = dosage_units * active_ingredient_mg_per_unit / 1_000_000
```

`api_kg` is **contained active-ingredient demand**, not a manufacturing input
requirement: no yield, salt-factor or potency adjustment is applied. For an apparent
combination product, mass is either computed from an explicit per-ingredient
`active_ingredient_mg_per_unit` (and labelled as that single ingredient) or refused.

**Company capture is applied exactly once.** In epidemiology mode `peak_share` is the
modelled product's share *of patients* and `company_capture_share` is a separate factor
on the derived units; in observed-volume mode `peak_capture_share` already *is* the
company capture, so `company_capture_share` is rejected there by schema, service and
database check constraint alike. `addressable_*` (total demand) and `business_*` (our
obtainable volume) are separate response fields so the UI cannot present one as the other.

Money is `Decimal`/`NUMERIC` end to end. Revenue multiplies a business volume by a net
price **in the same unit**, and requires currency and basis together. Public gross
spending is never treated as manufacturer net revenue.

## Data model

`molecule_forecast_parameters` hangs off `requests` and inherits `requests.org_id` for
tenancy — no ownership column is duplicated, matching how `sku_rows` and
`request_messages` already work.

A request is forecast at **one granularity only**: either one request-level row
(`sku_row_id IS NULL`) or one row per SKU, never both, so the rows can be summed without
double-counting. `UNIQUE(request_id, sku_row_id)` does not constrain request-level rows
because NULLs compare distinct in both PostgreSQL and SQLite — a **partial unique index**
on `request_id WHERE sku_row_id IS NULL` does, and the service rejects mixing levels.

`molecule_source_observations` records source URL, identifier, geography, coverage
wording, period, metric, unit, retrieval timestamp and transformation for each datum. A
suppressed or unreported value stays `NULL`; it is never stored as `0`, because a
suppressed small cell and a true zero mean opposite things.
`molecule_forecast_audit` is append-only, one row per accepted revision.

Constraints live in the database as well as the schema, so a direct SQL write cannot
create an uncomputable row: share bounds, `base ≤ upside`, `ramp_speed > 0`,
`growth > -1`, positive conversion denominators, nonnegative populations, the
mode-specific required/forbidden field sets, and the complete price triplet.

## API

| Endpoint | Behaviour |
|---|---|
| `GET /forecast/{request_id}` | Loads persisted inputs and calculates. **Never** fetches upstream. |
| `POST /forecast/upsert` | Complete parameter set, atomic, revision-checked. |
| `GET /forecast/sources/search` | Read-only evidence search. Registered **before** the dynamic route. |
| `POST /forecast/sources/import` | Validated CSV/JSON import, bounded to 500 rows / 1 MB. |
| `POST /forecast/sources/cms-part-d/ingest` | Ingests an official CMS bulk CSV; columns resolved from its header; records retrieval provenance. |
| `GET /forecast/sources/cms-part-d/status` | File verification, publication freshness and API connectivity, reported independently. |

Release management — the validation workflow, the monthly metadata check and how freshness
degrades — is documented in [`release-management.md`](release-management.md).

Every endpoint reuses `get_current_user` and `_visible_or_404` from
`app/routers/requests.py` — imported rather than reimplemented, so forecast visibility
can never drift from request visibility. Searches authorize **before** consulting the
cache.

Concurrency is optimistic: the client sends the revision it loaded (`0` to create), and a
mismatch is rejected with **409** rather than silently overwriting. `ON CONFLICT` is
deliberately avoided because the test suite runs on SQLite; the write is a
`SELECT … FOR UPDATE` (a no-op on SQLite) inside one transaction.

**No forecast cache.** Two scenarios are twenty `expit` evaluations; adding shared
infrastructure to memoize that would cost more than it saves. Only source searches are
cached, in a bounded per-process TTL cache — which is *not* shared across workers, and is
cleared on upsert.

## The CMS Part D source

**Dataset identity, verified against official publications** (not guessed, not toggled):

| Fact | Value | Verified from |
|---|---|---|
| Dataset | Medicare Part D Spending by Drug | datahub.hhs.gov record `xzs3-ddeh` (attribution `data.cms.gov`) |
| API dataset UUID | `7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b` | HHS archive log `healthdata.gov/resource/hc4a-gw37.json`, `additionalAccessPoints` |
| Bulk CSV | `DSD_PTD_RY26_P04_V10_DY24_BGM.csv` | same access-point record; independently confirmed by the Internet Archive's capture index for the identical CMS URL |
| Data years in file | 2020–2024 (latest 2024) | the file's own header row |
| Update frequency | annual (`R/P1Y`) | HHS `Common Core` metadata |
| Spending basis | gross drug cost; excludes manufacturer rebates | CMS dataset description |

Column names are **resolved from the data in front of the parser**, not hardcoded:
`resolve_columns` confirms `Brnd_Name`/`Gnrc_Name` are present and expands
`Tot_Dsg_Unts_{year}`, `Tot_Clms_{year}`, `Tot_Benes_{year}`, `Tot_Spndng_{year}` against
the actual header. A CMS rename therefore produces a loud `configuration_incomplete`
rather than silently wrong numbers.

**Double counting, found in the real data:** CMS emits each brand twice — once under
`Mftr_Name = "Overall"` and once per manufacturer, with identical totals. Only the
roll-up row is emitted as an observation; the per-manufacturer rows are counted and
reported in a warning. A generic-name query matching several brands (semaglutide →
Ozempic, Rybelsus, Wegovy) flags every row `ambiguous_match` rather than summing them.

### Access: the API is blocked, the download is the supported route

`data.cms.gov/data-api/*` and `data.cms.gov/sites/default/files/*` return **HTTP 403 at
the Akamai edge**, including from the **deployment image built from `backend/Dockerfile`,
run locally in Docker**. It has *not* been probed from a deployed host — this app is not
deployed anywhere yet — and the report states that distinction explicitly. The same address reaches `data.cms.gov/provider-data/*` and
`www.cms.gov` with 200, so it is a path-scoped control, not an IP ban. CMS publishes no
API key for this dataset, so it is not an authentication failure. Full evidence,
endpoints, UTC timestamps and Akamai reference numbers are in
[`cms-access-report.md`](cms-access-report.md), ready to send to CMS support. No attempt
was made to imitate a browser fingerprint.

So there are two ingest routes sharing one parser:

- `CmsPartDAdapter.search()` — the live JSON API, for when CMS is reachable. On failure it
  reports `api_unavailable` **and names the bulk CSV as the alternative**.
- `CmsPartDFileIngestor.ingest()` — an official CMS file, via
  `POST /forecast/sources/cms-part-d/ingest` and a file picker in the panel. Gzip is
  handled; the file need not come from this machine.

**A browser extension is not a dependency.** Nothing in the running application uses one.
The file route is the supported path, and the API route resumes automatically if CMS
access is restored.

### Provenance: publication and retrieval are recorded separately

`source_url` always stays the publisher's canonical CMS URL. How the bytes actually
arrived is recorded beside it, so an archived copy is never presented as live CMS access:

| Field | Meaning |
|---|---|
| `provenance_class` | `live_cms_api`, `archived_cms_publication`, `user_supplied_file` or `manual_entry` |
| `source_url` | the CMS publication URL |
| `retrieval_url` | the URL actually fetched, when it differs (e.g. a web-archive capture) |
| `archive_capture_date` | when the archive captured the publisher's file |
| `retrieved_at` | when this application read it |
| `content_sha256` | computed here from the ingested bytes, never taken on trust |

Supplying a `retrieval_url` labels the ingest an **archived CMS publication**, and the
panel says so in words. The verified reference file is recorded with two digests: the
text digest the ingestor compares against, and the raw-bytes digest a person gets from
`shasum` on the download (CMS serves it gzip-encoded).

### Three states, never conflated

`SourceStatus` describes one search result: `api_unavailable`,
`configuration_incomplete`, or `no_matching_records`. Only the last says anything about
the molecule.

### Three source-health facts, reported independently

`GET /forecast/sources/cms-part-d/status` reports these separately, because they fail
independently and are fixed differently — a deployment can hold a verified file of the
current reporting year and still have no API connectivity:

1. **File verification** — does the ingested file match the copy whose contents were read
   by hand? An unrecognised digest is reported, not treated as an error; columns are
   resolved from the file's own header either way.
2. **Publication freshness** — is the reporting year the newest CMS is known to publish?
3. **API connectivity** — probed **on demand only** (`check_api=true`), never on a
   forecast read. A 403 is reported as `blocked` with its Akamai reference extracted from
   the HTML-escaped edge page, plus a paste-ready support summary.

The panel renders these as three separate tiles and always shows the **reporting year**
and the **last successful refresh**.

openFDA remains regulatory/product context only. No LLM call and no paid search touches
the forecasting path.

## Verification

- `backend`: 288 tests pass (133 pre-existing + 155 new) on Python 3.11.
- Migrations `0008`, `0009` and `0010` apply and downgrade cleanly on **PostgreSQL 16**; five invalid
  writes were rejected by the database itself, and `BIGINT` held 9,000,000,000.
- `frontend`: `npm run build` compiles successfully (there is no frontend test framework
  here by design — see CLAUDE.md).
- **Live data**, separate from the mocked tests: the genuine CMS file
  (`DSD_PTD_RY26_P04_V10_DY24_BGM.csv`, 14,536 drug rows) was ingested end to end through
  the real endpoints. Ozempic, data year 2024, as published by CMS: 42,324,232.836 dosage
  units, 10,417,182 claims, 1,952,637 beneficiaries, $12,970,296,347 gross spending. Those
  dosage units became the observed-volume baseline, giving an addressable 47,555,507 units
  in 2026 at 6%/yr growth (= 42,324,232 x 1.06^2), with the forecast citing the CMS URL.

### Non-finite request values

A bare `NaN`/`Infinity` JSON literal used to return 500: FastAPI echoes the offending
input into its 422 body and Starlette serialises with `allow_nan=False`, so the error
response itself failed to encode. `app/main.py` now handles `RequestValidationError` and
renders non-finite floats as strings. The body shape is unchanged — a `detail` list of
items with `loc` and `msg` — so `frontend/lib/api.ts`'s `parseError` contract and every
existing router behave exactly as before. Regression tests cover the 422 status, the
preserved contract, and an ordinary validation error.

Both the repo's `.venv` and `frontend/node_modules` are built for the devcontainer and do
not run on this macOS host, so backend tests and the frontend build were run in
`python:3.11-slim` and `node:20-slim` containers — the same bases as the project's own
Dockerfiles.
