export class ApiError extends Error {
  status: number;
  fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

async function parseError(resp: Response, fallback: string): Promise<ApiError> {
  try {
    const body = await resp.json();
    if (resp.status === 422 && Array.isArray(body.detail)) {
      const fieldErrors: Record<string, string> = {};
      for (const item of body.detail) {
        const field = item.loc?.[item.loc.length - 1];
        if (typeof field === "string") fieldErrors[field] = item.msg;
      }
      return new ApiError(resp.status, "Check the highlighted fields and try again.", fieldErrors);
    }
    if (typeof body.detail === "string") {
      return new ApiError(resp.status, body.detail);
    }
  } catch {
    // response wasn't JSON — fall through to the generic message
  }
  return new ApiError(resp.status, fallback);
}

export async function login(name: string, email: string, role?: string, title?: string, phone?: string) {
  const resp = await fetch(`/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, role, title, phone }),
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't sign you in — check your name and email and try again.");
  }
  return resp.json() as Promise<{
    access_token: string;
    token_type: string;
    user: { id: number; org_id: number; org_name: string; name: string; email: string; role: string };
    session_id: string | null;
  }>;
}

export type SkuRow = {
  id: number;
  strength: string;
  cartridge: string;
  fill_ml: number;
  batch_size_l: number | null;
};
export type ServiceSelection = {
  id: number;
  sku_row_id: number;
  standard_dv: boolean;
  threshold: boolean;
  ifu: boolean;
  human_factor: boolean;
};
export type RequestRow = {
  id: number;
  org_id: number;
  org_name: string;
  brand: string;
  market: string;
  device: string | null;
  status: string;
  total: number;
  assigned_kam_id: number | null;
  assigned_kam_name: string | null;
  suggested_kam_id: number | null;
  suggested_kam_name: string | null;
  viscosity_val: number | null;
  differentiated: boolean;
  chosen_option: number | null;
  severity: string | null;
  timeline_months: number | null;
  comment: string | null;
  urgency: string | null;
  kam_cost_usd: number | null;
  kam_timeline_months: number | null;
  kam_notes: string | null;
  exhibit_batch_start: string | null;
  exhibit_batch_end: string | null;
  tentative_approval_months: number | null;
  assembly_machine_qualification: boolean | null;
  assembly_qualification_qty: number | null;
  assembly_qualification_date: string | null;
  platform_design_verification_request: boolean | null;
  sample_request: boolean | null;
  sample_request_qty: number | null;
};
export type RequestDetail = RequestRow & { sku_rows: SkuRow[]; service_selections: ServiceSelection[] };

export type ReferenceProduct = {
  brand: string;
  molecule: string;
  device: string;
  strengths: string[];
  visc_val: number;
  visc_ref: string;
  cartridge: string;
  presentations: Record<string, { cartridge: string; fill_ml: number }>;
};

export type PlatformOptionRow = {
  sku: string;
  cartridge: string;
  platform: string | null;
  cls: string | null;
  sub: string | null;
  resolution: string | null;
  lockout: string | null;
  mech: string | null;
  band: string;
  pct: number | null;
  fallback: boolean;
  visc_limited: boolean;
};
export type PlatformOptions = { options: Record<"1" | "2" | "3", PlatformOptionRow[]> };

export async function createRequest(
  token: string,
  body: {
    brand: string;
    market: string;
    strengths?: string[];
    viscosity_val?: number | null;
    device?: string | null;
    differentiated?: boolean;
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't submit that request — try again.");
  }
  return resp.json();
}

export async function listRequests(token: string): Promise<RequestRow[]> {
  const resp = await fetch(`/api/requests`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't load your requests — try again.");
  }
  return resp.json();
}

export async function getRequestCount(token: string): Promise<number> {
  const resp = await fetch(`/api/requests/count`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't load your request count — try again.");
  }
  const body = (await resp.json()) as { count: number };
  return body.count;
}

export async function listReferenceProducts(token: string): Promise<ReferenceProduct[]> {
  const resp = await fetch(`/api/reference-products`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load reference products — try again.");
  return resp.json();
}

export type LookedUpStrength = { strength: string; cartridge: string; fill_ml: number };
export type StrengthLookup = {
  found: boolean;
  brand: string;
  molecule: string | null;
  device: string | null;
  strengths: LookedUpStrength[];
  citation: string | null;
};
export type ViscosityLookup = {
  found: boolean;
  brand: string;
  visc_val_low: number | null;
  visc_val_high: number | null;
  citations: string[];
};

export async function lookupStrengths(token: string, brand: string, market: string): Promise<StrengthLookup> {
  const resp = await fetch(`/api/reference-lookup/strengths`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ brand, market }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't look that up — try again.");
  return resp.json();
}

export async function lookupViscosity(token: string, brand: string, molecule?: string): Promise<ViscosityLookup> {
  const resp = await fetch(`/api/reference-lookup/viscosity`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ brand, molecule }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't look that up — try again.");
  return resp.json();
}

export async function getRequestDetail(token: string, id: number): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load that request — try again.");
  return resp.json();
}

export async function updateRequestStep1(
  token: string,
  id: number,
  body: {
    brand: string;
    market: string;
    strengths: string[];
    viscosity_val: number | null;
    device: string | null;
    differentiated: boolean;
    sku_rows: { strength: string; cartridge: string; fill_ml: number }[];
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save that step — try again.");
  return resp.json();
}

export async function getPlatformOptions(token: string, id: number): Promise<PlatformOptions> {
  const resp = await fetch(`/api/requests/${id}/platform-options`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load platform options — try again.");
  return resp.json();
}

export async function updatePlatformOptions(
  token: string,
  id: number,
  body: {
    exhibit_batch_start: string | null;
    exhibit_batch_end: string | null;
    tentative_approval_months: number | null;
    assembly_machine_qualification: boolean | null;
    assembly_qualification_qty: number | null;
    assembly_qualification_date: string | null;
    platform_design_verification_request: boolean | null;
    sample_request: boolean | null;
    sample_request_qty: number | null;
    sku_batch_sizes: { sku_row_id: number; batch_size_l: number | null }[];
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/platform-options`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save those details — try again.");
  return resp.json();
}

export async function selectOption(token: string, id: number, chosenOption: number): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/select-option`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ chosen_option: chosenOption }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't select that option — try again.");
  return resp.json();
}

export async function updateServices(
  token: string,
  id: number,
  body: {
    selections: { sku_row_id: number; standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }[];
    comment: string;
    urgency: string;
  }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/services`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save your service selections — try again.");
  return resp.json();
}

export async function submitRequest(token: string, id: number): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/submit`, { method: "POST", headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't submit that request — try again.");
  return resp.json();
}

export type Kam = { id: number; name: string; email: string };
export type OrgKamLink = { org_id: number; org_name: string; kam_user_id: number | null; kam_name: string | null };
export type AuditEntry = {
  id: number;
  org_id: number | null;
  org_name: string | null;
  actor_name: string;
  action: string;
  detail: string;
  created_at: string;
};
export type DashboardMetrics = {
  quarterly_target: Record<string, number>;
  new_customers_qtr: Record<string, number>;
  platform_production: Record<string, number>;
  rep_quarterly: Record<string, { region: string; quarters: Record<string, number> }>;
  rep_platform_matrix: Record<string, Record<string, number>>;
  rep_customer_matrix: Record<string, Record<string, number>>;
  live: { requests_by_status: Record<string, number>; total_requests: number };
};

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export async function listKams(token: string): Promise<Kam[]> {
  const resp = await fetch(`/api/kams`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the KAM roster — try again.");
  return resp.json();
}

export async function listOrgKamMap(token: string): Promise<OrgKamLink[]> {
  const resp = await fetch(`/api/org-kam-map`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load organization routing — try again.");
  return resp.json();
}

export async function updateOrgKamMap(token: string, orgId: number, kamUserId: number): Promise<OrgKamLink> {
  const resp = await fetch(`/api/org-kam-map/${orgId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ kam_user_id: kamUserId }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't update that assignment — try again.");
  return resp.json();
}

