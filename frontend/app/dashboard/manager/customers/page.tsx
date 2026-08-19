"use client";
import { useEffect, useState } from "react";
import { ApiError, CustomerVisit, listCustomerVisits } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { EmptyState } from "@/components/EmptyState";

export default function CustomerActivityPage() {
  const { token, user } = useRoleGuard("BD Manager");
  const [visits, setVisits] = useState<CustomerVisit[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    listCustomerVisits(token)
      .then(setVisits)
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load customer activity."))
      .finally(() => setLoading(false));
  }, [token]);

  if (!token || !user) return null;

  return (
    <>
      <Header userName={user.name} role={user.role} token={token} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <h1 className="font-display text-lg font-semibold text-forest-900">Customer activity</h1>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <Card padding="p-0">
          {loading ? (
            <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
          ) : error ? null : visits.length === 0 ? (
            <EmptyState message="No customer logins recorded yet." />
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Organization</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Access date</th>
                  <th className="px-4 py-3 font-medium">Pages visited</th>
                </tr>
              </thead>
              <tbody>
                {visits.map((v) => (
                  <tr key={v.id} className="border-b border-ink-700/5 last:border-0">
                    <td className="px-4 py-3 font-body text-sm text-ink-700">
                      {v.contact_name}
                      <span className="block font-body text-xs text-ink-700/50">{v.contact_title}</span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-ink-700/70">{v.org_name}</td>
                    <td className="px-4 py-3 font-body text-sm text-ink-700/70">{v.contact_email}</td>
                    <td className="px-4 py-3 font-body text-sm text-ink-700/70">{v.contact_phone}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ink-700/70">
                      {new Date(v.started_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-body text-xs text-ink-700/70">
                      {v.pages_visited.length === 0 ? "—" : v.pages_visited.join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </main>
    </>
  );
}
