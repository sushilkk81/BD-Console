# CMS Part D API access — report for CMS support

Prepared 2026-09-29.

**Where these probes ran — stated precisely.** Everything below was captured from the
**deployment _image_ built from `backend/Dockerfile`** (`python:3.11-slim`, the same image
`docker-compose` and the Render blueprint build), running **locally in Docker on a macOS
developer machine**. That is the deployment *artifact*, not the deployed *host*.

**No probe has been run from the actual deployed environment.** The Render blueprint in
this repository has never been applied — there is no running Render service, and
`infra/terraform/` has never been applied either. So the result below establishes that the
block is not specific to a developer's shell or Python install; it does **not** establish
what a Render egress address would see. Those are different questions and are reported
separately:

| Environment | Probed? | Result |
|---|---|---|
| macOS host shell (curl) | yes | 403 |
| Deployment image, locally in Docker | yes | 403 |
| A second, unrelated network | yes | 403 |
| Actual deployed host (Render) | **no — not deployed** | unknown |

The first action after a deployment exists is to run the probe there (see *How to
reproduce*), because a hosting provider's address range may be treated differently.

The application does not depend on this being resolved: it runs on ingested CMS files
today. This report exists so the access question can be raised with CMS.

## Summary

Requests to the Medicare Part D Spending by Drug **data API** and to the **bulk CSV path**
are denied at the Akamai edge with HTTP 403 before reaching the dataset. CMS publishes no
API key for this dataset, so this is not an authentication failure. Requests from the same
address to `data.cms.gov/provider-data/*` and `www.cms.gov` succeed with HTTP 200, so the
address is not blocked wholesale — the denial is scoped to these paths.

## Affected endpoints

| Path | Result |
|---|---|
| `https://data.cms.gov/data-api/v1/dataset/7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b/data` | **403** |
| `https://data.cms.gov/data-api/v1/dataset/7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b/dictionary` | **403** |
| `https://data.cms.gov/sites/default/files/2026-06/98218f98-166c-4723-8438-c344a4ef96a6/DSD_PTD_RY26_P04_V10_DY24_BGM.csv` | **403** |
| `https://data.cms.gov/data.json` | **403** |
| `https://data.cms.gov/resources/medicare-part-d-spending-by-drug-data-dictionary` | **403** |
| `https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items` | 200 |
| `https://www.cms.gov/` | 200 |

## Probes from the deployment image (local Docker)

| UTC timestamp | Endpoint | HTTP | Akamai reference |
|---|---|---|---|
| 2026-09-29T09:10:07.531777+00:00 | `/data-api/v1/dataset/7e0b4365-…/data` | 403 | `18.550ed217.1790673007.46c51118` |
| 2026-09-29T09:10:08.239535+00:00 | `/data-api/v1/dataset/7e0b4365-…/data` | 403 | `18.6e0ed217.1790673008.28ad6303` |
| 2026-09-29T09:09:23.480207+00:00 | `/data-api/v1/dataset/7e0b4365-…/data` | 403 | `18.6e0ed217.1790672963.28accd56` |

A fresh reference number is issued per request; any one of them identifies the denial in
Akamai's logs.

## What was ruled out

- **Not authentication.** No API key is published for this dataset, and no credential was
  sent or is expected.
- **Not the client address.** `provider-data` and `www.cms.gov` answer 200 from the same
  address in the same container, seconds apart.
- **Not content negotiation.** Identical 403 with and without `Accept: application/json`,
  with `Referer: https://data.cms.gov/`, and forced to HTTP/1.1.
- **Not rate limiting.** The first request of a cold container is already denied, and the
  response is a 403 access-denied page rather than a 429.
- **Not one network.** Reproduced from this machine, from the deployment image in local
  Docker, and from a second unrelated network. Not yet tested from a deployed host, as
  noted above.

No attempt was made to imitate a browser fingerprint or otherwise work around the control.

## Question for CMS

Is programmatic access to `data-api/v1` and the `sites/default/files` bulk downloads
expected to be available to server-side clients, and if so, is there an allow-list,
registration, or documented user-agent convention this deployment should follow?

## How to reproduce

```bash
docker build -t bdconsole-backend backend/
docker run --rm -e PYTHONPATH=/app bdconsole-backend python -c \
  "from app.forecasting_engine.services.sources.cms_part_d import probe_api; \
   print(probe_api().support_summary())"
```

The same probe is available to signed-in users at
`GET /api/forecast/sources/cms-part-d/status?request_id=<id>&check_api=true`, which
returns the endpoint, UTC timestamp, HTTP status and Akamai reference, and renders a
paste-ready summary in the forecast panel.