export async function assignKam(token: string, requestId: number, kamUserId: number): Promise<RequestRow> {
  const resp = await fetch(`/api/requests/${requestId}/assign-kam`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ kam_user_id: kamUserId }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't assign that request — try again.");
  return resp.json();
}

export async function getDashboardMetrics(token: string): Promise<DashboardMetrics> {
  const resp = await fetch(`/api/dashboard/metrics`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the command centre — try again.");
  return resp.json();
}

export async function getAuditLog(token: string): Promise<AuditEntry[]> {
  const resp = await fetch(`/api/dashboard/audit-log`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the audit trail — try again.");
  return resp.json();
}

export type Message = {
  id: number;
  request_id: number;
  channel: "internal" | "customer";
  sender_user_id: number;
  sender_name: string;
  body: string;
  created_at: string;
};

export async function submitKamAssessment(
  token: string,
  id: number,
  body: { kam_cost_usd: number; kam_timeline_months: number; kam_notes?: string }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/kam-assessment`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't save that assessment — try again.");
  return resp.json();
}

export async function bdReview(
  token: string,
  id: number,
  body: { decision: "approve" | "revise"; note?: string }
): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/bd-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't record that review — try again.");
  return resp.json();
}

export async function respondToCustomer(token: string, id: number, message: string): Promise<RequestDetail> {
  const resp = await fetch(`/api/requests/${id}/respond-to-customer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ message }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't send that response — try again.");
  return resp.json();
}

export async function postMessage(
  token: string,
  id: number,
  channel: "internal" | "customer",
  body: string
): Promise<Message> {
  const resp = await fetch(`/api/requests/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ channel, body }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't send that message — try again.");
  return resp.json();
}

export async function getMessages(token: string, id: number): Promise<Message[]> {
  const resp = await fetch(`/api/requests/${id}/messages`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load messages — try again.");
  return resp.json();
}

export async function recordPageview(token: string, sessionId: string, page: string): Promise<void> {
  await fetch(`/api/activity/pageview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ session_id: sessionId, page }),
  }).catch(() => {
    // fire-and-forget — a failed beacon must never block navigation or surface an error
  });
}

