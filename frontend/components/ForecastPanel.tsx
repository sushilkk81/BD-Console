"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ApiError,
  Forecast,
  ForecastCollection,
  ForecastParameters,
  MetricKey,
  CmsSourceStatus,
  SourceObservation,
  SourceSearch,
  SourceStatus,
  getCmsSourceStatus,
  getForecast,
  importForecastSources,
  ingestCmsPartDFile,
  searchForecastSources,
  upsertForecast,
} from "@/lib/api";
import { MARKETS } from "@/lib/markets";
import { Card } from "@/components/Card";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/SelectField";
import { TextField } from "@/components/TextField";
import { EmptyState } from "@/components/EmptyState";

// Matching the dashboard's chart conventions.
const GRID_STROKE = "rgba(43, 46, 44, 0.12)";
const AXIS_STROKE = "rgba(43, 46, 44, 0.2)";
const AXIS_TICK = { fontSize: 12, fill: "rgba(43, 46, 44, 0.7)" };
const BASE_COLOR = "#1B7A4D";
const UPSIDE_COLOR = "#F0883E";
const ADDRESSABLE_COLOR = "rgba(43, 46, 44, 0.35)";

const METRICS: { value: MetricKey; label: string }[] = [
  { value: "patients", label: "Annual treated patients" },
  { value: "dosage_units", label: "Dosage units" },
  { value: "packs", label: "Packs" },
  { value: "api_kg", label: "API (kg contained)" },
  { value: "revenue", label: "Revenue" },
];

