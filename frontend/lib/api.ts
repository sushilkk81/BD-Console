export async function login(name: string, email: string, role?: string) {
  const resp = await fetch(`/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, role }),
  });
  if (!resp.ok) throw new Error(`Login failed: ${resp.status}`);
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
  if (!resp.ok) throw new Error(`Create request failed: ${resp.status}`);
  return resp.json();
}

export async function listRequests(token: string) {
  const resp = await fetch(`/api/requests`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`List requests failed: ${resp.status}`);
  return resp.json();
}