export type CustomerVisit = {
  id: number;
  org_id: number;
  org_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  contact_title: string;
  pages_visited: string[];
  started_at: string;
};

export async function listCustomerVisits(token: string): Promise<CustomerVisit[]> {
  const resp = await fetch(`/api/customer-visits`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the customer engagement log — try again.");
  return resp.json();
}

export type Notification = {
  id: number;
  org_id: number;
  message: string;
  link_path: string;
  is_read: boolean;
  created_at: string;
};

export async function listNotifications(token: string): Promise<Notification[]> {
  const resp = await fetch(`/api/notifications`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load notifications — try again.");
  return resp.json();
}

export async function markNotificationRead(token: string, id: number): Promise<Notification> {
  const resp = await fetch(`/api/notifications/${id}/read`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't update that notification — try again.");
  return resp.json();
}

// --- Forecasting -------------------------------------------------------------
// The backend router is mounted at /forecast; this proxy prepends /api, so the
// client URLs below read /api/forecast/... like every other call in this file.

export type ForecastMode = "epidemiology" | "observed_volume";
export type PriceBasis = "per_dosage_unit" | "per_pack" | "per_api_kg";
export type MetricKey = "patients" | "dosage_units" | "packs" | "api_kg" | "revenue";

export type ForecastParameters = {
  sku_row_id?: number | null;
  molecule: string;
  brand?: string | null;
  geography: string;
  indication?: string | null;
  strength?: string | null;
  dosage_form?: string | null;
  forecast_start_year: number;
  launch_year: number;
  forecast_mode: ForecastMode;
  target_population?: number | null;
  population_basis?: "prevalence" | "incidence" | null;
  treatment_basis?: "chronic" | "annual_course" | null;
  reference_units?: number | null;
  reference_year?: number | null;
  annual_growth_rate?: number | null;
  reference_coverage_note?: string | null;
  base_peak_share: number;
  upside_peak_share: number;
  ramp_speed: number;
  inflection_year: number;
  units_per_patient_per_year?: number | null;
  units_per_patient_basis?: string | null;
  units_per_pack?: number | null;
  active_ingredient_mg_per_unit?: number | null;
  company_capture_share?: number | null;
  probability_of_success?: number | null;
  net_price?: string | null;
  price_currency?: string | null;
  price_basis?: PriceBasis | null;
  source_observation_id?: number | null;
  override_reason?: string | null;
  overridden_source_value?: number | null;
};

export type Scenario = {
  addressable_patients: number[] | null;
  patients: number[] | null;
  addressable_dosage_units: number[] | null;
  business_dosage_units: number[] | null;
  business_packs: number[] | null;
  business_api_kg: number[] | null;
  business_revenue: string[] | null;
  risk_adjusted_business_dosage_units: number[] | null;
};

export type ProvenanceClass =
  | "live_cms_api"
  | "archived_cms_publication"
  | "user_supplied_file"
  | "manual_entry";

export type SourceObservation = {
  id: number | null;
  source_kind: "cms_part_d" | "file_import" | "manual_entry";
  source_url: string | null;
  source_identifier: string | null;
  molecule: string | null;
  brand: string | null;
  geography: string;
  coverage: string;
  period_label: string;
  metric: string;
  unit: string;
  value: string | null;
  currency: string | null;
  strength: string | null;
  dosage_form: string | null;
  transformation: string;
  ambiguous_match: boolean;
  retrieved_at: string;
  stale: boolean;
  provenance_class: ProvenanceClass;
  retrieval_url: string | null;
  archive_capture_date: string | null;
  content_sha256: string | null;
};

/** The three CMS source facts, reported and rendered independently. */
export type CmsSourceStatus = {
  dataset_title: string;
  publication_url: string;
  reporting_year: number | null;
  latest_published_year: number;
  file_verification: "verified" | "unrecognised" | "mismatch" | null;
  file_sha256: string | null;
  publication_freshness: "current" | "superseded" | "unknown";
  published_on: string | null;
  last_metadata_check_at: string | null;
  last_metadata_check_status: string | null;
  metadata_check_detail: string | null;
  new_release_detected: boolean;
  freshness_label: string;
  active_release_status: string | null;
  active_release_validated_at: string | null;
  active_release_checks: { name: string; passed: boolean; detail: string }[] | null;
  api_connectivity: "reachable" | "blocked" | "error" | "not_checked";
  api_endpoint: string;
  api_http_status: number | null;
  api_checked_at: string | null;
  akamai_reference: string | null;
  api_detail: string | null;
  support_summary: string | null;
  last_successful_refresh: string | null;
  last_refresh_provenance: ProvenanceClass | null;
  retrieval_url: string | null;
  archive_capture_date: string | null;
  observation_count: number;
};

export type Forecast = {
  deal_id: number;
  request_id: number;
  sku_row_id: number | null;
  revision: number;
  model_version: string;
  forecast_mode: ForecastMode;
  calendar_years: number[];
  base_case: Scenario;
  upside_case: Scenario;
  unit_metadata: {
    patients: string | null;
    dosage_units: string | null;
    packs: string | null;
    api_kg: string | null;
    revenue: string | null;
  };
  assumption_summary: Record<string, unknown>;
  source_references: SourceObservation[];
  updated_at: string;
  warnings: string[];
};

export type ForecastCollection = {
  request_id: number;
  granularity: "request" | "sku" | "none";
  forecasts: Forecast[];
  warnings: string[];
};

/** Why a source returned nothing. These are never conflated in the UI: only
 *  "no_matching_records" says anything about the molecule itself. */
export type SourceStatus =
  | "available"
  | "no_matching_records"
  | "configuration_incomplete"
  | "api_unavailable";

export type SourceSearch = {
  query_echo: Record<string, unknown>;
  results: SourceObservation[];
  available: boolean;
  status: SourceStatus;
  unavailable_reason: string | null;
  truncated: boolean;
  warnings: string[];
};

export async function getForecast(token: string, requestId: number): Promise<ForecastCollection> {
  const resp = await fetch(`/api/forecast/${requestId}`, { headers: authHeaders(token) });
  if (!resp.ok) throw await parseError(resp, "We couldn't load the forecast — try again.");
  return resp.json();
}

export async function upsertForecast(
  token: string,
  requestId: number,
  revision: number,
  parameters: ForecastParameters,
  changeReason?: string
): Promise<ForecastCollection> {
  const resp = await fetch(`/api/forecast/upsert`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({
      request_id: requestId,
      revision,
      parameters,
      change_reason: changeReason ?? null,
    }),
  });
  if (!resp.ok) {
    // A 409 here means someone else saved first — the caller reloads rather than retrying.
    throw await parseError(resp, "We couldn't save those assumptions — try again.");
  }
  return resp.json();
}

export async function searchForecastSources(
  token: string,
  query: { request_id: number; geography: string; molecule?: string; brand?: string; period?: string }
): Promise<SourceSearch> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const resp = await fetch(`/api/forecast/sources/search?${params.toString()}`, {
    headers: authHeaders(token),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't search utilization sources — try again.");
  return resp.json();
}

export async function importForecastSources(
  token: string,
  requestId: number,
  csv: string
): Promise<SourceSearch> {
  const resp = await fetch(`/api/forecast/sources/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ request_id: requestId, format: "csv", payload: csv }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't import that file — try again.");
  return resp.json();
}

/** Ingest the official CMS Part D bulk CSV. Used when the CMS API is unreachable —
 *  the file is the publisher's own artifact and provenance is recorded as its CMS URL. */
export async function ingestCmsPartDFile(
  token: string,
  body: {
    request_id: number;
    payload: string;
    molecule?: string;
    brand?: string;
    data_year?: number;
    retrieval_note?: string;
  }
): Promise<SourceSearch> {
  const resp = await fetch(`/api/forecast/sources/cms-part-d/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't read that CMS file — try again.");
  return resp.json();
}

export async function getCmsSourceStatus(
  token: string,
  requestId: number,
  checkApi = false
): Promise<CmsSourceStatus> {
  const resp = await fetch(
    `/api/forecast/sources/cms-part-d/status?request_id=${requestId}&check_api=${checkApi}`,
    { headers: authHeaders(token) }
  );
  if (!resp.ok) throw await parseError(resp, "We couldn't read the CMS source status — try again.");
  return resp.json();
}
