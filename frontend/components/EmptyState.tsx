import { ReactNode } from "react";

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-ink-700/15 px-6 py-12 text-center">
      <span className="grid h-8 w-8 grid-cols-2 grid-rows-2 overflow-hidden rounded-md opacity-40" aria-hidden="true">
        <span className="bg-forest-600" />
        <span className="bg-lime-500" />
        <span className="bg-orange-500" />
        <span className="bg-ink-700/30" />
      </span>
      <p className="font-body text-sm text-ink-700/70">{message}</p>
      {action}
    </div>
  );
}
