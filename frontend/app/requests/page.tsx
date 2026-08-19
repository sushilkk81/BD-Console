"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, listRequests, listReferenceProducts, ApiError, RequestRow } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { MARKETS } from "@/lib/markets";
import { Button } from "@/components/Button";
import { AutocompleteField } from "@/components/AutocompleteField";
import { MultiSelectField } from "@/components/MultiSelectField";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRow, MobileSkeletonCard } from "@/components/Skeleton";

export default function RequestsPage() {
  const { token, user } = useRoleGuard("Customer");
  const router = useRouter();
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [brandOptions, setBrandOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewForm, setShowNewForm] = useState(false);
  const [brand, setBrand] = useState("");
  const [markets, setMarkets] = useState<string[]>(["US"]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [banner, setBanner] = useState("");
  const [loadError, setLoadError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function refreshRequests(t: string) {
    return listRequests(t)
      .then(setRequests)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : "We couldn't load your requests — try again.")
      );
  }

  useEffect(() => {
    if (!token) return;
    refreshRequests(token).finally(() => setLoading(false));
    listReferenceProducts(token)
      .then((products) => setBrandOptions(products.map((p) => p.brand)))
      .catch(() => {
        // a failed suggestions fetch shouldn't block starting a request — brand stays free text
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBannerError("");
    setBanner("");
    const errors: Record<string, string> = {};
    if (!brand.trim()) errors.brand = "Enter a brand.";
    if (markets.length === 0) errors.market = "Select at least one market.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    const results = await Promise.allSettled(markets.map((market) => createRequest(token, { brand, market })));
    const succeeded = results.filter((r) => r.status === "fulfilled") as PromiseFulfilledResult<
      Awaited<ReturnType<typeof createRequest>>
    >[];
    const failedMarkets = markets.filter((_, i) => results[i].status === "rejected");

    await refreshRequests(token);

    if (failedMarkets.length === 0) {
      setShowNewForm(false);
      setBrand("");
      setMarkets(["US"]);
      if (succeeded.length === 1) {
        router.push(`/requests/${succeeded[0].value.id}`);
        return;
      }
      setBanner(`Created ${succeeded.length} draft requests — one per selected market.`);
    } else {
      setBannerError(
        succeeded.length > 0
          ? `Started requests for ${succeeded.length} market(s), but couldn't start: ${failedMarkets.join(", ")} — try again for those.`
          : `We couldn't start that request — try again.`
      );
    }
    setSubmitting(false);
  }

  if (!token) return null;

  return (
    <>
      <Header userName={user?.name} role={user?.role} token={token ?? undefined} />
      <main className="mx-auto flex max-w-4xl flex-col gap-8 px-4 py-8 sm:px-6">
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h1 className="font-display text-lg font-semibold text-forest-900">Your requests</h1>
            {!showNewForm && <Button onClick={() => setShowNewForm(true)}>+ New request</Button>}
          </div>

          {banner && (
            <div className="mb-4">
              <Banner variant="success" message={banner} onDismiss={() => setBanner("")} />
            </div>
          )}

          {showNewForm && (
            <Card className="mb-6">
              <form onSubmit={handleCreate} className="flex flex-col gap-4" noValidate>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
                  <div className="flex-1">
                    <AutocompleteField
                      label="Brand"
                      name="brand"
                      value={brand}
                      onChange={setBrand}
                      options={brandOptions}
                      error={fieldErrors.brand}
                    />
                  </div>
                  <Button type="submit" loading={submitting} className="sm:self-start">
                    {submitting
                      ? "Starting…"
                      : markets.length > 1
                        ? `Start ${markets.length} requests`
                        : "Start request"}
                  </Button>
                </div>
                <MultiSelectField
                  label="Markets"
                  name="market"
                  values={markets}
                  onChange={setMarkets}
                  options={MARKETS}
                  error={fieldErrors.market}
                />
              </form>
              {bannerError && (
                <div className="mt-4">
                  <Banner message={bannerError} onDismiss={() => setBannerError("")} />
                </div>
              )}
            </Card>
          )}

          <Card padding="p-0">
            {loadError ? (
              <div className="p-6">
                <Banner message={loadError} onDismiss={() => setLoadError("")} />
              </div>
            ) : !loading && requests.length === 0 ? (
              <EmptyState message="No requests yet — start your first one above." />
            ) : (
              <>
                <table className="hidden w-full text-left sm:table">
                  <thead>
                    <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                      <th className="px-4 py-3 font-medium">ID</th>
                      <th className="px-4 py-3 font-medium">Brand</th>
                      <th className="px-4 py-3 font-medium">Market</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium" />
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
                        <tr key={r.id} className="border-b border-ink-700/5 last:border-0">
                          <td className="px-4 py-3 font-mono text-sm text-ink-700/70">{r.id}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.brand}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.market}</td>
                          <td className="px-4 py-3">
                            <StatusChip status={r.status} />
                          </td>
                          <td className="px-4 py-3 text-right">
                            <Button variant="secondary" onClick={() => router.push(`/requests/${r.id}`)}>
                              {r.status === "Draft" ? "Continue" : "View"}
                            </Button>
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
                      <button
                        key={r.id}
                        onClick={() => router.push(`/requests/${r.id}`)}
                        className="flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm font-medium text-ink-700">{r.brand}</span>
                          <span className="font-mono text-xs text-ink-700/70">#{r.id}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm text-ink-700/70">{r.market}</span>
                          <StatusChip status={r.status} />
                        </div>
                      </button>
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
