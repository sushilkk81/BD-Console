"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, listRequests, ApiError } from "@/lib/api";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { SelectField } from "@/components/SelectField";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRow, MobileSkeletonCard } from "@/components/Skeleton";

type RequestRow = {
  id: number;
  brand: string;
  market: string;
  device: string | null;
  status: string;
  total: number;
};

const MARKETS = [
  { value: "US", label: "US" },
  { value: "EU", label: "EU" },
  { value: "Canada", label: "Canada" },
];

export default function RequestsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | undefined>();
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [highlightId, setHighlightId] = useState<number | null>(null);

  useEffect(() => {
    const t = localStorage.getItem("bdconsole_token");
    if (!t) {
      router.replace("/login");
      return;
    }
    setToken(t);
    const rawUser = localStorage.getItem("bdconsole_user");
    if (rawUser) setUserName(JSON.parse(rawUser).name);
    listRequests(t)
      .then(setRequests)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : "We couldn't load your requests — try again.")
      )
      .finally(() => setLoading(false));
  }, [router]);

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!brand.trim()) errors.brand = "Enter a brand.";
    return errors;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBannerError("");
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      const created = await createRequest(token, { brand, market });
      const updated = await listRequests(token);
      setRequests(updated);
      setBrand("");
      setHighlightId(created.id);
      setTimeout(() => setHighlightId(null), 1500);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors);
      } else {
        setBannerError("We couldn't submit that request — try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) return null;

  return (
    <>
      <Header userName={userName} />
      <main className="mx-auto flex max-w-4xl flex-col gap-8 px-4 py-8 sm:px-6">
        <section>
          <h1 className="mb-4 font-display text-lg font-semibold text-forest-900">New request</h1>
          <Card>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4 sm:flex-row sm:items-end" noValidate>
              <div className="flex-1">
                <TextField label="Brand" name="brand" value={brand} onChange={setBrand} error={fieldErrors.brand} />
              </div>
              <div className="w-full sm:w-40">
                <SelectField label="Market" name="market" value={market} onChange={setMarket} options={MARKETS} />
              </div>
              <Button type="submit" loading={submitting}>
                {submitting ? "Submitting…" : "Submit request"}
              </Button>
            </form>
            {bannerError && (
              <div className="mt-4">
                <Banner message={bannerError} onDismiss={() => setBannerError("")} />
              </div>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-lg font-semibold text-forest-900">Your requests</h2>
          <Card padding="p-0">
            {loadError ? (
              <div className="p-6">
                <Banner message={loadError} onDismiss={() => setLoadError("")} />
              </div>
            ) : !loading && requests.length === 0 ? (
              <EmptyState message="No requests yet — submit your first one above." />
            ) : (
              <>
                <table className="hidden w-full text-left sm:table">
                  <thead>
                    <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                      <th className="px-4 py-3 font-medium">ID</th>
                      <th className="px-4 py-3 font-medium">Brand</th>
                      <th className="px-4 py-3 font-medium">Market</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <>
                        <SkeletonRow />
                        <SkeletonRow />
                        <SkeletonRow />
                      </>
                    ) : (
                      requests.map((r) => (
                        <tr
                          key={r.id}
                          className={`border-b border-ink-700/5 transition-colors last:border-0 ${
                            highlightId === r.id ? "bg-lime-500/10" : ""
                          }`}
                        >
                          <td className="px-4 py-3 font-mono text-sm text-ink-700/70">{r.id}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.brand}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.market}</td>
                          <td className="px-4 py-3">
                            <StatusChip status={r.status} />
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>

                <div className="divide-y divide-ink-700/5 sm:hidden">
                  {loading ? (
                    <>
                      <MobileSkeletonCard />
                      <MobileSkeletonCard />
                      <MobileSkeletonCard />
                    </>
                  ) : (
                    requests.map((r) => (
                      <div
                        key={r.id}
                        className={`flex flex-col gap-1.5 px-4 py-3 transition-colors ${
                          highlightId === r.id ? "bg-lime-500/10" : ""
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm font-medium text-ink-700">{r.brand}</span>
                          <span className="font-mono text-xs text-ink-700/70">#{r.id}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm text-ink-700/70">{r.market}</span>
                          <StatusChip status={r.status} />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </Card>
        </section>
      </main>
    </>
  );
}