/** Blank means "not stated" and is sent as null — never silently defaulted to a number. */
function numOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function fmt(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

type Draft = {
  forecast_mode: "epidemiology" | "observed_volume";
  molecule: string;
  brand: string;
  geography: string;
  indication: string;
  forecast_start_year: string;
  launch_year: string;
  target_population: string;
  population_basis: string;
  treatment_basis: string;
  reference_units: string;
  reference_year: string;
  annual_growth_rate: string;
  reference_coverage_note: string;
  base_peak_share: string;
  upside_peak_share: string;
  ramp_speed: string;
  inflection_year: string;
  units_per_patient_per_year: string;
  units_per_patient_basis: string;
  units_per_pack: string;
  active_ingredient_mg_per_unit: string;
  company_capture_share: string;
  probability_of_success: string;
  net_price: string;
  price_currency: string;
  price_basis: string;
  source_observation_id: number | null;
  override_reason: string;
  overridden_source_value: string;
};

const EMPTY_DRAFT: Draft = {
  forecast_mode: "epidemiology",
  molecule: "", brand: "", geography: "", indication: "",
  forecast_start_year: String(new Date().getFullYear() + 1),
  launch_year: String(new Date().getFullYear() + 1),
  target_population: "", population_basis: "", treatment_basis: "",
  reference_units: "", reference_year: "", annual_growth_rate: "", reference_coverage_note: "",
  base_peak_share: "", upside_peak_share: "", ramp_speed: "0.8", inflection_year: "4",
  units_per_patient_per_year: "", units_per_patient_basis: "", units_per_pack: "",
  active_ingredient_mg_per_unit: "", company_capture_share: "", probability_of_success: "",
  net_price: "", price_currency: "", price_basis: "",
  source_observation_id: null, override_reason: "", overridden_source_value: "",
};

function draftFromForecast(forecast: Forecast): Draft {
  const a = forecast.assumption_summary as Record<string, unknown>;
  const str = (key: string) => (a[key] === null || a[key] === undefined ? "" : String(a[key]));
  return {
    ...EMPTY_DRAFT,
    forecast_mode: forecast.forecast_mode,
    molecule: str("molecule"), brand: str("brand"), geography: str("geography"),
    indication: str("indication"),
    forecast_start_year: str("forecast_start_year"), launch_year: str("launch_year"),
    target_population: str("target_population"), population_basis: str("population_basis"),
    treatment_basis: str("treatment_basis"), reference_units: str("reference_units"),
    reference_year: str("reference_year"), annual_growth_rate: str("annual_growth_rate"),
    reference_coverage_note: str("reference_coverage_note"),
    base_peak_share: str("base_peak_share"), upside_peak_share: str("upside_peak_share"),
    ramp_speed: str("ramp_speed"), inflection_year: str("inflection_year"),
    units_per_patient_per_year: str("units_per_patient_per_year"),
    units_per_patient_basis: str("units_per_patient_basis"),
    units_per_pack: str("units_per_pack"),
    active_ingredient_mg_per_unit: str("active_ingredient_mg_per_unit"),
    company_capture_share: str("company_capture_share"),
    probability_of_success: str("probability_of_success"),
    net_price: str("net_price"), price_currency: str("price_currency"),
    price_basis: str("price_basis"),
    override_reason: str("override_reason"),
    overridden_source_value: str("overridden_source_value"),
  };
}

/** Local-only completeness check. Nothing is sent until the draft can produce a forecast,
 *  and nothing missing is filled in with a guess — the field simply stays required. */
function draftProblems(draft: Draft): string[] {
  const problems: string[] = [];
  if (!draft.molecule.trim()) problems.push("Molecule is required.");
  if (!draft.geography.trim()) problems.push("Geography is required — it is never assumed.");
  if (numOrNull(draft.forecast_start_year) === null) problems.push("Forecast start year is required.");
  if (numOrNull(draft.launch_year) === null) problems.push("Launch year is required.");
  const base = numOrNull(draft.base_peak_share);
  const upside = numOrNull(draft.upside_peak_share);
  if (base === null) problems.push("Base peak share is required — market share is never assumed.");
  if (upside === null) problems.push("Upside peak share is required.");
  if (base !== null && upside !== null && base > upside) {
    problems.push("Base peak share must not exceed upside peak share.");
  }
  const ramp = numOrNull(draft.ramp_speed);
  if (ramp === null || ramp <= 0) problems.push("Ramp speed must be greater than 0.");
  const inflection = numOrNull(draft.inflection_year);
  if (inflection === null || inflection < 0.5 || inflection > 15) {
    problems.push("Inflection year must be between 0.5 and 15.");
  }
  if (draft.forecast_mode === "epidemiology") {
    if (numOrNull(draft.target_population) === null) {
      problems.push("Target population is required in epidemiology mode.");
    }
    if (!draft.population_basis) {
      problems.push("State whether the population is prevalence or incidence — they are never mixed.");
    }
    if (!draft.treatment_basis) {
      problems.push("State whether treatment is chronic or an annual course.");
    }
  } else {
    if (numOrNull(draft.reference_units) === null) {
      problems.push("Reference dosage units are required in observed-volume mode.");
    }
    if (numOrNull(draft.reference_year) === null) {
      problems.push("Reference data year is required — growth is measured from it.");
    }
    if (numOrNull(draft.annual_growth_rate) === null) {
      problems.push("Annual growth rate is required in observed-volume mode.");
    }
  }
  const priceParts = [draft.net_price.trim(), draft.price_currency.trim(), draft.price_basis.trim()];
  if (priceParts.some((p) => p !== "") && priceParts.some((p) => p === "")) {
    problems.push("A net price needs both a currency and a price basis.");
  }
  if (draft.overridden_source_value.trim() !== "" && !draft.override_reason.trim()) {
    problems.push("An override needs a reason.");
  }
  return problems;
}

function toParameters(draft: Draft, skuRowId: number | null): ForecastParameters {
  const epi = draft.forecast_mode === "epidemiology";
  return {
    sku_row_id: skuRowId,
    molecule: draft.molecule.trim(),
    brand: draft.brand.trim() || null,
    geography: draft.geography.trim(),
    indication: draft.indication.trim() || null,
    forecast_start_year: numOrNull(draft.forecast_start_year) as number,
    launch_year: numOrNull(draft.launch_year) as number,
    forecast_mode: draft.forecast_mode,
    target_population: epi ? numOrNull(draft.target_population) : null,
    population_basis: epi ? ((draft.population_basis || null) as "prevalence" | "incidence" | null) : null,
    treatment_basis: epi ? ((draft.treatment_basis || null) as "chronic" | "annual_course" | null) : null,
    reference_units: epi ? null : numOrNull(draft.reference_units),
    reference_year: epi ? null : numOrNull(draft.reference_year),
    annual_growth_rate: epi ? null : numOrNull(draft.annual_growth_rate),
    reference_coverage_note: epi ? null : draft.reference_coverage_note.trim() || null,
    base_peak_share: numOrNull(draft.base_peak_share) as number,
    upside_peak_share: numOrNull(draft.upside_peak_share) as number,
    ramp_speed: numOrNull(draft.ramp_speed) as number,
    inflection_year: numOrNull(draft.inflection_year) as number,
    units_per_patient_per_year: numOrNull(draft.units_per_patient_per_year),
    units_per_patient_basis: draft.units_per_patient_basis.trim() || null,
    units_per_pack: numOrNull(draft.units_per_pack),
    active_ingredient_mg_per_unit: numOrNull(draft.active_ingredient_mg_per_unit),
    company_capture_share: epi ? numOrNull(draft.company_capture_share) : null,
    probability_of_success: numOrNull(draft.probability_of_success),
    net_price: draft.net_price.trim() || null,
    price_currency: draft.price_currency.trim().toUpperCase() || null,
    price_basis: (draft.price_basis || null) as ForecastParameters["price_basis"],
    source_observation_id: draft.source_observation_id,
    override_reason: draft.override_reason.trim() || null,
    overridden_source_value: numOrNull(draft.overridden_source_value),
  };
}

function seriesFor(forecast: Forecast, scenario: "base_case" | "upside_case", metric: MetricKey) {
  const s = forecast[scenario];
  switch (metric) {
    case "patients":
      return s.patients;
    case "dosage_units":
      return s.business_dosage_units;
    case "packs":
      return s.business_packs;
    case "api_kg":
      return s.business_api_kg;
    case "revenue":
      return s.business_revenue ? s.business_revenue.map(Number) : null;
  }
}

function addressableFor(forecast: Forecast, metric: MetricKey) {
  if (metric === "patients") return forecast.base_case.addressable_patients;
  if (metric === "dosage_units") return forecast.base_case.addressable_dosage_units;
  return null;
}

/** The three non-results are shown as three different things, because they call for
 *  three different actions. Conflating them would let "we couldn't ask" read as
 *  "this molecule has no Medicare utilization". */
const STATUS_PRESENTATION: Record<
  Exclude<SourceStatus, "available">,
  { heading: string; tone: string; guidance: string }
> = {
  api_unavailable: {
    heading: "Source unavailable — we could not reach CMS",
    tone: "bg-orange-500/10 text-orange-700",
    guidance:
      "This is not a statement about the molecule. The dataset is configured and verified; " +
      "upload the official CMS CSV below to use the same figures.",
  },
  configuration_incomplete: {
    heading: "Not configured — this deployment cannot query the source yet",
    tone: "bg-orange-500/10 text-orange-700",
    guidance:
      "The dataset descriptor or the file's columns did not resolve. No lookup was attempted.",
  },
  no_matching_records: {
    heading: "No matching records — the source answered and has nothing for this query",
    tone: "bg-ink-700/5 text-ink-700/80",
    guidance:
      "CMS Part D covers the US only, and only drugs dispensed to Part D enrollees. " +
      "For other markets use an import or manual entry.",
  },
};

const FILE_VERIFICATION_LABEL: Record<string, string> = {
  verified: "Matches the verified copy",
  unrecognised: "Usable, but not the verified copy",
  mismatch: "Checksum mismatch",
};
const FRESHNESS_LABEL: Record<string, string> = {
  current: "Latest published year",
  superseded: "A newer year has been published",
  unknown: "No reporting year loaded yet",
};
const CONNECTIVITY_LABEL: Record<string, string> = {
  reachable: "Live CMS API reachable",
  blocked: "Live CMS API blocked",
  error: "Live CMS API error",
  not_checked: "Live CMS API not checked",
};

function StatusTile({ heading, value, detail, tone }: {
  heading: string; value: string; detail?: string | null; tone: string;
}) {
  return (
    <div className={`rounded-lg px-3 py-2.5 ${tone}`}>
      <p className="font-body text-[11px] uppercase tracking-wide opacity-70">{heading}</p>
      <p className="mt-0.5 font-body text-sm font-medium">{value}</p>
      {detail && <p className="mt-0.5 font-body text-xs opacity-75">{detail}</p>}
    </div>
  );
}

/** The three source facts are shown as three tiles, never merged into one badge: a
 *  verified, current file and a blocked API are independent conditions. */
function CmsStatusStrip({ status, onCheckApi, checking }: {
  status: CmsSourceStatus; onCheckApi: () => void; checking: boolean;
}) {
  const good = "bg-forest-600/10 text-forest-900";
  const warn = "bg-orange-500/10 text-orange-700";
  const neutral = "bg-ink-700/5 text-ink-700/80";

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-ink-700/10 p-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="font-display text-sm font-semibold text-forest-900">
          {status.dataset_title}
        </h4>
        <span className="font-body text-xs text-ink-700/60">
          Reporting year{" "}
          <span className="font-mono text-ink-700">{status.reporting_year ?? "—"}</span>
          {" · "}last successful refresh{" "}
          <span className="font-mono text-ink-700">
            {status.last_successful_refresh
              ? new Date(status.last_successful_refresh).toLocaleString()
              : "never"}
          </span>
        </span>
      </div>

      {status.freshness_label && (
        <p className="font-body text-xs text-ink-700/80">{status.freshness_label}</p>
      )}
      {status.new_release_detected && (
        <p className="rounded-lg bg-orange-500/10 px-3 py-2 font-body text-xs text-orange-700">
          A newer CMS release has been detected. {status.metadata_check_detail} It must pass
          validation before it replaces the active release.
        </p>
      )}

      <div className="grid gap-2 sm:grid-cols-3">
        <StatusTile
          heading="File verification"
          value={status.file_verification
            ? FILE_VERIFICATION_LABEL[status.file_verification]
            : "No file loaded"}
          detail={status.file_sha256 ? `sha256 ${status.file_sha256.slice(0, 16)}…` : null}
          tone={status.file_verification === "verified" ? good
            : status.file_verification === "mismatch" ? warn : neutral}
        />
        <StatusTile
          heading="Publication freshness"
          value={FRESHNESS_LABEL[status.publication_freshness]}
          detail={[
            status.published_on ? `Published ${status.published_on}` : null,
            `Metadata checked ${status.last_metadata_check_at
              ? new Date(status.last_metadata_check_at).toLocaleDateString()
              : "never"}`,
          ].filter(Boolean).join(" · ")}
          tone={status.publication_freshness === "current" ? good
            : status.publication_freshness === "superseded" ? warn : neutral}
        />
        <StatusTile
          heading="API connectivity"
          value={CONNECTIVITY_LABEL[status.api_connectivity]}
          detail={status.api_http_status ? `HTTP ${status.api_http_status}` : null}
          tone={status.api_connectivity === "reachable" ? good
            : status.api_connectivity === "blocked" || status.api_connectivity === "error"
              ? warn : neutral}
        />
      </div>

      {status.active_release_checks && (
        <p className="font-body text-xs text-ink-700/70">
          Active release <strong>{status.active_release_status}</strong>
          {status.active_release_validated_at &&
            ` on ${new Date(status.active_release_validated_at).toLocaleDateString()}`}
          {" — "}
          {status.active_release_checks.map((c) => `${c.name} ${c.passed ? "✓" : "✗"}`).join(", ")}.
          A checksum identifies the file; these checks are what verify it.
        </p>
      )}

      {status.last_refresh_provenance === "archived_cms_publication" && (
        <p className="font-body text-xs text-ink-700/70">
          Loaded from an <strong>archived CMS publication</strong>, not live CMS access.
          Published at{" "}
          <span className="break-all font-mono text-[11px]">{status.publication_url}</span>
          {status.retrieval_url && (
            <>
              {" "}· retrieved from{" "}
              <span className="break-all font-mono text-[11px]">{status.retrieval_url}</span>
            </>
          )}
          {status.archive_capture_date && (
            <> · captured {new Date(status.archive_capture_date).toLocaleDateString()}</>
          )}
        </p>
      )}

      {status.api_connectivity === "blocked" && status.support_summary && (
        <div className="rounded-lg bg-orange-500/10 px-3 py-2">
          <p className="font-body text-xs text-orange-700">
            Live CMS access is blocked at the edge. Imported data below is unaffected. For a
            CMS support ticket:
          </p>
          <p className="mt-1 break-all font-mono text-[11px] text-orange-700">
            {status.support_summary}
          </p>
        </div>
      )}

      <div>
        <Button variant="secondary" onClick={onCheckApi} loading={checking}>
          Check CMS API connectivity
        </Button>
      </div>
    </div>
  );
}

