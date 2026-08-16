"use client";
import { useEffect, useState } from "react";
import { ApiError, RequestRow, listRequests } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";

export default function KamWorkspacePage() {
  const { token, user } = useRoleGuard("Key Account Manager");
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeId, setActiveId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    listRequests(token)
      .then(setRequests)
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load your requests."))
      .finally(() => setLoading(false));
  }, [token]);

  if (!token || !user) return null;

  const orgsCovered = new Set(requests.map((r) => r.org_id)).size;
  const active = requests.find((r) => r.id === activeId) ?? null;

  return (
    <>
      <Header userName={user.name} role={user.role} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <div>
          <h1 className="font-display text-lg font-semibold text-forest-900">Welcome, {user.name}</h1>
          <p className="font-body text-sm text-ink-700/70">You see only the organizations and requests routed to you.</p>
        </div>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Card>
            <p className="font-display text-2xl font-semibold text-forest-900">{requests.length}</p>
            <p className="font-body text-sm text-ink-700/70">Assigned requests</p>
          </Card>
          <Card>
            <p className="font-display text-2xl font-semibold text-forest-900">{orgsCovered}</p>
            <p className="font-body text-sm text-ink-700/70">Organizations covered</p>
          </Card>
        </div>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">My assigned customer requests</h2>
          <Card padding="p-0">
            {!loading && requests.length === 0 ? (
              <EmptyState message="No customer requests assigned to you yet — the BD Manager assigns them from the inbox." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Brand</th>
                    <th className="px-4 py-3 font-medium">Market</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => setActiveId(r.id === activeId ? null : r.id)}
                      className={`cursor-pointer border-b border-ink-700/5 transition-colors last:border-0 hover:bg-sand-50 ${
                        activeId === r.id ? "bg-lime-500/10" : ""
                      }`}
                    >
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{r.org_name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{r.brand}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.market}</td>
                      <td className="px-4 py-3"><StatusChip status={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        {active && (
          <section>
            <h2 className="mb-4 font-display text-base font-semibold text-forest-900">
              {active.org_name} · {active.brand} — details
            </h2>
            <Card>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Market</dt>
                  <dd className="font-body text-sm text-ink-700">{active.market}</dd>
                </div>
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Device</dt>
                  <dd className="font-body text-sm text-ink-700">{active.device ?? "—"}</dd>
                </div>
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Total</dt>
                  <dd className="font-body text-sm text-ink-700">${active.total.toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Status</dt>
                  <dd><StatusChip status={active.status} /></dd>
                </div>
              </dl>
              <p className="mt-4 font-body text-xs text-ink-700/50">
                Full SKU, budget, and deliverable-schedule detail isn't ported yet.
              </p>
            </Card>
          </section>
        )}
      </main>
    </>
  );
}
