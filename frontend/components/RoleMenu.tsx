"use client";

import { useEffect, useId, useRef, useState } from "react";

type Option = { value: string; label: string; description?: string };

type RoleMenuProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  placeholder: string;
};

export function RoleMenu({ label, value, onChange, options, placeholder }: RoleMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative w-full">
      <span className="mb-1.5 block font-body text-sm font-medium text-ink-700">{label}</span>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 rounded-lg border border-ink-700/15 bg-white px-4 py-3.5 font-display text-sm font-medium text-ink-700 outline-none transition-colors focus-visible:border-forest-600 focus-visible:ring-2 focus-visible:ring-forest-600/30"
      >
        <span className={selected ? "text-ink-700" : "text-ink-700/50"}>
          {selected ? selected.label : placeholder}
        </span>
        <span
          aria-hidden="true"
          className={`shrink-0 text-forest-600 transition-transform ${open ? "rotate-180" : ""}`}
        >
          ▾
        </span>
      </button>

      {open && (
        <div
          id={menuId}
          role="menu"
          className="absolute z-10 mt-2 w-full overflow-hidden rounded-lg border border-ink-700/10 bg-white shadow-lg"
        >
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="menuitem"
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              className={`flex w-full flex-col gap-0.5 px-4 py-3.5 text-left font-body text-sm transition-colors hover:bg-sand-50 ${
                opt.value === value ? "bg-lime-500/10 text-forest-900" : "text-ink-700"
              }`}
            >
              <span className="font-display font-medium">{opt.label}</span>
              {opt.description && <span className="text-xs text-ink-700/60">{opt.description}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