function SourceStatusNotice({ search }: { search: SourceSearch }) {
  const key = search.status === "available" ? "no_matching_records" : search.status;
  const presentation = STATUS_PRESENTATION[key];
  return (
    <div role="status" className={`rounded-lg px-3.5 py-2.5 ${presentation.tone}`}>
      <p className="font-body text-sm font-medium">{presentation.heading}</p>
      {search.unavailable_reason && (
        <p className="mt-1 font-body text-xs opacity-90">{search.unavailable_reason}</p>
      )}
      <p className="mt-1 font-body text-xs opacity-75">{presentation.guidance}</p>
    </div>
  );
}

export function ForecastPanel({
  token,
  requestId,
  defaultBrand,
  defaultMarket,
}: {
  token: string;
  requestId: number;
  defaultBrand?: string;
  defaultMarket?: string;
}) {
  const [collection, setCollection] = useState<ForecastCollection | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [metric, setMetric] = useState<MetricKey>("patients");
  const [search, setSearch] = useState<SourceSearch | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [csv, setCsv] = useState("");
  const [importing, setImporting] = useState(false);
  const [cmsIngesting, setCmsIngesting] = useState(false);
  const [cmsStatus, setCmsStatus] = useState<CmsSourceStatus | null>(null);
  const [checkingApi, setCheckingApi] = useState(false);

  const forecast = collection?.forecasts[0] ?? null;

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const data = await getForecast(token, requestId);
      setCollection(data);
      setConflict(false);
      if (data.forecasts.length > 0) {
        setDraft(draftFromForecast(data.forecasts[0]));
        setEditing(false);
      } else {
        setDraft((d) => ({
          ...d,
          brand: d.brand || defaultBrand || "",
          geography: d.geography || defaultMarket || "",
        }));
      }
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "We couldn't load the forecast.");
    } finally {
      setLoading(false);
    }
  }, [token, requestId, defaultBrand, defaultMarket]);

  const loadCmsStatus = useCallback(async (checkApi = false) => {
    try {
      setCmsStatus(await getCmsSourceStatus(token, requestId, checkApi));
    } catch {
      // The status strip is informational; a failure here must not block the panel.
      setCmsStatus(null);
    }
  }, [token, requestId]);

  useEffect(() => {
    void load();
    void loadCmsStatus(false);
  }, [load, loadCmsStatus]);

  async function handleCheckApi() {
    setCheckingApi(true);
    try {
      await loadCmsStatus(true);
    } finally {
      setCheckingApi(false);
    }
  }

  const problems = useMemo(() => draftProblems(draft), [draft]);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  async function handleSave() {
    if (problems.length > 0) return; // drafts stay local until they are valid
    setSaving(true);
    setSaveError("");
    setFieldErrors({});
    setConflict(false);
    try {
      const data = await upsertForecast(
        token, requestId, forecast?.revision ?? 0,
        toParameters(draft, forecast?.sku_row_id ?? null),
        draft.override_reason.trim() || undefined
      );
      setCollection(data);
      if (data.forecasts.length > 0) setDraft(draftFromForecast(data.forecasts[0]));
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflict(true);
        setSaveError(err.message);
      } else if (err instanceof ApiError) {
        setSaveError(err.message);
        setFieldErrors(err.fieldErrors);
      } else {
        setSaveError("We couldn't save those assumptions.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleSearch() {
    setSearching(true);
    setSearchError("");
    try {
      setSearch(await searchForecastSources(token, {
        request_id: requestId,
        geography: draft.geography.trim(),
        molecule: draft.molecule.trim() || undefined,
        brand: draft.brand.trim() || undefined,
      }));
    } catch (err) {
      setSearchError(err instanceof ApiError ? err.message : "We couldn't search sources.");
    } finally {
      setSearching(false);
    }
  }

  async function handleImport() {
    setImporting(true);
    setSearchError("");
    try {
      setSearch(await importForecastSources(token, requestId, csv));
      setCsv("");
    } catch (err) {
      setSearchError(err instanceof ApiError ? err.message : "We couldn't import that data.");
    } finally {
      setImporting(false);
    }
  }

  /** Reads the official CMS bulk CSV the user downloaded from data.cms.gov. Kept as a
   *  separate action from the generic import so its provenance stays the CMS URL. */
  async function handleCmsFile(file: File) {
    setCmsIngesting(true);
    setSearchError("");
    try {
      setSearch(await ingestCmsPartDFile(token, {
        request_id: requestId,
        payload: await file.text(),
        molecule: draft.molecule.trim() || undefined,
        brand: draft.brand.trim() || undefined,
        retrieval_note: `official CMS CSV download (${file.name})`,
      }));
      await loadCmsStatus(false);
    } catch (err) {
      setSearchError(err instanceof ApiError ? err.message : "We couldn't read that CMS file.");
    } finally {
      setCmsIngesting(false);
    }
  }

  /** Adopting evidence only pre-fills the draft. It never overwrites a saved assumption
   *  on its own — the reviewer still has to save, and the source is recorded alongside. */
  function adoptAsBaseline(obs: SourceObservation) {
    if (obs.value === null) return;
    setEditing(true);
    setDraft((d) => ({
      ...d,
      forecast_mode: "observed_volume",
      reference_units: String(Math.round(Number(obs.value))),
      reference_year: obs.period_label.slice(0, 4),
      reference_coverage_note: obs.coverage,
      geography: d.geography || obs.geography,
      molecule: d.molecule || obs.molecule || "",
      source_observation_id: obs.id,
      target_population: "",
      population_basis: "",
      treatment_basis: "",
      company_capture_share: "",
    }));
  }

  const chartData = useMemo(() => {
    if (!forecast) return [];
    const base = seriesFor(forecast, "base_case", metric);
    const upside = seriesFor(forecast, "upside_case", metric);
    const addressable = addressableFor(forecast, metric);
    return forecast.calendar_years.map((year, i) => ({
      year,
      Base: base ? base[i] : null,
      Upside: upside ? upside[i] : null,
      Addressable: addressable ? addressable[i] : null,
    }));
  }, [forecast, metric]);

  const metricAvailable = forecast ? seriesFor(forecast, "base_case", metric) !== null : false;
  const staleSources = forecast?.source_references.filter((s) => s.stale) ?? [];

  if (loading) {
    return (
      <Card>
        <div className="flex animate-pulse flex-col gap-3 motion-reduce:animate-none">
          <span className="block h-5 w-64 rounded bg-ink-700/10" />
          <span className="block h-40 w-full rounded bg-ink-700/10" />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-base font-semibold text-forest-900">
              Molecule market intelligence &amp; volume forecast
            </h2>
            <p className="mt-1 font-body text-xs text-ink-700/70">
              Ten-year Base and Upside projections from stated assumptions. Evidence-backed —
              not a reproduction of IQVIA or Newport coverage.
            </p>
          </div>
          {forecast && (
            <span className="rounded-md bg-ink-700/5 px-2.5 py-1 font-mono text-xs text-ink-700/70">
              rev {forecast.revision} · model {forecast.model_version}
            </span>
          )}
        </div>

        {loadError && <Banner message={loadError} onDismiss={() => setLoadError("")} />}
        {conflict && (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-orange-500/10 px-3.5 py-2.5"
          >
            <p className="font-body text-sm text-orange-700">
              {saveError} Your edits are still on screen — reload the saved version before saving again.
            </p>
            <Button variant="secondary" onClick={() => void load()}>
              Reload saved version
            </Button>
          </div>
        )}
        {saveError && !conflict && <Banner message={saveError} onDismiss={() => setSaveError("")} />}

        {!forecast && !editing && (
          <EmptyState
            message="No forecast saved for this request yet. Nothing is assumed on your behalf — geography, population, market share, dose and price all have to be stated."
            action={<Button onClick={() => setEditing(true)}>Add forecast assumptions</Button>}
          />
        )}

        {forecast && !editing && (
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-72">
              <SelectField
                label="Metric"
                name="forecast-metric"
                value={metric}
                onChange={(v) => setMetric(v as MetricKey)}
                options={METRICS}
              />
            </div>
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Edit assumptions
            </Button>
          </div>
        )}
      </Card>

      {/* --- Assumptions editor ------------------------------------------- */}
      {editing && (
        <Card className="flex flex-col gap-5">
          <h3 className="font-display text-sm font-semibold text-forest-900">Assumptions</h3>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <SelectField
              label="Input mode"
              name="forecast_mode"
              value={draft.forecast_mode}
              onChange={(v) => set("forecast_mode", v as Draft["forecast_mode"])}
              options={[
                { value: "epidemiology", label: "Epidemiology (patient-derived)" },
                { value: "observed_volume", label: "Observed volume (market baseline)" },
              ]}
            />
            <TextField label="Molecule" name="molecule" value={draft.molecule}
              onChange={(v) => set("molecule", v)} error={fieldErrors.molecule} />
            <TextField label="Brand (optional)" name="brand" value={draft.brand}
              onChange={(v) => set("brand", v)} />
            <SelectField
              label="Geography"
              name="geography"
              value={draft.geography}
              onChange={(v) => set("geography", v)}
              options={MARKETS}
              placeholder="Select a market"
              error={fieldErrors.geography}
            />
            <TextField label="Indication (optional)" name="indication" value={draft.indication}
              onChange={(v) => set("indication", v)} />
            <TextField label="Forecast start year" name="forecast_start_year"
              value={draft.forecast_start_year} onChange={(v) => set("forecast_start_year", v)} />
            <TextField label="Launch year" name="launch_year" value={draft.launch_year}
              onChange={(v) => set("launch_year", v)} />
          </div>

          {draft.forecast_mode === "epidemiology" ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <TextField label="Eligible patient population (N)" name="target_population"
                value={draft.target_population} onChange={(v) => set("target_population", v)}
                error={fieldErrors.target_population} />
              <SelectField label="Population basis" name="population_basis"
                value={draft.population_basis} onChange={(v) => set("population_basis", v)}
                placeholder="Prevalence or incidence"
                options={[
                  { value: "prevalence", label: "Prevalence (living with the disease)" },
                  { value: "incidence", label: "Incidence (newly diagnosed this year)" },
                ]} />
              <SelectField label="Treatment basis" name="treatment_basis"
                value={draft.treatment_basis} onChange={(v) => set("treatment_basis", v)}
                placeholder="Chronic or annual course"
                options={[
                  { value: "chronic", label: "Chronic ongoing therapy" },
                  { value: "annual_course", label: "One annual treatment course" },
                ]} />
              <TextField label="Our company capture share (0–1)" name="company_capture_share"
                value={draft.company_capture_share}
                onChange={(v) => set("company_capture_share", v)} />
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <TextField label="Reference dosage units" name="reference_units"
                value={draft.reference_units} onChange={(v) => set("reference_units", v)}
                error={fieldErrors.reference_units} />
              <TextField label="Reference data year" name="reference_year"
                value={draft.reference_year} onChange={(v) => set("reference_year", v)} />
              <TextField label="Annual growth rate (e.g. 0.07)" name="annual_growth_rate"
                value={draft.annual_growth_rate} onChange={(v) => set("annual_growth_rate", v)} />
              <TextField label="Reference coverage note" name="reference_coverage_note"
                value={draft.reference_coverage_note}
                onChange={(v) => set("reference_coverage_note", v)} />
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <TextField
              label={draft.forecast_mode === "epidemiology"
                ? "Base peak patient share (0–1)" : "Base peak capture share (0–1)"}
              name="base_peak_share" value={draft.base_peak_share}
              onChange={(v) => set("base_peak_share", v)} error={fieldErrors.base_peak_share} />
            <TextField
              label={draft.forecast_mode === "epidemiology"
                ? "Upside peak patient share (0–1)" : "Upside peak capture share (0–1)"}
              name="upside_peak_share" value={draft.upside_peak_share}
              onChange={(v) => set("upside_peak_share", v)} error={fieldErrors.upside_peak_share} />
            <TextField label="Ramp speed (> 0)" name="ramp_speed" value={draft.ramp_speed}
              onChange={(v) => set("ramp_speed", v)} error={fieldErrors.ramp_speed} />
            <TextField label="Inflection year (0.5–15)" name="inflection_year"
              value={draft.inflection_year} onChange={(v) => set("inflection_year", v)}
              error={fieldErrors.inflection_year} />
          </div>

          <div>
            <h4 className="mb-2 font-display text-xs font-semibold uppercase tracking-wide text-ink-700/60">
              Unit conversions — each metric appears only when its inputs are supplied
            </h4>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <TextField label="Dosage units per patient per year" name="units_per_patient_per_year"
                value={draft.units_per_patient_per_year}
                onChange={(v) => set("units_per_patient_per_year", v)} />
              <TextField label="Treatment/exposure basis for that figure" name="units_per_patient_basis"
                value={draft.units_per_patient_basis}
                onChange={(v) => set("units_per_patient_basis", v)} />
              <TextField label="Dosage units per pack" name="units_per_pack"
                value={draft.units_per_pack} onChange={(v) => set("units_per_pack", v)} />
              <TextField label="Active ingredient mg per unit" name="active_ingredient_mg_per_unit"
                value={draft.active_ingredient_mg_per_unit}
                onChange={(v) => set("active_ingredient_mg_per_unit", v)} />
            </div>
          </div>

          <div>
            <h4 className="mb-2 font-display text-xs font-semibold uppercase tracking-wide text-ink-700/60">
              Optional net price — gross public spending is never used as net revenue
            </h4>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <TextField label="Net price" name="net_price" value={draft.net_price}
                onChange={(v) => set("net_price", v)} />
              <TextField label="Currency (ISO, e.g. USD)" name="price_currency"
                value={draft.price_currency} onChange={(v) => set("price_currency", v)} />
              <SelectField label="Price basis" name="price_basis" value={draft.price_basis}
                onChange={(v) => set("price_basis", v)} placeholder="Per which unit?"
                options={[
                  { value: "per_dosage_unit", label: "Per dosage unit" },
                  { value: "per_pack", label: "Per pack" },
                  { value: "per_api_kg", label: "Per kg API" },
                ]} />
              <TextField label="Probability of success (0–1, reported separately)"
                name="probability_of_success" value={draft.probability_of_success}
                onChange={(v) => set("probability_of_success", v)} />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <TextField label="Overridden source value (optional)" name="overridden_source_value"
              value={draft.overridden_source_value}
              onChange={(v) => set("overridden_source_value", v)} />
            <TextField label="Reason for the override" name="override_reason"
              value={draft.override_reason} onChange={(v) => set("override_reason", v)} />
          </div>

          {problems.length > 0 && (
            <div className="rounded-lg bg-orange-500/10 px-3.5 py-2.5">
              <p className="mb-1 font-body text-sm font-medium text-orange-700">
                Not saved yet — this draft stays on your screen until it is complete:
              </p>
              <ul className="list-inside list-disc font-body text-xs text-orange-700">
                {problems.map((p) => <li key={p}>{p}</li>)}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <Button onClick={() => void handleSave()} loading={saving} disabled={problems.length > 0}>
              {forecast ? "Save assumptions" : "Create forecast"}
            </Button>
            <Button variant="secondary" onClick={() => { setEditing(false); void load(); }}>
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {/* --- Chart + table ------------------------------------------------- */}
      {forecast && !editing && (
        <>
          <Card className="flex flex-col gap-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-display text-sm font-semibold text-forest-900">
                {METRICS.find((m) => m.value === metric)?.label} — Base vs Upside
              </h3>
              <span className="font-body text-xs text-ink-700/60">
                Modelled projection · {forecast.calendar_years[0]}–
                {forecast.calendar_years[forecast.calendar_years.length - 1]}
              </span>
            </div>
            {metricAvailable ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={chartData}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="year" tick={AXIS_TICK} stroke={AXIS_STROKE} />
                  <YAxis tick={AXIS_TICK} stroke={AXIS_STROKE} width={80}
                    tickFormatter={(v: number) => fmt(v)} />
                  <Tooltip formatter={(v: number) => fmt(v)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {chartData.some((d) => d.Addressable !== null) && (
                    <Line type="monotone" dataKey="Addressable" name="Addressable (total demand)"
                      stroke={ADDRESSABLE_COLOR} strokeDasharray="4 4" dot={false} />
                  )}
                  <Line type="monotone" dataKey="Base" name="Base case (our volume)"
                    stroke={BASE_COLOR} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="Upside" name="Upside case (our volume)"
                    stroke={UPSIDE_COLOR} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState message={
                `${METRICS.find((m) => m.value === metric)?.label} is not available: its conversion ` +
                "input was not supplied. It is reported as unavailable rather than as zero."
              } />
            )}
          </Card>

          <Card className="flex flex-col gap-3">
            <h3 className="font-display text-sm font-semibold text-forest-900">Annual figures</h3>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] border-collapse">
                <thead>
                  <tr className="border-b border-ink-700/10 text-left">
                    <th className="px-3 py-2 font-body text-xs font-medium text-ink-700/70">Year</th>
                    <th className="px-3 py-2 text-right font-body text-xs font-medium text-ink-700/70">Base</th>
                    <th className="px-3 py-2 text-right font-body text-xs font-medium text-ink-700/70">Upside</th>
                  </tr>
                </thead>
                <tbody>
                  {chartData.map((row) => (
                    <tr key={row.year} className="border-b border-ink-700/5">
                      <td className="px-3 py-2 font-mono text-sm text-ink-700">{row.year}</td>
                      <td className="px-3 py-2 text-right font-mono text-sm text-ink-700">{fmt(row.Base)}</td>
                      <td className="px-3 py-2 text-right font-mono text-sm text-ink-700">{fmt(row.Upside)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="font-body text-xs text-ink-700/60">
              Rounded for display only; stored and calculated at full precision.
            </p>
          </Card>

          {forecast.warnings.length > 0 && (
            <Card className="flex flex-col gap-2">
              <h3 className="font-display text-sm font-semibold text-forest-900">
                What this forecast does and does not claim
              </h3>
              <ul className="list-inside list-disc font-body text-xs text-ink-700/80">
                {forecast.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </Card>
          )}
        </>
      )}

      {/* --- Evidence ------------------------------------------------------ */}
      <Card className="flex flex-col gap-4">
        <div>
          <h3 className="font-display text-sm font-semibold text-forest-900">
            Observed utilization evidence
          </h3>
          <p className="mt-1 font-body text-xs text-ink-700/70">
            Measured figures from a named source — shown separately from the modelled projection
            above, and never merged into your assumptions without you adopting them.
          </p>
        </div>

        {cmsStatus && (
          <CmsStatusStrip status={cmsStatus} onCheckApi={() => void handleCheckApi()}
            checking={checkingApi} />
        )}

        {staleSources.length > 0 && (
          <div role="status" className="rounded-lg bg-orange-500/10 px-3.5 py-2.5">
            <p className="font-body text-sm text-orange-700">
              {staleSources.length} cited source(s) are older than six months — re-check before relying on them.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <Button variant="secondary" onClick={() => void handleSearch()} loading={searching}
            disabled={!draft.geography.trim() || !(draft.molecule.trim() || draft.brand.trim())}>
            Search public sources
          </Button>
          <span className="font-body text-xs text-ink-700/60">
            Needs a geography and a molecule or brand — neither is guessed.
          </span>
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-ink-700/10 px-3.5 py-3">
          <label htmlFor="cms-file" className="font-body text-sm font-medium text-ink-700">
            Or load the official CMS Part D file
            {cmsIngesting && <span className="ml-2 text-xs text-ink-700/60">reading…</span>}
          </label>
          <p className="font-body text-xs text-ink-700/60">
            Medicare Part D Spending by Drug (DSD_PTD_…_BGM.csv), downloaded from data.cms.gov.
            Columns are read from the file&apos;s own header, and the CMS URL it is published at
            is recorded as the source.
          </p>
          <input
            id="cms-file"
            type="file"
            accept=".csv,text/csv"
            disabled={cmsIngesting}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleCmsFile(file);
              e.target.value = "";
            }}
            className="font-body text-xs text-ink-700 file:mr-3 file:rounded-lg file:border file:border-forest-600 file:bg-white file:px-3 file:py-1.5 file:font-body file:text-xs file:text-forest-600"
          />
        </div>
        {searchError && <Banner message={searchError} onDismiss={() => setSearchError("")} />}

        {search && !search.available && <SourceStatusNotice search={search} />}

        {search && search.available && search.results.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse">
              <thead>
                <tr className="border-b border-ink-700/10 text-left">
                  {["Source", "Metric", "Value", "Unit", "Period", "Coverage", ""].map((h) => (
                    <th key={h} className="px-3 py-2 font-body text-xs font-medium text-ink-700/70">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {search.results.map((obs, i) => (
                  <tr key={`${obs.id ?? "new"}-${obs.metric}-${i}`} className="border-b border-ink-700/5 align-top">
                    <td className="px-3 py-2 font-body text-xs text-ink-700">
                      <span className="rounded bg-forest-600/10 px-1.5 py-0.5 font-medium text-forest-900">
                        Observed
                      </span>
                      <span className="ml-2">{obs.source_kind}</span>
                      {obs.ambiguous_match && (
                        <span className="ml-2 rounded bg-orange-500/10 px-1.5 py-0.5 text-orange-700">
                          ambiguous match
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-body text-xs text-ink-700">{obs.metric}</td>
                    <td className="px-3 py-2 font-mono text-xs text-ink-700">
                      {obs.value === null
                        ? <span className="text-ink-700/50">suppressed / not reported</span>
                        : Number(obs.value).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 font-body text-xs text-ink-700">
                      {obs.unit}{obs.currency ? ` (${obs.currency})` : ""}
                    </td>
                    <td className="px-3 py-2 font-body text-xs text-ink-700">{obs.period_label}</td>
                    <td className="px-3 py-2 font-body text-xs text-ink-700/70">{obs.coverage}</td>
                    <td className="px-3 py-2">
                      {obs.value !== null && obs.metric === "dosage_units" && (
                        <Button variant="secondary" onClick={() => adoptAsBaseline(obs)}>
                          Use as baseline
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {search && search.warnings.length > 0 && (
          <ul className="list-inside list-disc font-body text-xs text-orange-700">
            {search.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        )}

        <div className="flex flex-col gap-2">
          <label htmlFor="forecast-csv" className="font-body text-sm font-medium text-ink-700">
            Import licensed or manually collected data (CSV)
          </label>
          <p className="font-body text-xs text-ink-700/60">
            Header row required: geography, coverage, period_label, metric, unit, value — plus
            optional molecule, brand, strength, dosage_form, currency, source_url,
            source_identifier, transformation. Leave value blank where the source suppressed it.
          </p>
          <textarea
            id="forecast-csv"
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            rows={4}
            placeholder="geography,coverage,period_label,metric,unit,value"
            className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-mono text-xs text-ink-700"
          />
          <div>
            <Button variant="secondary" onClick={() => void handleImport()} loading={importing}
              disabled={!csv.trim()}>
              Import rows
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
