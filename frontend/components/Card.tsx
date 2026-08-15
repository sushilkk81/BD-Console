import { ReactNode } from "react";

export function Card({
  children,
  className = "",
  padding = "p-6",
}: {
  children: ReactNode;
  className?: string;
  padding?: string;
}) {
  return (
    <div className={`rounded-2xl border border-ink-700/10 bg-white shadow-sm ${padding} ${className}`}>
      {children}
    </div>
  );
}
