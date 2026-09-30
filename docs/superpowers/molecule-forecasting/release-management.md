# CMS release management

How a CMS Part D file becomes the one this application forecasts from, and how that stays
honest over time.

## The distinction this design rests on

> **A checksum identifies a file. It does not verify the source.**

Matching a recorded digest means only "these are the same bytes someone already examined".
It says nothing about whether the file is genuine, well-formed, or safe to forecast from.
Source verification is a separate, documented set of checks that a new legitimate CMS
release passes **on its own merits** — so a new release never requires an unexplained
hardcoded digest edit.

The two are reported separately and never collapsed:

| Concept | Where it lives | What it answers |
|---|---|---|
| Checksum identity | `molecule_source_observations.content_sha256`, `file_verification` | Are these the same bytes as the copy read by hand? |
| Source verification | `cms_dataset_releases.validation_status` + `validation_report` | Did this file pass provenance, schema, units and duplicate checks? |

An `unrecognised` checksum is **not** an error. CMS reissues these files; the parser
resolves columns from the file's own header either way.

## The validation workflow

Every ingested file enters `cms_dataset_releases` and is validated by
`services/sources/cms_release_registry.py`. Four checks, all recorded in
`validation_report`:

1. **provenance** — the publication URL is CMS's, on an allowlisted host; a file claiming
   archived provenance must say which URL it was actually retrieved from.
2. **schema** — the metric columns for the claimed reporting year resolve from the file's
   own header (`Tot_Dsg_Unts_{year}` and friends). A CMS rename fails here loudly.
3. **units** — every resolved metric carries the unit this engine expects. Claims are not
   dosage units; beneficiaries are not annual treated patients.
4. **duplicates** — the `Overall` roll-up rows are present, so per-manufacturer duplicates
   can be excluded. Without them brand totals cannot be de-duplicated and the file is
   rejected rather than double-counted.

Outcomes:

- **All pass** → `validated`, and the release is promoted to active.
- **Any fail** → `rejected`, kept with its report so the failure is visible, never promoted.
- **Digest already known** → returned as-is; repeated ingests do not churn the registry.

Promotion preserves history: the previous active release is marked `superseded`, never
deleted or rewritten, so an older forecast can still be traced to the file it used.

## Recurring metadata check

`app/forecasting_engine/services/sources/cms_metadata_check.py`, run monthly.

This application has **no scheduler runtime**, and this does not add one. Its established
pattern for operational tasks is a runnable command (`scripts/smoke_test.sh`,
`alembic upgrade head` on boot), so the check is a command:

```bash
python -m app.forecasting_engine.services.sources.cms_metadata_check
```

`render.yaml` runs it as a Render cron service (`0 6 1 * *`) against the same database.
Host cron or CI would serve equally well.

It reads CMS's own metadata through the HHS catalogue record
(`https://datahub.hhs.gov/api/views/xzs3-ddeh.json`, attribution `data.cms.gov`), which is
reachable where `data.cms.gov`'s API is not, and records one `cms_metadata_checks` row per
run: status, the latest reporting year seen, the publication date, and whether a new
release was detected.

**It never promotes anything.** A detected release is an instruction to a person: download
the new file and ingest it, at which point it goes through the validation workflow above.

## Freshness degrades rather than lying

Freshness is derived from these check rows, never from a configured constant:

| Condition | Reported |
|---|---|
| Recent successful check, loaded year ≥ latest seen | `current` |
| Recent successful check, a newer year published | `superseded` |
| No check has ever succeeded | `unknown` |
| Newest successful check older than 45 days | `unknown` |
| Check ran but was unreachable/errored | `unknown` |

If the scheduled job stops running, freshness decays to `unknown` within the grace period
instead of claiming "current" indefinitely.

## Labelling

The panel states, in words:

> **Latest published: 2024.** These are observed 2024 Medicare Part D figures, not
> current-year sales.

with the publication date and the last metadata check timestamp beside it. The reporting
year is always named, so nobody reads a 2024 utilization figure as this year's sales.

## When CMS publishes the 2025 file

1. The monthly check detects the new reporting year and flags `new_release_detected`; the
   panel surfaces it and freshness turns `superseded`.
2. Download the new file from the CMS publication URL.
3. Ingest it through the forecast panel or
   `POST /api/forecast/sources/cms-part-d/ingest`, recording where it came from.
4. It is validated on its own merits. If all four checks pass it is promoted; the 2024
   release becomes `superseded` and is retained.
5. No code change, and no digest edit, is required.

The descriptor's `verified_file` digests stay as a record of the copy that was read by
hand on 2026-09-29. They are evidence, not a gate.
