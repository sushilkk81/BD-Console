"use client";
import { Fragment, useEffect, useState } from "react";
import {
  ApiError, AuditEntry, Kam, Message, OrgKamLink, RequestRow,
  assignKam, bdReview, getAuditLog, getMessages, listKams, listOrgKamMap, listRequests, updateOrgKamMap,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { SelectField } from "@/components/SelectField";
import { EmptyState } from "@/components/EmptyState";
import { MessageThread } from "@/components/MessageThread";

export default function KamAdminPage() {
  const { token, user } = useRoleGuard("BD Manager");
  const [kams, setKams] = useState<Kam[]>([]);
  const [orgLinks, setOrgLinks] = useState<OrgKamLink[]>([]);
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [assignPick, setAssignPick] = useState<Record<number, string>>({});
  const [reviewNote, setReviewNote] = useState<Record<number, string>>({});
  const [reviewError, setReviewError] = useState("");
  const [threadOpenFor, setThreadOpenFor] = useState<number | null>(null);
  const [thread, setThread] = useState<Message[]>([]);

  function loadAll(t: string) {
    Promise.all([listKams(t), listOrgKamMap(t), listRequests(t), getAuditLog(t)])
      .then(([k, o, r, a]) => {
        setKams(k);
        setOrgLinks(o);
        setRequests(r);
        setAudit(a);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load KAM admin data."))
      .finally(() => setLoading(false));
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
    const req = requests.find((r) => r.id === requestId);
    const pick = assignPick[requestId] ?? (req?.suggested_kam_id ? String(req.suggested_kam_id) : "");
    if (!pick) return;
    try {
      await assignKam(token, requestId, Number(pick));
      loadAll(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't assign that request.");
    }
  }

  async function handleReview(requestId: number, decision: "approve" | "revise") {
    if (!token) return;
    const note = reviewNote[requestId];
    if (decision === "revise" && !note) {
      setReviewError("Add a note explaining what needs revision.");
      return;
    }
    try {
      await bdReview(token, requestId, { decision, note: decision === "revise" ? note : undefined });
      setReviewNote((prev) => ({ ...prev, [requestId]: "" }));
      loadAll(token);
    } catch (err) {
      setReviewError(err instanceof ApiError ? err.message : "We couldn't record that review.");
    }
  }

  async function toggleThread(requestId: number) {
    if (threadOpenFor === requestId) {
      setThreadOpenFor(null);
      return;
    }
    setThreadOpenFor(requestId);
    if (token) getMessages(token, requestId).then(setThread).catch(() => setThread([]));
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
            {loading ? (
              <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
            ) : error ? null : kams.length === 0 ? (
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
            {loading ? (
              <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
            ) : error ? null : orgLinks.length === 0 ? (
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
            {loading ? (
              <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
            ) : error ? null : unassigned.length === 0 ? (
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
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Requests awaiting your review</h2>
          {reviewError && <Banner message={reviewError} onDismiss={() => setReviewError("")} />}
          <Card padding="p-0">
            {loading ? (
              <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
            ) : requests.filter((r) => r.status === "KAM Assessment Submitted").length === 0 ? (
              <EmptyState message="No assessments waiting on your review right now." />
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                    <th className="px-4 py-3 font-medium">Organization</th>
                    <th className="px-4 py-3 font-medium">Brand / market</th>
                    <th className="px-4 py-3 font-medium">KAM cost</th>
                    <th className="px-4 py-3 font-medium">Timeline</th>
                    <th className="px-4 py-3 font-medium">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.filter((r) => r.status === "KAM Assessment Submitted").map((r) => (
                    <Fragment key={r.id}>
                      <tr className="border-b border-ink-700/5 last:border-0">
                        <td className="px-4 py-3 font-body text-sm text-ink-700">{r.org_name}</td>
                        <td className="px-4 py-3 font-body text-sm text-ink-700/70">{r.brand} · {r.market}</td>
                        <td className="px-4 py-3 font-body text-sm text-ink-700">
                          {r.kam_cost_usd != null ? `$${r.kam_cost_usd.toLocaleString()}` : "—"}
                        </td>
                        <td className="px-4 py-3 font-body text-sm text-ink-700/70">
                          {r.kam_timeline_months != null ? `${r.kam_timeline_months} mo` : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col gap-2">
                            <div className="flex gap-2">
                              <button
                                type="button" onClick={() => handleReview(r.id, "approve")}
                                className="rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50"
                              >
                                Approve
                              </button>
                              <button
                                type="button" onClick={() => handleReview(r.id, "revise")}
                                className="rounded-lg border border-orange-500 px-3 py-2 font-body text-sm text-orange-700 hover:bg-sand-50"
                              >
                                Send back
                              </button>
                              <button
                                type="button" onClick={() => toggleThread(r.id)}
                                className="rounded-lg border border-ink-700/15 px-3 py-2 font-body text-sm text-ink-700/70 hover:bg-sand-50"
                              >
                                {threadOpenFor === r.id ? "Hide messages" : "View messages"}
                              </button>
                            </div>
                            <textarea
                              placeholder="Revision note (required to send back)"
                              value={reviewNote[r.id] ?? ""} rows={2}
                              onChange={(e) => setReviewNote((prev) => ({ ...prev, [r.id]: e.target.value }))}
                              className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2 font-body text-sm text-ink-700"
                            />
                          </div>
                        </td>
                      </tr>
                      {threadOpenFor === r.id && (
                        <tr className="border-b border-ink-700/5 last:border-0">
                          <td colSpan={5} className="bg-sand-50 px-4 py-4">
                            <MessageThread messages={thread} emptyLabel="No messages on this request yet." />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Audit trail</h2>
          <Card padding="p-0">
            {loading ? (
              <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
            ) : error ? null : audit.length === 0 ? (
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
