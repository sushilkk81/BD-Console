"use client";
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Label, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getDashboardMetrics, ApiError, DashboardMetrics } from "@/lib/api";
import { useRoleGuard } from "@/lib/session";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { Banner } from "@/components/Banner";
import { Heatmap } from "@/components/Heatmap";

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"];

// Recessive, hairline, solid — never dashed — per dataviz skill grid guidance.
const GRID_STROKE = "rgba(43, 46, 44, 0.12)";
const AXIS_STROKE = "rgba(43, 46, 44, 0.2)";
const AXIS_TICK = { fontSize: 12, fill: "rgba(43, 46, 44, 0.7)" };
const LABEL_STYLE = { fontSize: 11, fill: "#2B2E2C" };
// Bars are capped thin and rounded only at the data end, per mark spec.
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
const MAX_BAR_SIZE = 24;

function Kpi({ value, label }: { value: string; label: string }) {
  return (
    <Card>
      <p className="font-display text-2xl font-semibold text-forest-900">{value}</p>
      <p className="font-body text-sm text-ink-700/70">{label}</p>
    </Card>
  );
}

export default function ManagerCommandCentre() {
  const { token, user } = useRoleGuard("BD Manager");
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    getDashboardMetrics(token)
      .then(setMetrics)
      .catch((err) => setError(err instanceof ApiError ? err.message : "We couldn't load the command centre."));
  }, [token]);

  if (!token || !user) return null;

  const annualTarget = metrics ? Object.values(metrics.quarterly_target).reduce((a, b) => a + b, 0) : 0;
  const expectedPipeline = metrics
    ? Object.values(metrics.rep_quarterly).reduce(
        (sum, rep) => sum + Object.values(rep.quarters).reduce((a, b) => a + b, 0), 0,
      )
    : 0;
  const newCustomers = metrics ? Object.values(metrics.new_customers_qtr).reduce((a, b) => a + b, 0) : 0;
  const coverage = annualTarget > 0 ? Math.round((expectedPipeline / annualTarget) * 100) : 0;

  const targetVsExpected = QUARTERS.map((q) => ({
    quarter: q,
    Target: metrics?.quarterly_target[q] ?? 0,
    Expected: metrics
      ? Object.values(metrics.rep_quarterly).reduce((sum, rep) => sum + (rep.quarters[q] ?? 0), 0)
      : 0,
  }));
  const newCustomersByQtr = QUARTERS.map((q) => ({ quarter: q, "New customers": metrics?.new_customers_qtr[q] ?? 0 }));
  const production = metrics
    ? Object.entries(metrics.platform_production)
        .sort((a, b) => b[1] - a[1])
        .map(([platform, units]) => ({ platform, "Million units": units }))
    : [];
  const reps = metrics ? Object.keys(metrics.rep_quarterly) : [];
  const platforms = metrics ? Object.keys(metrics.platform_production) : [];
  const customers = metrics ? Array.from(new Set(Object.values(metrics.rep_customer_matrix).flatMap((c) => Object.keys(c)))) : [];

  return (
    <>
      <Header userName={user.name} role={user.role} />
      <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6">
        <h1 className="font-display text-lg font-semibold text-forest-900">Business against target, by quarter</h1>
        {error && <Banner message={error} onDismiss={() => setError("")} />}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Kpi value={`$${annualTarget}M`} label="Annual target" />
          <Kpi value={`$${expectedPipeline}M`} label="Expected pipeline" />
          <Kpi value={`${coverage}%`} label="Target coverage" />
          <Kpi value={String(newCustomers)} label="New customers (FY)" />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">Business vs target — by quarter</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={targetVsExpected}>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="quarter" tick={AXIS_TICK} stroke={AXIS_STROKE} />
                <YAxis tick={AXIS_TICK} stroke={AXIS_STROKE} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Target" fill="#F0883E" radius={BAR_RADIUS} maxBarSize={MAX_BAR_SIZE}>
                  <LabelList dataKey="Target" position="top" style={LABEL_STYLE} formatter={(v: number) => `$${v}M`} />
                </Bar>
                <Bar dataKey="Expected" fill="#1B7A4D" radius={BAR_RADIUS} maxBarSize={MAX_BAR_SIZE}>
                  <LabelList dataKey="Expected" position="top" style={LABEL_STYLE} formatter={(v: number) => `$${v}M`} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">New customers added — by quarter</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={newCustomersByQtr}>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="quarter" tick={AXIS_TICK} stroke={AXIS_STROKE} />
                <YAxis tick={AXIS_TICK} stroke={AXIS_STROKE} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="New customers" fill="#8DC63F" radius={BAR_RADIUS} maxBarSize={MAX_BAR_SIZE}>
                  <LabelList dataKey="New customers" position="top" style={LABEL_STYLE} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>

        <Card>
          <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">
            Expected production output per Shaily variant (million units)
          </h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={production}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="platform" tick={AXIS_TICK} stroke={AXIS_STROKE} />
              <YAxis tick={AXIS_TICK} stroke={AXIS_STROKE}>
                <Label value="Million units" angle={-90} position="insideLeft" style={{ fontSize: 11, fill: "rgba(43,46,44,0.7)" }} />
              </YAxis>
              <Tooltip />
              <Bar dataKey="Million units" fill="#1B7A4D" radius={BAR_RADIUS} maxBarSize={MAX_BAR_SIZE}>
                <LabelList dataKey="Million units" position="top" style={LABEL_STYLE} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">BD representative × platform ($M)</h2>
            <Heatmap rows={reps} cols={platforms} matrix={metrics?.rep_platform_matrix ?? {}} />
          </Card>
          <Card>
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">BD representative × business partner ($M)</h2>
            <Heatmap rows={reps} cols={customers} matrix={metrics?.rep_customer_matrix ?? {}} />
          </Card>
        </div>

        <Card padding="p-0">
          <div className="overflow-x-auto p-6">
            <h2 className="mb-4 font-display text-sm font-semibold text-forest-900">
              Per-representative business — quarter-wise & annual ($M)
            </h2>
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/70">
                  <th scope="col" className="px-3 py-2 font-medium">Representative</th>
                  <th scope="col" className="px-3 py-2 font-medium">Region</th>
                  {QUARTERS.map((q) => (
                    <th key={q} scope="col" className="px-3 py-2 font-medium">{q}</th>
                  ))}
                  <th scope="col" className="px-3 py-2 font-medium">Annual</th>
                </tr>
              </thead>
              <tbody>
                {reps.map((rep) => {
                  const data = metrics!.rep_quarterly[rep];
                  const annual = Object.values(data.quarters).reduce((a, b) => a + b, 0);
                  return (
                    <tr key={rep} className="border-b border-ink-700/5 last:border-0">
                      <td className="px-3 py-2 font-body text-sm text-ink-700">{rep}</td>
                      <td className="px-3 py-2 font-body text-sm text-ink-700/70">{data.region}</td>
                      {QUARTERS.map((q) => (
                        <td key={q} className="px-3 py-2 font-body text-sm text-ink-700">${data.quarters[q] ?? 0}M</td>
                      ))}
                      <td className="px-3 py-2 font-body text-sm font-medium text-ink-700">${annual}M</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </main>
    </>
  );
}
