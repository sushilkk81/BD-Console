"use client";
import { useEffect, useState } from "react";
import {
  ApiError, AuditEntry, Kam, OrgKamLink, RequestRow,
  assignKam, getAuditLog, listKams, listOrgKamMap, listRequests, updateOrgKamMap,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { SelectField } from "@/components/SelectField";
import { EmptyState } from "@/components/EmptyState";

export default function KamAdminPage() {
  const { token, user } = useRoleGuard("BD Manager");
  const [kams, setKams] = useState<Kam[]>([]);
  const [orgLinks, setOrgLinks] = useState<OrgKamLink[]>([]);
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");
  const [assignPick, setAssignPick] = useState<Record<number, string>>({});

  function loadAll(t: string) {
    Promise.all([listKams(t), listOrgKamMap(t), listRequests(t), getAuditLog(t)])
      .then(([k, o, r, a]) => {
        setKams(k);
        setOrgLinks(o);
        setRequests(r);
        setAudit(a);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load KAM admin data."));
  }

  useEffect(() => {
    if (token) loadAll(token);
  }, [token]);

  async function handleOrgKamChange(orgId: number, kamUserId: string) {
    if (!token || !kamUserId) return;
    try {
      await updateOrgKamMap(token, orgId, Number(kamUserId));
      loadAll(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't update that assignment.");
    }
  }

  async function handleAssign(requestId: number) {
    if (!token) return;
    const pick = assignPick[requestId];
    if (!pick) return;
    try {
      await assignKam(token, requestId, Number(pick));
      loadAll(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't assign that request.");
    }
  }

  if (!token || !user) return null;

  const kamOptions = kams.map((k) => ({ value: String(k.id), label: k.name }));
  const unassigned = requests.filter((r) => !r.assigned_kam_id);

  return (
    <>
      <Header userName={user.name} role={user.role} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <h1 className="font-display text-lg font-semibold text-forest-900">Key Account Managers & query routing</h1>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">KAM roster</h2>
          <Card padding="p-0">
            {kams.length === 0 ? (
              <EmptyState message="No Key Account Managers have logged in yet." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">KAM</th>
                    <th className="px-4 py-3 font-medium">Login</th>
                  </tr>
                </thead>
                <tbody>
                  {kams.map((k) => (
                    <tr key={k.id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{k.name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{k.email}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Organization → KAM assignment</h2>
          <Card padding="p-0">
            {orgLinks.length === 0 ? (
              <EmptyState message="No customer organizations yet." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Assigned KAM</th>
                  </tr>
                </thead>
                <tbody>
                  {orgLinks.map((link) => (
                    <tr key={link.org_id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{link.org_name}</td>
                      <td className="px-4 py-3">
                        <SelectField
                          label="Assigned KAM"
                          name={`org-${link.org_id}`}
                          value={link.kam_user_id ? String(link.kam_user_id) : ""}
                          onChange={(v) => handleOrgKamChange(link.org_id, v)}
                          options={kamOptions}
                          placeholder="Unassigned"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Incoming customer requests — assign a KAM</h2>
          <Card padding="p-0">
            {unassigned.length === 0 ? (
              <EmptyState message="No unassigned requests right now." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Brand / market</th>
                    <th className="px-4 py-3 font-medium">Suggested</th>
                    <th className="px-4 py-3 font-medium">Assign</th>
                  </tr>
                </thead>
                <tbody>
                  {unassigned.map((r) => (
                    <tr key={r.id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{r.org_name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.brand} · {r.market}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.suggested_kam_name ?? "—"}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <SelectField
                            label="Assign to"
                            name={`assign-${r.id}`}
                            value={assignPick[r.id] ?? (r.suggested_kam_id ? String(r.suggested_kam_id) : "")}
                            onChange={(v) => setAssignPick((prev) => ({ ...prev, [r.id]: v }))}
                            options={kamOptions}
                            placeholder="Select…"
                          />
                          <button
                            type="button"
                            onClick={() => handleAssign(r.id)}
                            className="rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50"
                          >
                            Assign
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Audit trail</h2>
          <Card padding="p-0">
            {audit.length === 0 ? (
              <EmptyState message="No activity yet — link an organization or assign a KAM to populate the trail." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">When</th>
                    <th className="px-4 py-3 font-medium">Actor</th>
                    <th className="px-4 py-3 font-medium">Action</th>
                    <th className="px-4 py-3 font-medium">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-4 py-3 font-mono text-xs text-ink-700/70">{new Date(a.created_at).toLocaleString()}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700">{a.actor_name}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{a.action}</td>
                      <td className="px-4 py-3 font-body text-sm text-ink-700/70">{a.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>
      </main>
    </>
  );
}
