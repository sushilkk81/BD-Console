type HeatmapProps = {
  rows: string[];
  cols: string[];
  matrix: Record<string, Record<string, number>>;
};

// Sequential ramp (single hue, light -> dark) discretized into three tiers so every
// in-cell label clears WCAG AA text contrast (>=4.5:1) against its own fill — a
// continuous alpha blend has a "muddy middle" band where neither white nor ink text
// reaches 4.5:1, so the ramp is stepped instead of interpolated. See dataviz skill.
const TIERS = [
  { upTo: 1 / 3, background: "rgba(27, 122, 77, 0.25)", text: "text-ink-700" },
  { upTo: 2 / 3, background: "rgba(27, 122, 77, 0.55)", text: "text-ink-700" },
  { upTo: Infinity, background: "#1B7A4D", text: "text-white" },
] as const;

function tierFor(ratio: number) {
  return TIERS.find((tier) => ratio <= tier.upTo) ?? TIERS[TIERS.length - 1];
}

export function Heatmap({ rows, cols, matrix }: HeatmapProps) {
  const max = Math.max(1, ...rows.flatMap((r) => cols.map((c) => matrix[r]?.[c] ?? 0)));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">
          Heatmap of values by representative and category — darker cells indicate larger values.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="p-2" />
            {cols.map((c) => (
              <th key={c} scope="col" className="p-2 font-body text-xs font-medium text-ink-700/70">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r}>
              <th scope="row" className="p-2 text-left font-body text-xs font-medium text-ink-700/70">
                {r}
              </th>
              {cols.map((c) => {
                const value = matrix[r]?.[c] ?? 0;
                const tier = value > 0 ? tierFor(value / max) : null;
                return (
                  <td key={c} className="p-2 text-center">
                    {tier && (
                      <div
                        className={`mx-auto flex h-10 w-14 items-center justify-center rounded-md font-mono text-xs font-medium ${tier.text}`}
                        style={{ backgroundColor: tier.background }}
                        title={`${r} × ${c}: ${value}`}
                      >
                        {value}
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
