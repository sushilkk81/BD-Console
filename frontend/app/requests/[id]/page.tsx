"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  PlatformOptions,
  ReferenceProduct,
  RequestDetail,
  getPlatformOptions,
  getRequestDetail,
  listReferenceProducts,
  selectOption,
  updateRequestStep1,
} from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Header } from "@/components/Header";
import { Card } from "@/components/Card";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/SelectField";
import { TextField } from "@/components/TextField";

const MARKETS = [
  { value: "US", label: "US" },
  { value: "EU", label: "EU" },
  { value: "Canada", label: "Canada" },
];
const CART_SIZES = ["1.5 mL", "3 mL", "1 mL PFS", "3 mL PFS", "1 mL Bespoke"];
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

  const [options, setOptions] = useState<PlatformOptions | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState("");
  const [selecting, setSelecting] = useState(false);

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

  const currentRef = refProducts.find((p) => p.brand === brand) ?? null;
  const isDraft = detail?.status === "Draft";

  function reconcileRowsForStrengths(next: string[]) {
    setStrengths(next);
    setSkuRows((prev) => {
      const existing = new Map(prev.map((r) => [r.strength, r]));
      return next.map((s) => {
        if (existing.has(s)) return existing.get(s)!;
        const cart = currentRef?.cartridge ?? "3 mL";
        return { strength: s, cartridge: cart, fill_ml: 1.5 };
      });
    });
  }

  function handleBrandChange(nextBrand: string) {
    setBrand(nextBrand);
    const ref = refProducts.find((p) => p.brand === nextBrand);
    reconcileRowsForStrengths(ref ? [...ref.strengths] : []);
    setDevice(ref?.device ?? null);
    setDifferentiated(false);
    setViscosityVal("");
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

  if (!token) return null;
  if (notFound) {
    return (
      <>
        <Header userName={user?.name} role={user?.role} />
        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
          <Banner message="That request doesn't exist or isn't yours." onDismiss={() => router.push("/requests")} />
        </main>
      </>
    );
  }

  return (
    <>
      <Header userName={user?.name} role={user?.role} />
      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6">
        <nav className="flex gap-2 rounded-full bg-sand-50 p-1" aria-label="Wizard steps">
          {STEPS.map((s) => (
            <button
              key={s.key}
              disabled={!isDraft && s.key !== "form"}
              onClick={() => isDraft && setStep(s.key)}
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
                        onChange={isDraft ? (v) => setMarket(v) : () => {}}
                        options={MARKETS}
                      />
                    </div>
                  </div>
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
                    {isDraft && currentRef && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => setViscosityVal(currentRef.visc_val)}
                      >
                        ＋ Need assistance
                      </Button>
                    )}
                  </div>
                  {currentRef?.visc_ref && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">📄 Literature reference: {currentRef.visc_ref}</p>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 font-display text-base font-semibold text-forest-900">Device type</h2>
                  <label className="flex items-center gap-2 font-body text-sm text-ink-700">
                    <input
                      type="checkbox"
                      disabled={!isDraft}
                      checked={differentiated}
                      onChange={(e) => setDifferentiated(e.target.checked)}
                    />
                    Differentiated formulation (override auto-selected device)
                  </label>
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
              <PlaceholderStepCost />
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
function PlaceholderStepCost() {
  return <Card>Step 3 lands in a later task.</Card>;
}
