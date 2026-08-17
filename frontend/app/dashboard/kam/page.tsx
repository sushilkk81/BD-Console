"use client";
import { useEffect, useState } from "react";
import {
  ApiError, Message, RequestDetail, RequestRow,
  getMessages, getRequestDetail, listRequests, postMessage, respondToCustomer, submitKamAssessment,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";
import { MessageThread } from "@/components/MessageThread";

export default function KamWorkspacePage() {
  const { token, user } = useRoleGuard("Key Account Manager");
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeId, setActiveId] = useState<number | null>(null);
  const [activeDetail, setActiveDetail] = useState<RequestDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [costInput, setCostInput] = useState("");
  const [timelineInput, setTimelineInput] = useState("");
  const [notesInput, setNotesInput] = useState("");
  const [actionError, setActionError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) return;
    listRequests(token)
      .then(setRequests)
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load your requests."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token || activeId == null) {
      setActiveDetail(null);
      setMessages([]);
      return;
    }
    getRequestDetail(token, activeId).then(setActiveDetail).catch(() => setActiveDetail(null));
    getMessages(token, activeId).then(setMessages).catch(() => setMessages([]));
  }, [token, activeId]);

  if (!token || !user) return null;

  const orgsCovered = new Set(requests.map((r) => r.org_id)).size;
  const active = requests.find((r) => r.id === activeId) ?? null;

  async function handleSubmitAssessment() {
    if (!token || !activeId) return;
    const cost = Number(costInput);
    const timeline = Number(timelineInput);
    if (!cost || !timeline) {
      setActionError("Enter a cost and a timeline before submitting the assessment.");
      return;
    }
    setSubmitting(true);
    setActionError("");
    try {
      const updated = await submitKamAssessment(token, activeId, {
        kam_cost_usd: cost, kam_timeline_months: timeline, kam_notes: notesInput || undefined,
      });
      setActiveDetail(updated);
      setRequests((prev) => prev.map((r) => (r.id === updated.id ? { ...r, status: updated.status } : r)));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "We couldn't save that assessment.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRespondToCustomer(message: string) {
    if (!token || !activeId) return;
    const updated = await respondToCustomer(token, activeId, message);
    setActiveDetail(updated);
    setRequests((prev) => prev.map((r) => (r.id === updated.id ? { ...r, status: updated.status } : r)));
  }

  async function handlePostInternal(body: string) {
    if (!token || !activeId) return;
    const msg = await postMessage(token, activeId, "internal", body);
    setMessages((prev) => [...prev, msg]);
  }

  async function handlePostCustomerFollowUp(body: string) {
    if (!token || !activeId) return;
    const msg = await postMessage(token, activeId, "customer", body);
    setMessages((prev) => [...prev, msg]);
    getRequestDetail(token, activeId).then(setActiveDetail).catch(() => {});
  }

  return (
    <>
      <Header userName={user.name} role={user.role} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <div>
          <h1 className="font-display text-lg font-semibold text-forest-900">Welcome, {user.name}</h1>
          <p className="font-body text-sm text-ink-700/70">You see only the organizations and requests routed to you.</p>
        </div>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        {loading ? (
          <p className="font-body text-sm text-ink-700/70">Loading…</p>
        ) : (
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
        )}

        <section>
          <h2 className="mb-4 font-display text-base font-semibold text-forest-900">My assigned customer requests</h2>
          <Card padding="p-0">
            {loading ? (
              <p className="p-6 font-body text-sm text-ink-700/70">Loading…</p>
            ) : error ? null : requests.length === 0 ? (
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
              {actionError && <Banner message={actionError} onDismiss={() => setActionError("")} />}

              {activeDetail && (active.status === `Assigned to ${user.name}` || active.status === "Revision Requested") && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Submit your assessment</h3>
                  {active.status === "Revision Requested" && (
                    <p className="font-body text-xs text-orange-700">
                      The BD Manager sent this back for revision — see the internal notes below.
                    </p>
                  )}
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <input
                      type="number" placeholder="Cost (USD)" value={costInput}
                      onChange={(e) => setCostInput(e.target.value)}
                      className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700 sm:w-40"
                    />
                    <input
                      type="number" placeholder="Timeline (months)" value={timelineInput}
                      onChange={(e) => setTimelineInput(e.target.value)}
                      className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700 sm:w-40"
                    />
                  </div>
                  <textarea
                    placeholder="Notes for the BD Manager" value={notesInput} rows={2}
                    onChange={(e) => setNotesInput(e.target.value)}
                    className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700"
                  />
                  <button
                    type="button" onClick={handleSubmitAssessment} disabled={submitting}
                    className="self-start rounded-lg border border-forest-600 px-3 py-2 font-body text-sm text-forest-600 hover:bg-sand-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Submit assessment
                  </button>
                </div>
              )}

              {activeDetail && active.status === "Approved — Awaiting KAM Response" && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Respond to the customer</h3>
                  <MessageThread
                    messages={[]}
                    emptyLabel="Approved — send your response to the customer."
                    onPost={handleRespondToCustomer}
                    placeholder="Cost, timeline, and any notes for the customer…"
                  />
                </div>
              )}

              {activeDetail && (active.status === "Responded to Customer" || active.status === "Customer Query") && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Customer conversation</h3>
                  <MessageThread
                    messages={messages.filter((m) => m.channel === "customer")}
                    emptyLabel="No messages yet."
                    onPost={handlePostCustomerFollowUp}
                  />
                </div>
              )}

              {activeDetail && (
                <div className="mt-6 flex flex-col gap-3 border-t border-ink-700/10 pt-6">
                  <h3 className="font-display text-sm font-semibold text-forest-900">Internal notes (BD Manager)</h3>
                  <MessageThread
                    messages={messages.filter((m) => m.channel === "internal")}
                    emptyLabel="No internal notes yet."
                    onPost={handlePostInternal}
                  />
                </div>
              )}
            </Card>
          </section>
        )}
      </main>
    </>
  );
}
