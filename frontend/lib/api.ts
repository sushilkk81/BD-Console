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

export async function listRequests(token: string) {
  const resp = await fetch(`/api/requests`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't load your requests — try again.");
  }
  return resp.json();
}
