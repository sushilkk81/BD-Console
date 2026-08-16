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

export async function login(name: string, email: string, role?: string) {
  const resp = await fetch(`/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, role }),
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't sign you in — check your name and email and try again.");
  }
  return resp.json();
}

export async function createRequest(
  token: string,
  body: { brand: string; market: string; device?: string }
) {
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

export type Kam = { id: number; name: string; email: string };
export type OrgKamLink = { org_id: number; org_name: string; kam_user_id: number | null; kam_name: string | null };
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
};
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
