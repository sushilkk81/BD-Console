"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import type { Dispatch, SetStateAction } from "react";
import {
  ApiError,
  Message,
  PlatformOptions,
  ReferenceProduct,
  RequestDetail,
  getMessages,
  getPlatformOptions,
  getRequestDetail,
  listReferenceProducts,
  lookupStrengths,
  lookupViscosity,
  postMessage,
  selectOption,
  submitRequest,
  updateRequestStep1,
  updateServices,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { MARKETS } from "@/lib/markets";
import { Header } from "@/components/Header";
import { Card } from "@/components/Card";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/SelectField";
import { TextField } from "@/components/TextField";
import { MessageThread } from "@/components/MessageThread";

const CART_SIZES = ["1.5 mL", "3 mL", "1 mL PFS", "3 mL PFS", "1 mL Bespoke"];
const RESPONDED_STATUSES = ["Responded to Customer", "Customer Query"];
const STEPS = [
  { key: "form", label: "1 · Request" },
  { key: "options", label: "2 · Platform options" },
  { key: "cost", label: "3 · Cost & deal" },
] as const;
type StepKey = (typeof STEPS)[number]["key"];

type SkuDraft = { strength: string; cartridge: string; fill_ml: number };

export default function RequestWizardPage() {
  const { token, user } = useRoleGuard("Customer");
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const requestId = Number(params.id);

  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [refProducts, setRefProducts] = useState<ReferenceProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [step, setStep] = useState<StepKey>("form");

  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");
  const [strengths, setStrengths] = useState<string[]>([]);
  const [skuRows, setSkuRows] = useState<SkuDraft[]>([]);
  const [viscosityVal, setViscosityVal] = useState<number | "">("");
  const [differentiated, setDifferentiated] = useState(false);
  const [device, setDevice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [strengthLookupLoading, setStrengthLookupLoading] = useState(false);
  const [strengthLookupNotFound, setStrengthLookupNotFound] = useState(false);
  const [viscosityLookup, setViscosityLookup] = useState<{ visc_val: number; citation: string | null } | null>(null);
  const [viscosityLookupLoading, setViscosityLookupLoading] = useState(false);
  const [viscosityLookupNotFound, setViscosityLookupNotFound] = useState(false);
  const [lookedUpBrandMarket, setLookedUpBrandMarket] = useState<string | null>(null);
  const [liveLookupPresentations, setLiveLookupPresentations] = useState<
    Record<string, { cartridge: string; fill_ml: number }>
  >({});

  const [options, setOptions] = useState<PlatformOptions | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState("");
  const [selecting, setSelecting] = useState(false);

  const [serviceRows, setServiceRows] = useState<
    Record<number, { standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }>
  >({});
  const [comment, setComment] = useState("");
  const [urgency, setUrgency] = useState("Level 1 · call back today");
  const [savingServices, setSavingServices] = useState(false);
  const [servicesError, setServicesError] = useState("");
  const [submittingRequest, setSubmittingRequest] = useState(false);
  const [submitBanner, setSubmitBanner] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [queryError, setQueryError] = useState("");
  const [postingQuery, setPostingQuery] = useState(false);

  useEffect(() => {
    if (!token || Number.isNaN(requestId)) return;
    Promise.all([getRequestDetail(token, requestId), listReferenceProducts(token)])
      .then(([req, products]) => {
        setDetail(req);
        setRefProducts(products);
        setBrand(req.brand);
        setMarket(req.market);
        setStrengths(req.sku_rows.map((r) => r.strength));
        setSkuRows(req.sku_rows.map((r) => ({ strength: r.strength, cartridge: r.cartridge, fill_ml: r.fill_ml })));
        setViscosityVal(req.viscosity_val ?? "");
        setDifferentiated(req.differentiated);
        setDevice(req.device);
        if (req.chosen_option != null && req.status === "Draft") setStep("options");
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setLoadError(err instanceof ApiError ? err.message : "We couldn't load this request — try again.");
        }
      })
      .finally(() => setLoading(false));
  }, [token, requestId]);

  useEffect(() => {
    if (!token || !detail || !RESPONDED_STATUSES.includes(detail.status)) {
      setMessages([]);
      return;
    }
    getMessages(token, requestId).then(setMessages).catch(() => setMessages([]));
  }, [token, detail, requestId]);

  const currentRef = refProducts.find((p) => p.brand === brand) ?? null;
  const isDraft = detail?.status === "Draft";

  function reconcileRowsForStrengths(next: string[]) {
    setStrengths(next);
    setSkuRows((prev) => {
      const existing = new Map(prev.map((r) => [r.strength, r]));
      return next.map((s) => {
        if (existing.has(s)) return existing.get(s)!;
        const live = liveLookupPresentations[s];
        if (live) return { strength: s, cartridge: live.cartridge, fill_ml: live.fill_ml };
        const cart = currentRef?.cartridge ?? "3 mL";
        return { strength: s, cartridge: cart, fill_ml: 1.5 };
      });
    });
  }

  function resetForRefChange(ref: ReferenceProduct | undefined) {
    reconcileRowsForStrengths(ref ? [...ref.strengths] : []);
    setDevice(ref?.device ?? null);
    setDifferentiated(false);
    setViscosityVal("");
    setStrengthLookupNotFound(false);
    setViscosityLookup(null);
    setViscosityLookupNotFound(false);
    setLookedUpBrandMarket(null);
    setLiveLookupPresentations({});
  }

  function handleBrandChange(nextBrand: string) {
    setBrand(nextBrand);
    const ref = refProducts.find((p) => p.brand === nextBrand);
    resetForRefChange(ref);
  }

  function handleMarketChange(nextMarket: string) {
    setMarket(nextMarket);
    resetForRefChange(currentRef ?? undefined);
  }

  async function handleLiveStrengthLookup() {
    if (!token || !brand || !market) return;
    setStrengthLookupLoading(true);
    setStrengthLookupNotFound(false);
    try {
      const result = await lookupStrengths(token, brand, market);
      if (result.found) {
        setLookedUpBrandMarket(`${brand}|${market}`);
        setLiveLookupPresentations((prev) => {
          const next = { ...prev };
          for (const s of result.strengths) {
            next[s.strength] = { cartridge: s.cartridge, fill_ml: s.fill_ml };
          }
          return next;
        });
        setRefProducts((prev) => {
          const existing = prev.find((p) => p.brand === result.brand);
          const merged: ReferenceProduct = {
            brand: result.brand,
            molecule: result.molecule ?? existing?.molecule ?? "",
            device: result.device ?? existing?.device ?? "",
            strengths: result.strengths.map((s) => s.strength),
            visc_val: existing?.visc_val ?? 0,
            visc_ref: existing?.visc_ref ?? "",
            cartridge: result.strengths[0]?.cartridge ?? existing?.cartridge ?? "3 mL",
          };
          return existing ? prev.map((p) => (p.brand === result.brand ? merged : p)) : [...prev, merged];
        });
      } else {
        setStrengthLookupNotFound(true);
      }
    } catch (err) {
      console.error(err);
      setStrengthLookupNotFound(true);
    } finally {
      setStrengthLookupLoading(false);
    }
  }

  async function handleLiveViscosityLookup() {
    if (!token || !brand) return;
    setViscosityLookupLoading(true);
    setViscosityLookupNotFound(false);
    setViscosityLookup(null);
    try {
      const result = await lookupViscosity(token, brand, currentRef?.molecule);
      if (result.found && result.visc_val != null) {
        setViscosityLookup({ visc_val: result.visc_val, citation: result.citation });
      } else {
        setViscosityLookupNotFound(true);
      }
    } catch (err) {
      console.error(err);
      setViscosityLookupNotFound(true);
    } finally {
      setViscosityLookupLoading(false);
    }
  }

  async function saveStep1(): Promise<boolean> {
    if (!token) return false;
    setSaveError("");
    setSaving(true);
    try {
      const updated = await updateRequestStep1(token, requestId, {
        brand,
        market,
        strengths,
        viscosity_val: viscosityVal === "" ? null : Number(viscosityVal),
        device,
        differentiated,
        sku_rows: skuRows,
      });
      setDetail(updated);
      return true;
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "We couldn't save this step — try again.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleContinueToOptions() {
    if (await saveStep1()) setStep("options");
  }

  useEffect(() => {
    if (step !== "options" || !token || !detail) return;
    setOptionsLoading(true);
    setOptionsError("");
    getPlatformOptions(token, requestId)
      .then(setOptions)
      .catch((err) => setOptionsError(err instanceof ApiError ? err.message : "We couldn't load platform options — try again."))
      .finally(() => setOptionsLoading(false));
  }, [step, token, detail, requestId]);

  async function handleSelectOption(n: 1 | 2 | 3) {
    if (!token) return;
    setSelecting(true);
    try {
      const updated = await selectOption(token, requestId, n);
      setDetail(updated);
      setStep("cost");
    } catch (err) {
      setOptionsError(err instanceof ApiError ? err.message : "We couldn't select that option — try again.");
    } finally {
      setSelecting(false);
    }
  }

  useEffect(() => {
    if (!detail) return;
    const bySkuId = new Map(detail.service_selections.map((s) => [s.sku_row_id, s]));
    const seeded: typeof serviceRows = {};
    for (const row of detail.sku_rows) {
      const existing = bySkuId.get(row.id);
      seeded[row.id] = existing
        ? { standard_dv: existing.standard_dv, threshold: existing.threshold, ifu: existing.ifu, human_factor: existing.human_factor }
        : { standard_dv: true, threshold: false, ifu: false, human_factor: false };
    }
    setServiceRows(seeded);
    setComment(detail.comment ?? "");
    setUrgency(detail.urgency ?? "Level 1 · call back today");
  }, [detail]);

  const PRICES = { standard_dv_lead: { minor: 200, moderate: 250, major: 350 }, add_dv: 50, threshold: 2110, ifu: 1110, human_factor: 400000 };

  function estimateTotal(): number {
    if (!detail) return 0;
    const sev = (detail.severity as "minor" | "moderate" | "major" | null) ?? "minor";
    const rows = Object.values(serviceRows);
    const nDv = rows.filter((r) => r.standard_dv).length;
    const lead = PRICES.standard_dv_lead[sev];
    const dv = nDv ? (lead + PRICES.add_dv * Math.max(0, nDv - 1)) * 1000 : 0;
    const thr = rows.filter((r) => r.threshold).length * PRICES.threshold;
    const ifu = rows.filter((r) => r.ifu).length * PRICES.ifu;
    const hf = rows.filter((r) => r.human_factor).length * PRICES.human_factor;
    return dv + thr + ifu + hf;
  }

  async function handleSaveServices(): Promise<boolean> {
    if (!token || !detail) return false;
    setServicesError("");
    setSavingServices(true);
    try {
      const updated = await updateServices(token, requestId, {
        selections: detail.sku_rows.map((row) => ({ sku_row_id: row.id, ...serviceRows[row.id] })),
        comment,
        urgency,
      });
      setDetail(updated);
      return true;
    } catch (err) {
      setServicesError(err instanceof ApiError ? err.message : "We couldn't save your service selections — try again.");
      return false;
    } finally {
      setSavingServices(false);
    }
  }

  async function handleSubmitRequest() {
    if (!(await handleSaveServices())) return;
    if (!token) return;
    setSubmittingRequest(true);
    try {
      await submitRequest(token, requestId);
      setSubmitBanner("Submitted to the Shaily BD desk. The BD Manager will assign a Key Account Manager.");
      setTimeout(() => router.push("/requests"), 1600);
    } catch (err) {
      setServicesError(err instanceof ApiError ? err.message : "We couldn't submit that request — try again.");
    } finally {
      setSubmittingRequest(false);
    }
  }

  async function handlePostQuery(body: string) {
    if (!token) return;
    setQueryError("");
    setPostingQuery(true);
    try {
      const msg = await postMessage(token, requestId, "customer", body);
      setMessages((prev) => [...prev, msg]);
      const updated = await getRequestDetail(token, requestId);
      setDetail(updated);
    } catch (err) {
      setQueryError(err instanceof ApiError ? err.message : "We couldn't send that message — try again.");
    } finally {
      setPostingQuery(false);
    }
  }

  if (!token) return null;
  if (notFound) {
    return (
      <>
        <Header userName={user?.name} role={user?.role} token={token ?? undefined} />
        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
          <Banner message="That request doesn't exist or isn't yours." onDismiss={() => router.push("/requests")} />
        </main>
      </>
    );
  }

  return (
    <>
      <Header userName={user?.name} role={user?.role} token={token ?? undefined} />
      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6">
        <nav className="flex gap-2 rounded-full bg-sand-50 p-1" aria-label="Wizard steps">
          {STEPS.map((s) => (
            <button
              key={s.key}
              onClick={() => setStep(s.key)}
              className={`flex-1 rounded-full px-3 py-2 font-body text-sm transition-colors ${
                step === s.key ? "bg-white font-medium text-forest-900 shadow-sm" : "text-ink-700/60"
              }`}
            >
              {s.label}
            </button>
          ))}
        </nav>

        {loading ? (
          <div className="h-64 w-full animate-pulse rounded-2xl bg-sand-50" />
        ) : loadError ? (
          <Banner message={loadError} onDismiss={() => setLoadError("")} />
        ) : (
          <>
            {!isDraft && (
              <Banner
                message="This request has been submitted — it's read-only. Cost editing and negotiation are handled by your assigned Shaily KAM."
                onDismiss={() => {}}
              />
            )}

            {detail && RESPONDED_STATUSES.includes(detail.status) && (
              <Card className="flex flex-col gap-4">
                <div>
                  <h2 className="font-display text-base font-semibold text-forest-900">Shaily's response</h2>
                  {(detail.kam_cost_usd != null || detail.kam_timeline_months != null) && (
                    <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
                      <div>
                        <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Assessed cost</dt>
                        <dd className="font-body text-sm text-ink-700">
                          {detail.kam_cost_usd != null ? `$${detail.kam_cost_usd.toLocaleString()}` : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="font-body text-xs uppercase tracking-wide text-ink-700/70">Timeline</dt>
                        <dd className="font-body text-sm text-ink-700">
                          {detail.kam_timeline_months != null ? `${detail.kam_timeline_months} months` : "—"}
                        </dd>
                      </div>
                    </dl>
                  )}
                </div>
                {queryError && <Banner message={queryError} onDismiss={() => setQueryError("")} />}
                <MessageThread
                  messages={messages}
                  emptyLabel="No messages yet."
                  onPost={handlePostQuery}
                  posting={postingQuery}
                  placeholder="Ask a question about this response…"
                />
              </Card>
            )}

            {step === "form" && (
              <Card className="flex flex-col gap-6">
                <div>
                  <h2 className="mb-4 font-display text-base font-semibold text-forest-900">Reference product</h2>
                  <div className="flex flex-col gap-4 sm:flex-row">
                    <div className="flex-1">
                      <SelectField
                        label="Reference product brand"
                        name="brand"
                        value={brand}
                        onChange={isDraft ? handleBrandChange : () => {}}
                        options={refProducts.map((p) => ({ value: p.brand, label: p.brand }))}
                      />
                    </div>
                    <div className="w-full sm:w-40">
                      <SelectField
                        label="Target market"
                        name="market"
                        value={market}
                        onChange={isDraft ? handleMarketChange : () => {}}
                        options={MARKETS}
                      />
                    </div>
                  </div>
                  {isDraft && brand && market && lookedUpBrandMarket !== `${brand}|${market}` && (
                    <div className="mt-2">
                      <Button
                        type="button"
                        variant="secondary"
                        loading={strengthLookupLoading}
                        onClick={handleLiveStrengthLookup}
                      >
                        {strengthLookupLoading
                          ? "Looking up…"
                          : currentRef
                          ? "🔍 Refresh for this market"
                          : "🔍 Look up live"}
                      </Button>
                      {strengthLookupNotFound && (
                        <p className="mt-2 font-body text-xs text-ink-700/70">
                          No data found for this brand/market — enter details manually.
                        </p>
                      )}
                    </div>
                  )}
                  {currentRef && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      ✓ Recognised — <b>{currentRef.molecule}</b> · device auto-set to <b>{currentRef.device}</b>.
                    </p>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">Strength(s) / SKUs</h2>
                  <div className="flex flex-wrap gap-2">
                    {(currentRef?.strengths ?? []).map((s) => (
                      <label
                        key={s}
                        className={`cursor-pointer rounded-full border px-3 py-1.5 font-body text-sm ${
                          strengths.includes(s)
                            ? "border-forest-600 bg-forest-600/10 text-forest-900"
                            : "border-ink-700/15 text-ink-700/70"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="sr-only"
                          disabled={!isDraft}
                          checked={strengths.includes(s)}
                          onChange={(e) => {
                            const next = e.target.checked ? [...strengths, s] : strengths.filter((x) => x !== s);
                            reconcileRowsForStrengths(next);
                          }}
                        />
                        {s}
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">Product viscosity</h2>
                  <div className="flex items-end gap-3">
                    <div className="w-40">
                      <TextField
                        label="Viscosity (cP)"
                        name="viscosity"
                        type="number"
                        value={viscosityVal === "" ? "" : String(viscosityVal)}
                        onChange={isDraft ? (v) => setViscosityVal(v === "" ? "" : Number(v)) : () => {}}
                      />
                    </div>
                    {isDraft && brand && (
                      <Button
                        type="button"
                        variant="secondary"
                        loading={viscosityLookupLoading}
                        onClick={handleLiveViscosityLookup}
                      >
                        {viscosityLookupLoading ? "Searching…" : "＋ Need assistance"}
                      </Button>
                    )}
                  </div>
                  {viscosityLookup && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      Literature suggests <b>{viscosityLookup.visc_val} cP</b>.{" "}
                      <button
                        type="button"
                        className="font-medium text-forest-600 underline-offset-2 hover:underline"
                        onClick={() => setViscosityVal(viscosityLookup.visc_val)}
                      >
                        Use this value
                      </button>
                      {viscosityLookup.citation && (
                        <>
                          {" "}
                          — <i>*{viscosityLookup.citation}</i>
                        </>
                      )}
                    </p>
                  )}
                  {viscosityLookupNotFound && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      No literature value found — enter manually.
                    </p>
                  )}
                  {!viscosityLookup && currentRef?.visc_ref && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">📄 Literature reference: {currentRef.visc_ref}</p>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">Device type</h2>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={differentiated}
                    disabled={!isDraft}
                    onClick={() => isDraft && setDifferentiated(!differentiated)}
                    className={`rounded-full border px-4 py-2 font-body text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      differentiated
                        ? "border-forest-600 bg-forest-600/10 text-forest-900"
                        : "border-ink-700/15 text-ink-700/70 hover:border-forest-600/40"
                    }`}
                  >
                    {differentiated ? "✓ " : ""}Differentiated formulation (override auto-selected device)
                  </button>
                  {differentiated ? (
                    <div className="mt-2 w-56">
                      <SelectField
                        label="Device type"
                        name="device"
                        value={device ?? ""}
                        onChange={isDraft ? (v) => setDevice(v) : () => {}}
                        options={[
                          { value: "Pen Injector", label: "Pen Injector" },
                          { value: "Auto-Injector", label: "Auto-Injector" },
                          { value: "On-Body", label: "On-Body" },
                        ]}
                      />
                    </div>
                  ) : (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      Device: {currentRef?.device ?? "—"} · auto from reference product
                    </p>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">
                    Cartridge & fill — one row per SKU
                  </h2>
                  {skuRows.length === 0 ? (
                    <p className="font-body text-sm text-ink-700/70">Select at least one strength above.</p>
                  ) : (
                    <table className="w-full text-left">
                      <thead>
                        <tr className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                          <th className="py-1.5">Strength</th>
                          <th className="py-1.5">Cartridge</th>
                          <th className="py-1.5">Fill (mL)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {skuRows.map((row, i) => (
                          <tr key={row.strength} className="border-t border-ink-700/5">
                            <td className="py-1.5 font-body text-sm text-ink-700">{row.strength}</td>
                            <td className="py-1.5">
                              <select
                                disabled={!isDraft}
                                value={row.cartridge}
                                onChange={(e) => {
                                  const next = [...skuRows];
                                  next[i] = { ...row, cartridge: e.target.value };
                                  setSkuRows(next);
                                }}
                                className="rounded-lg border border-ink-700/15 px-2 py-1 font-body text-sm"
                              >
                                {CART_SIZES.map((c) => (
                                  <option key={c} value={c}>
                                    {c}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="py-1.5">
                              <input
                                type="number"
                                step={0.1}
                                min={0.1}
                                disabled={!isDraft}
                                value={row.fill_ml}
                                onChange={(e) => {
                                  const next = [...skuRows];
                                  next[i] = { ...row, fill_ml: Number(e.target.value) };
                                  setSkuRows(next);
                                }}
                                className="w-24 rounded-lg border border-ink-700/15 px-2 py-1 font-body text-sm"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {saveError && <Banner message={saveError} onDismiss={() => setSaveError("")} />}

                {isDraft && (
                  <div>
                    <Button
                      onClick={handleContinueToOptions}
                      loading={saving}
                      disabled={strengths.length === 0 || skuRows.length === 0}
                    >
                      {saving ? "Saving…" : "Find platform options →"}
                    </Button>
                  </div>
                )}
              </Card>
            )}

            {step === "options" && detail && (
              <StepOptions
                options={options}
                loading={optionsLoading}
                error={optionsError}
                onDismissError={() => setOptionsError("")}
                chosenOption={detail.chosen_option}
                isDraft={isDraft}
                selecting={selecting}
                onSelect={handleSelectOption}
              />
            )}
            {step === "cost" && detail && (
              <StepCost
                detail={detail}
                serviceRows={serviceRows}
                setServiceRows={setServiceRows}
                comment={comment}
                setComment={setComment}
                urgency={urgency}
                setUrgency={setUrgency}
                isDraft={isDraft}
                estimatedTotal={estimateTotal()}
                error={servicesError}
                onDismissError={() => setServicesError("")}
                saving={savingServices}
                submitting={submittingRequest}
                submitBanner={submitBanner}
                onSubmit={handleSubmitRequest}
              />
            )}
          </>
        )}
      </main>
    </>
  );
}

function StepOptions({
  options,
  loading,
  error,
  onDismissError,
  chosenOption,
  isDraft,
  selecting,
  onSelect,
}: {
  options: PlatformOptions | null;
  loading: boolean;
  error: string;
  onDismissError: () => void;
  chosenOption: number | null;
  isDraft: boolean;
  selecting: boolean;
  onSelect: (n: 1 | 2 | 3) => void;
}) {
  if (loading) return <Card>Loading platform options…</Card>;
  if (error) return <Banner message={error} onDismiss={onDismissError} />;
  if (!options) return null;

  return (
    <div className="flex flex-col gap-6">
      <p className="font-body text-sm text-ink-700/70">
        Each SKU is matched to cartridge-compatible Shaily platforms and ranked by device-mechanism closeness to the
        reference product. Three option sets are proposed — pick the one to take forward.
      </p>
      {([1, 2, 3] as const).map((n) => {
        const rows = options.options[String(n) as "1" | "2" | "3"];
        const selected = chosenOption === n;
        return (
          <Card key={n} className={selected ? "border-forest-600" : ""}>
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded-full bg-sand-50 px-3 py-1 font-body text-xs font-medium text-ink-700">
                Option {n}
              </span>
              {selected && <span className="font-body text-xs font-medium text-forest-600">✓ selected</span>}
            </div>
            <table className="w-full text-left">
              <thead>
                <tr className="font-body text-xs uppercase tracking-wide text-ink-700/70">
                  <th className="py-1.5">SKU</th>
                  <th className="py-1.5">Platform</th>
                  <th className="py-1.5">Type</th>
                  <th className="py-1.5">Mechanism match</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.sku} className="border-t border-ink-700/5">
                    <td className="py-1.5 font-body text-sm text-ink-700">{row.sku}</td>
                    <td className="py-1.5 font-body text-sm text-ink-700">{row.platform ?? "—"}</td>
                    <td className="py-1.5 font-body text-sm text-ink-700">
                      {row.cls ?? "—"}
                      {row.sub ? ` · ${row.sub}` : ""}
                    </td>
                    <td className="py-1.5 font-body text-sm text-ink-700">
                      {row.band === "n/a" ? "—" : `${row.band} · ${row.pct}%`}
                      {row.fallback ? " ⚠ fallback" : ""}
                      {row.visc_limited ? " · visc-limited" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {isDraft && (
              <div className="mt-3">
                <Button variant={selected ? "primary" : "secondary"} loading={selecting} onClick={() => onSelect(n)}>
                  Select Option {n} →
                </Button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
function StepCost({
  detail,
  serviceRows,
  setServiceRows,
  comment,
  setComment,
  urgency,
  setUrgency,
  isDraft,
  estimatedTotal,
  error,
  onDismissError,
  saving,
  submitting,
  submitBanner,
  onSubmit,
}: {
  detail: RequestDetail;
  serviceRows: Record<number, { standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }>;
  setServiceRows: Dispatch<
    SetStateAction<Record<number, { standard_dv: boolean; threshold: boolean; ifu: boolean; human_factor: boolean }>>
  >;
  comment: string;
  setComment: (v: string) => void;
  urgency: string;
  setUrgency: (v: string) => void;
  isDraft: boolean;
  estimatedTotal: number;
  error: string;
  onDismissError: () => void;
  saving: boolean;
  submitting: boolean;
  submitBanner: string;
  onSubmit: () => void;
}) {
  function toggle(skuId: number, field: "standard_dv" | "threshold" | "ifu" | "human_factor") {
    if (!isDraft) return;
    setServiceRows((prev) => ({ ...prev, [skuId]: { ...prev[skuId], [field]: !prev[skuId][field] } }));
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <h2 className="mb-3 font-display text-base font-semibold text-forest-900">Service selection — per SKU</h2>
        <table className="w-full text-left">
          <thead>
            <tr className="font-body text-xs uppercase tracking-wide text-ink-700/70">
              <th className="py-1.5">SKU</th>
              <th className="py-1.5">Standard DV</th>
              <th className="py-1.5">Threshold</th>
              <th className="py-1.5">IFU</th>
              <th className="py-1.5">Human Factor</th>
            </tr>
          </thead>
          <tbody>
            {detail.sku_rows.map((row) => {
              const sel = serviceRows[row.id];
              if (!sel) return null;
              return (
                <tr key={row.id} className="border-t border-ink-700/5">
                  <td className="py-1.5 font-body text-sm text-ink-700">{row.strength}</td>
                  {(["standard_dv", "threshold", "ifu", "human_factor"] as const).map((field) => (
                    <td key={field} className="py-1.5">
                      <input
                        type="checkbox"
                        disabled={!isDraft}
                        checked={sel[field]}
                        onChange={() => toggle(row.id, field)}
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Card>
        <h2 className="mb-3 font-display text-base font-semibold text-forest-900">Total package</h2>
        <p className="font-mono text-2xl text-forest-900">${estimatedTotal.toLocaleString()}</p>
        <p className="mt-1 font-body text-xs text-ink-700/70">
          Estimate updates as you tick services; the authoritative total is saved when you continue.
        </p>
      </Card>

      {isDraft && (
        <Card>
          <h2 className="mb-3 font-display text-base font-semibold text-forest-900">
            Submit this request to the Shaily BD desk
          </h2>
          <div className="mb-3">
            <label className="mb-1.5 block font-body text-sm font-medium text-ink-700" htmlFor="comment">
              Comment for the Shaily BD desk
            </label>
            <textarea
              id="comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="e.g. Bracket SKU 2–3 into one DV."
              className="w-full rounded-lg border border-ink-700/15 px-3.5 py-2.5 font-body text-sm text-ink-700"
              rows={3}
            />
          </div>
          <div className="mb-4 w-72">
            <SelectField
              label="Urgency"
              name="urgency"
              value={urgency}
              onChange={setUrgency}
              options={[
                { value: "Level 1 · call back today", label: "Level 1 · call back today" },
                { value: "Level 2 · call back this week", label: "Level 2 · call back this week" },
              ]}
            />
          </div>
          {error && (
            <div className="mb-4">
              <Banner message={error} onDismiss={onDismissError} />
            </div>
          )}
          {submitBanner && (
            <div className="mb-4">
              <Banner message={submitBanner} onDismiss={() => {}} />
            </div>
          )}
          <Button onClick={onSubmit} loading={saving || submitting}>
            {saving || submitting ? "Submitting…" : "Submit request to Shaily BD"}
          </Button>
        </Card>
      )}
    </div>
  );
}
