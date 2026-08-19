"use client";

import { useEffect, useId, useRef, useState } from "react";

type AutocompleteFieldProps = {
  label: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  minChars?: number;
  required?: boolean;
  error?: string;
};

/** Free-text field that suggests matches from `options` once `minChars` characters are typed. */
export function AutocompleteField({
  label,
  name,
  value,
  onChange,
  options,
  minChars = 3,
  required,
  error,
}: AutocompleteFieldProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const matches =
    value.trim().length >= minChars
      ? options.filter((o) => o.toLowerCase().includes(value.trim().toLowerCase())).slice(0, 8)
      : [];

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    <div ref={rootRef} className="relative flex flex-col gap-1.5">
      <label htmlFor={name} className="font-body text-sm font-medium text-ink-700">
        {label}
      </label>
      <input
        id={name}
        name={name}
        type="text"
        value={value}
        autoComplete="off"
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        required={required}
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-invalid={!!error}
        aria-describedby={error ? `${name}-error` : undefined}
        className={`rounded-lg border px-3.5 py-2.5 font-body text-sm text-ink-700 outline-none transition-colors focus-visible:border-forest-600 focus-visible:ring-2 focus-visible:ring-forest-600/30 ${
          error ? "border-orange-500" : "border-ink-700/15"
        }`}
      />
      {open && matches.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute top-full z-10 mt-1 w-full overflow-hidden rounded-lg border border-ink-700/10 bg-white shadow-lg"
        >
          {matches.map((m) => (
            <li key={m}>
              <button
                type="button"
                role="option"
                aria-selected={m === value}
                onClick={() => {
                  onChange(m);
                  setOpen(false);
                }}
                className="block w-full px-3.5 py-2 text-left font-body text-sm text-ink-700 transition-colors hover:bg-sand-50"
              >
                {m}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p id={`${name}-error`} className="font-body text-xs text-orange-700">
          {error}
        </p>
      )}
    </div>
  );
}
