import { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-ink-700/10 bg-white p-6 shadow-sm ${className}`}>
      {children}
    </div>
  );
}
