type StatusCategory = "attention" | "progress" | "closed" | "active";

function categorize(status: string): StatusCategory {
  const s = status.toLowerCase();
  if (s.includes("awaiting")) return "attention";
  if (s.includes("review") || s.includes("progress") || s.includes("assigned")) return "progress";
  if (s.includes("closed") || s.includes("declined") || s.includes("rejected") || s.includes("complete")) {
    return "closed";
  }
  return "active";
}

// [top-left, top-right, bottom-left, bottom-right] — echoes the Shaily mark's
// four-quadrant geometry; muted quadrants use a translucent ink tone.
const QUADRANTS: Record<StatusCategory, [string, string, string, string]> = {
  attention: ["bg-orange-500", "bg-ink-700/15", "bg-ink-700/15", "bg-lime-500"],
  progress: ["bg-forest-600", "bg-ink-700/15", "bg-ink-700/15", "bg-lime-500"],
  closed: ["bg-ink-700/15", "bg-ink-700/15", "bg-ink-700/15", "bg-ink-700/15"],
  active: ["bg-forest-600", "bg-ink-700/15", "bg-ink-700/15", "bg-orange-500"],
};

export function StatusChip({ status }: { status: string }) {
  const category = categorize(status);
  const [tl, tr, bl, br] = QUADRANTS[category];
  return (
    <span className="inline-flex items-center gap-2 font-body text-sm text-ink-700">
      <span className="grid h-3 w-3 grid-cols-2 grid-rows-2 overflow-hidden rounded-[3px]" aria-hidden="true">
        <span className={tl} />
        <span className={tr} />
        <span className={bl} />
        <span className={br} />
      </span>
      {status}
    </span>
  );
}
