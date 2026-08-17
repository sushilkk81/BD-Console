# Customer-Facing UI Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the frontend (currently unstyled) a bold, customer-friendly visual identity — colors, type, shared components — and apply it to the two screens that exist today (Login, Requests), with no change to their functional behavior or the API contract.

**Architecture:** Tailwind CSS v4 (CSS-first config via `@theme`, no `tailwind.config.ts` needed) supplies design tokens and utility classes. A small `frontend/components/` library (Button, TextField, SelectField, Card, StatusChip, EmptyState, Skeleton, Header) is built once and consumed by both pages. `lib/api.ts` gains a typed `ApiError` so pages can show field-level and banner errors instead of one generic string.

**Tech Stack:** Next.js 14.2.13 (existing), Tailwind CSS v4.3.3 + `@tailwindcss/postcss` v4.3.3 (new), `next/font/google` (bundled with Next, no new dependency) for Space Grotesk / IBM Plex Sans / IBM Plex Mono.

**Spec:** `docs/superpowers/specs/2026-08-15-customer-ui-design-system.md`

## Global Constraints

- Color tokens (exact hex, do not deviate): `forest-900 #0F4C33`, `forest-600 #1B7A4D`, `lime-500 #8DC63F`, `orange-500 #F0883E`, `sand-50 #FAF8F3`, `ink-700 #2B2E2C`.
- The signature gradient (`forest-600 → lime-500 → orange-500`) appears in exactly two places: the thin header/page accent band and primary button fills. Never a full-page or full-card wash.
- Fonts: Space Grotesk (display/headings), IBM Plex Sans (body), IBM Plex Mono (data/IDs) — loaded via `next/font/google`, self-hosted at build time.
- No new backend endpoints, no data model change, no change to what `POST /auth/login` or `POST`/`GET /requests` accept or return.
- No navigation shell — only Login and Requests exist; do not add a nav menu.
- No mockups of Phase 2+ screens (platform match, cost & service selection, dashboards) — out of scope for this plan.
- Accessibility floor: visible `:focus-visible` ring on every interactive element; `prefers-reduced-motion` respected (all transitions/animations collapse to instant).
- Responsive floor: single-column layout under ~640px (Tailwind `sm:` breakpoint); the requests table becomes a stacked card-per-request on mobile, not a horizontally-scrolling table.
- Login's domain-based gate logic (`@shaily.com` → role picker, everyone else → plain login) is unchanged — this plan is visual/UX only.

---

## File Structure

```
frontend/
├── postcss.config.mjs          (new)   — Tailwind v4 PostCSS plugin registration
├── app/
│   ├── globals.css             (new)   — @theme design tokens, base styles, reduced-motion
│   ├── layout.tsx               (modify) — font loading, globals.css import, metadata
│   ├── login/page.tsx           (modify) — restyled login screen
│   └── requests/page.tsx        (modify) — restyled requests screen
├── components/
│   ├── Button.tsx               (new)   — primary/secondary/loading button
│   ├── TextField.tsx            (new)   — labeled text input + inline error
│   ├── SelectField.tsx          (new)   — labeled select + inline error
│   ├── Card.tsx                 (new)   — white surface container
│   ├── StatusChip.tsx           (new)   — quadrant-mark status indicator
│   ├── EmptyState.tsx           (new)   — empty-list messaging
│   ├── Skeleton.tsx             (new)   — loading placeholders (table row + mobile card)
│   └── Header.tsx               (new)   — logo + product name + gradient band
├── lib/api.ts                   (modify) — ApiError class + field-error parsing
├── public/shaily-logo.png        (new)   — copied from assets/shaily-logo.png
└── package.json                  (modify) — add tailwindcss, @tailwindcss/postcss
```

---

### Task 1: Tailwind v4 setup, design tokens, fonts

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/app/globals.css`
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Produces: Tailwind utility classes for the named colors `forest-900`, `forest-600`, `lime-500`, `orange-500`, `sand-50`, `ink-700` (e.g. `bg-forest-600`, `text-ink-700`), and font utilities `font-display`, `font-body`, `font-mono` — every later task's components consume these class names directly.

- [ ] **Step 1: Add Tailwind v4 dependencies to `frontend/package.json`**

```json
{
  "name": "bdconsole-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "14.2.13",
    "react": "18.3.1",
    "react-dom": "18.3.1"
  },
  "devDependencies": {
    "typescript": "5.6.2",
    "@types/react": "18.3.5",
    "@types/node": "22.5.5",
    "tailwindcss": "^4.3.3",
    "@tailwindcss/postcss": "^4.3.3"
  }
}
```

- [ ] **Step 2: Install and verify the lockfile updates**

Run: `cd frontend && npm install`
Expected: `package-lock.json` updates to include `tailwindcss` and `@tailwindcss/postcss`, exits 0.

- [ ] **Step 3: Write `frontend/postcss.config.mjs`**

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

- [ ] **Step 4: Write `frontend/app/globals.css`**

```css
@import "tailwindcss";

@theme {
  --color-forest-900: #0F4C33;
  --color-forest-600: #1B7A4D;
  --color-lime-500: #8DC63F;
  --color-orange-500: #F0883E;
  --color-sand-50: #FAF8F3;
  --color-ink-700: #2B2E2C;

  --font-display: var(--font-space-grotesk), ui-sans-serif, system-ui, sans-serif;
  --font-body: var(--font-plex-sans), ui-sans-serif, system-ui, sans-serif;
  --font-mono: var(--font-plex-mono), ui-monospace, SFMono-Regular, monospace;
}

@layer base {
  body {
    @apply bg-sand-50 text-ink-700 font-body;
  }

  :focus-visible {
    outline: 2px solid var(--color-forest-600);
    outline-offset: 2px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
```

- [ ] **Step 5: Rewrite `frontend/app/layout.tsx`** to load fonts and import the stylesheet

```tsx
import type { Metadata } from "next";
import { Space_Grotesk, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-space-grotesk",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "BD Console",
  description: "Shaily BD Console — partnership requests",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${plexSans.variable} ${plexMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 6: Verify the build succeeds**

Run: `cd frontend && npm run build`
Expected: build completes with exit 0; no PostCSS/Tailwind errors in the output.

- [ ] **Step 7: Commit**

```bash
cd /Users/sushil/Documents/ClaudeProjects/BD-Console
git add frontend/package.json frontend/package-lock.json frontend/postcss.config.mjs frontend/app/globals.css frontend/app/layout.tsx
git commit -m "feat(fe): add Tailwind v4 design tokens and font loading"
```

---

### Task 2: Shared component library

**Files:**
- Create: `frontend/components/Button.tsx`
- Create: `frontend/components/TextField.tsx`
- Create: `frontend/components/SelectField.tsx`
- Create: `frontend/components/Card.tsx`
- Create: `frontend/components/StatusChip.tsx`
- Create: `frontend/components/EmptyState.tsx`
- Create: `frontend/components/Skeleton.tsx`
- Create: `frontend/components/Header.tsx`
- Create: `frontend/public/shaily-logo.png` (copied asset)

**Interfaces:**
- Consumes: Tailwind classes from Task 1 (`bg-forest-600`, `font-display`, etc.)
- Produces (exact names/signatures Tasks 3 & 4 rely on):
  - `Button({ variant?: "primary" | "secondary"; loading?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>)`
  - `TextField({ label: string; name: string; type?: string; value: string; onChange: (value: string) => void; required?: boolean; error?: string })`
  - `SelectField({ label: string; name: string; value: string; onChange: (value: string) => void; options: { value: string; label: string }[]; required?: boolean; placeholder?: string; error?: string })`
  - `Card({ children: ReactNode; className?: string })`
  - `StatusChip({ status: string })`
  - `EmptyState({ message: string; action?: ReactNode })`
  - `SkeletonRow()` and `MobileSkeletonCard()`
  - `Header({ userName?: string })`

- [ ] **Step 1: Copy the brand logo into `public/`**

Run: `cp /Users/sushil/Documents/ClaudeProjects/BD-Console/assets/shaily-logo.png /Users/sushil/Documents/ClaudeProjects/BD-Console/frontend/public/shaily-logo.png`
Expected: file exists at `frontend/public/shaily-logo.png`.

- [ ] **Step 2: Write `frontend/components/Button.tsx`**

```tsx
import { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
  loading?: boolean;
};

export function Button({
  variant = "primary",
  loading = false,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-5 py-2.5 font-display font-medium text-sm transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-600 disabled:cursor-not-allowed disabled:opacity-60";
  const variants: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary:
      "bg-gradient-to-r from-forest-600 via-lime-500 to-orange-500 text-white shadow-sm hover:opacity-90",
    secondary: "border border-forest-600 text-forest-600 bg-white hover:bg-sand-50",
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} disabled={disabled || loading} {...rest}>
      {loading && (
        <span
          className="h-4 w-4 animate-spin motion-reduce:animate-none rounded-full border-2 border-white/40 border-t-white"
          aria-hidden="true"
        />
      )}
      {children}
    </button>
  );
}
```

- [ ] **Step 3: Write `frontend/components/TextField.tsx`**

```tsx
type TextFieldProps = {
  label: string;
  name: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  error?: string;
};

export function TextField({ label, name, type = "text", value, onChange, required, error }: TextFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="font-body text-sm font-medium text-ink-700">
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        aria-invalid={!!error}
        aria-describedby={error ? `${name}-error` : undefined}
        className={`rounded-lg border px-3.5 py-2.5 font-body text-sm text-ink-700 outline-none transition-colors focus-visible:border-forest-600 focus-visible:ring-2 focus-visible:ring-forest-600/30 ${
          error ? "border-orange-500" : "border-ink-700/15"
        }`}
      />
      {error && (
        <p id={`${name}-error`} className="font-body text-xs text-orange-500">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Write `frontend/components/SelectField.tsx`**

```tsx
type Option = { value: string; label: string };

type SelectFieldProps = {
  label: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  required?: boolean;
  placeholder?: string;
  error?: string;
};

export function SelectField({
  label,
  name,
  value,
  onChange,
  options,
  required,
  placeholder,
  error,
}: SelectFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="font-body text-sm font-medium text-ink-700">
        {label}
      </label>
      <select
        id={name}
        name={name}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        aria-invalid={!!error}
        aria-describedby={error ? `${name}-error` : undefined}
        className={`rounded-lg border bg-white px-3.5 py-2.5 font-body text-sm text-ink-700 outline-none transition-colors focus-visible:border-forest-600 focus-visible:ring-2 focus-visible:ring-forest-600/30 ${
          error ? "border-orange-500" : "border-ink-700/15"
        }`}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={`${name}-error`} className="font-body text-xs text-orange-500">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Write `frontend/components/Card.tsx`**

```tsx
import { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-ink-700/10 bg-white p-6 shadow-sm ${className}`}>
      {children}
    </div>
  );
}
```

- [ ] **Step 6: Write `frontend/components/StatusChip.tsx`**

```tsx
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
```

- [ ] **Step 7: Write `frontend/components/EmptyState.tsx`**

```tsx
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
```

- [ ] **Step 8: Write `frontend/components/Skeleton.tsx`**

```tsx
export function SkeletonRow() {
  return (
    <tr className="animate-pulse motion-reduce:animate-none">
      <td className="px-4 py-3">
        <span className="block h-4 w-10 rounded bg-ink-700/10" />
      </td>
      <td className="px-4 py-3">
        <span className="block h-4 w-24 rounded bg-ink-700/10" />
      </td>
      <td className="px-4 py-3">
        <span className="block h-4 w-16 rounded bg-ink-700/10" />
      </td>
      <td className="px-4 py-3">
        <span className="block h-4 w-28 rounded bg-ink-700/10" />
      </td>
    </tr>
  );
}

export function MobileSkeletonCard() {
  return (
    <div className="flex animate-pulse flex-col gap-2 px-4 py-3 motion-reduce:animate-none">
      <span className="block h-4 w-32 rounded bg-ink-700/10" />
      <span className="block h-4 w-20 rounded bg-ink-700/10" />
    </div>
  );
}
```

- [ ] **Step 9: Write `frontend/components/Header.tsx`**

```tsx
import Image from "next/image";

export function Header({ userName }: { userName?: string }) {
  return (
    <header className="border-b border-ink-700/10 bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <Image src="/shaily-logo.png" alt="Shaily" width={140} height={37} priority />
          <span className="font-display text-base font-medium text-forest-900">BD Console</span>
        </div>
        {userName && <span className="font-body text-sm text-ink-700/70">{userName}</span>}
      </div>
      <div
        className="h-1 w-full bg-gradient-to-r from-forest-600 via-lime-500 to-orange-500"
        aria-hidden="true"
      />
    </header>
  );
}
```

- [ ] **Step 10: Verify the build succeeds**

Run: `cd frontend && npm run build`
Expected: build completes with exit 0; TypeScript reports no errors for the new component files.

- [ ] **Step 11: Commit**

```bash
cd /Users/sushil/Documents/ClaudeProjects/BD-Console
git add frontend/components frontend/public/shaily-logo.png
git commit -m "feat(fe): add shared component library (Button, fields, Card, StatusChip, EmptyState, Skeleton, Header)"
```

---

### Task 3: Login page — restyle + error handling

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/login/page.tsx`

**Interfaces:**
- Consumes: `Button`, `TextField`, `SelectField`, `Card` from Task 2.
- Produces: `ApiError` class (`status: number`, `message: string`, `fieldErrors: Record<string, string>`) — Task 4 also uses this.

- [ ] **Step 1: Add `ApiError` and error parsing to `frontend/lib/api.ts`**

```ts
export class ApiError extends Error {
  status: number;
  fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

async function parseError(resp: Response, fallback: string): Promise<ApiError> {
  try {
    const body = await resp.json();
    if (resp.status === 422 && Array.isArray(body.detail)) {
      const fieldErrors: Record<string, string> = {};
      for (const item of body.detail) {
        const field = item.loc?.[item.loc.length - 1];
        if (typeof field === "string") fieldErrors[field] = item.msg;
      }
      return new ApiError(resp.status, "Check the highlighted fields and try again.", fieldErrors);
    }
    if (typeof body.detail === "string") {
      return new ApiError(resp.status, body.detail);
    }
  } catch {
    // response wasn't JSON — fall through to the generic message
  }
  return new ApiError(resp.status, fallback);
}

export async function login(name: string, email: string, role?: string) {
  const resp = await fetch(`/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, role }),
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't sign you in — check your name and email and try again.");
  }
  return resp.json();
}

export async function createRequest(token: string, body: { brand: string; market: string; device?: string }) {
  const resp = await fetch(`/api/requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't submit that request — try again.");
  }
  return resp.json();
}

export async function listRequests(token: string) {
  const resp = await fetch(`/api/requests`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    throw await parseError(resp, "We couldn't load your requests — try again.");
  }
  return resp.json();
}
```

- [ ] **Step 2: Rewrite `frontend/app/login/page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, ApiError } from "@/lib/api";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { SelectField } from "@/components/SelectField";
import { Card } from "@/components/Card";

const INTERNAL_ROLES = ["BD Manager", "Key Account Manager"];

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isInternal = email.toLowerCase().endsWith("@shaily.com");

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = "Enter your name.";
    if (!email.trim()) errors.email = "Enter your email.";
    if (isInternal && !role) errors.role = "Select your role.";
    return errors;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBannerError("");
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      const result = await login(name, email, isInternal ? role : undefined);
      localStorage.setItem("bdconsole_token", result.access_token);
      localStorage.setItem("bdconsole_user", JSON.stringify(result.user));
      router.push("/requests");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors);
      } else {
        setBannerError("We couldn't sign you in — check your name and email and try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mb-8 flex items-center gap-3">
        <span className="grid h-8 w-8 grid-cols-2 grid-rows-2 overflow-hidden rounded-md" aria-hidden="true">
          <span className="bg-forest-600" />
          <span className="bg-lime-500" />
          <span className="bg-orange-500" />
          <span className="bg-forest-900" />
        </span>
        <span className="font-display text-lg font-semibold text-forest-900">BD Console</span>
      </div>

      <Card className="w-full max-w-sm">
        <h1 className="mb-6 font-display text-xl font-semibold text-forest-900">Sign in</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
          <TextField label="Name" name="name" value={name} onChange={setName} error={fieldErrors.name} />
          <TextField
            label="Email"
            name="email"
            type="email"
            value={email}
            onChange={setEmail}
            error={fieldErrors.email}
          />
          <div
            className={`grid transition-[grid-template-rows,opacity] duration-200 motion-reduce:transition-none ${
              isInternal ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
            }`}
          >
            <div className="overflow-hidden">
              <SelectField
                label="Role"
                name="role"
                value={role}
                onChange={setRole}
                placeholder="Select…"
                options={INTERNAL_ROLES.map((r) => ({ value: r, label: r }))}
                error={fieldErrors.role}
              />
            </div>
          </div>
          {bannerError && (
            <p role="alert" className="rounded-lg bg-orange-500/10 px-3.5 py-2.5 font-body text-sm text-orange-500">
              {bannerError}
            </p>
          )}
          <Button type="submit" loading={submitting} className="mt-2 w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
```

- [ ] **Step 3: Verify the build succeeds**

Run: `cd frontend && npm run build`
Expected: build completes with exit 0.

- [ ] **Step 4: Manual smoke check against a running dev server**

Run: `cd frontend && npm run dev &` then `sleep 3 && curl -s http://localhost:3000/login | grep -o 'Sign in' | head -1` then stop the dev server (`kill %1`).
Expected: prints `Sign in` (confirms the page renders server-side without crashing).

- [ ] **Step 5: Commit**

```bash
cd /Users/sushil/Documents/ClaudeProjects/BD-Console
git add frontend/lib/api.ts frontend/app/login/page.tsx
git commit -m "feat(fe): restyle login page with design system + inline/banner error handling"
```

---

### Task 4: Requests page — restyle + responsive + status chips

**Files:**
- Modify: `frontend/app/requests/page.tsx`

**Interfaces:**
- Consumes: `Button`, `TextField`, `SelectField`, `Card`, `Header`, `StatusChip`, `EmptyState`, `SkeletonRow`, `MobileSkeletonCard` from Task 2; `ApiError` from Task 3.

- [ ] **Step 1: Rewrite `frontend/app/requests/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, listRequests, ApiError } from "@/lib/api";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { SelectField } from "@/components/SelectField";
import { Card } from "@/components/Card";
import { Header } from "@/components/Header";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRow, MobileSkeletonCard } from "@/components/Skeleton";

type RequestRow = {
  id: number;
  brand: string;
  market: string;
  device: string | null;
  status: string;
  total: number;
};

const MARKETS = [
  { value: "US", label: "US" },
  { value: "EU", label: "EU" },
  { value: "Canada", label: "Canada" },
];

export default function RequestsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | undefined>();
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [highlightId, setHighlightId] = useState<number | null>(null);

  useEffect(() => {
    const t = localStorage.getItem("bdconsole_token");
    if (!t) {
      router.replace("/login");
      return;
    }
    setToken(t);
    const rawUser = localStorage.getItem("bdconsole_user");
    if (rawUser) setUserName(JSON.parse(rawUser).name);
    listRequests(t)
      .then(setRequests)
      .catch(() => setBannerError("We couldn't load your requests — try again."))
      .finally(() => setLoading(false));
  }, [router]);

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!brand.trim()) errors.brand = "Enter a brand.";
    return errors;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBannerError("");
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      const created = await createRequest(token, { brand, market });
      const updated = await listRequests(token);
      setRequests(updated);
      setBrand("");
      setHighlightId(created.id);
      setTimeout(() => setHighlightId(null), 1500);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors);
      } else {
        setBannerError("We couldn't submit that request — try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) return null;

  return (
    <>
      <Header userName={userName} />
      <main className="mx-auto flex max-w-4xl flex-col gap-8 px-4 py-8 sm:px-6">
        <section>
          <h1 className="mb-4 font-display text-lg font-semibold text-forest-900">New request</h1>
          <Card>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4 sm:flex-row sm:items-end" noValidate>
              <div className="flex-1">
                <TextField label="Brand" name="brand" value={brand} onChange={setBrand} error={fieldErrors.brand} />
              </div>
              <div className="w-full sm:w-40">
                <SelectField label="Market" name="market" value={market} onChange={setMarket} options={MARKETS} />
              </div>
              <Button type="submit" loading={submitting}>
                {submitting ? "Submitting…" : "Submit request"}
              </Button>
            </form>
            {bannerError && (
              <p
                role="alert"
                className="mt-4 rounded-lg bg-orange-500/10 px-3.5 py-2.5 font-body text-sm text-orange-500"
              >
                {bannerError}
              </p>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-4 font-display text-lg font-semibold text-forest-900">Your requests</h2>
          <Card className="p-0">
            {!loading && requests.length === 0 ? (
              <EmptyState message="No requests yet — submit your first one above." />
            ) : (
              <>
                <table className="hidden w-full text-left sm:table">
                  <thead>
                    <tr className="border-b border-ink-700/10 font-body text-xs uppercase tracking-wide text-ink-700/50">
                      <th className="px-4 py-3 font-medium">ID</th>
                      <th className="px-4 py-3 font-medium">Brand</th>
                      <th className="px-4 py-3 font-medium">Market</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <>
                        <SkeletonRow />
                        <SkeletonRow />
                        <SkeletonRow />
                      </>
                    ) : (
                      requests.map((r) => (
                        <tr
                          key={r.id}
                          className={`border-b border-ink-700/5 transition-colors last:border-0 ${
                            highlightId === r.id ? "bg-lime-500/10" : ""
                          }`}
                        >
                          <td className="px-4 py-3 font-mono text-sm text-ink-700/70">{r.id}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.brand}</td>
                          <td className="px-4 py-3 font-body text-sm text-ink-700">{r.market}</td>
                          <td className="px-4 py-3">
                            <StatusChip status={r.status} />
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>

                <div className="divide-y divide-ink-700/5 sm:hidden">
                  {loading ? (
                    <>
                      <MobileSkeletonCard />
                      <MobileSkeletonCard />
                      <MobileSkeletonCard />
                    </>
                  ) : (
                    requests.map((r) => (
                      <div
                        key={r.id}
                        className={`flex flex-col gap-1.5 px-4 py-3 transition-colors ${
                          highlightId === r.id ? "bg-lime-500/10" : ""
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm font-medium text-ink-700">{r.brand}</span>
                          <span className="font-mono text-xs text-ink-700/50">#{r.id}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="font-body text-sm text-ink-700/70">{r.market}</span>
                          <StatusChip status={r.status} />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </Card>
        </section>
      </main>
    </>
  );
}
```

- [ ] **Step 2: Verify the build succeeds**

Run: `cd frontend && npm run build`
Expected: build completes with exit 0.

- [ ] **Step 3: Manual smoke check against a running dev server**

Run: `cd frontend && npm run dev &` then `sleep 3 && curl -s http://localhost:3000/requests | grep -o 'Sign in\|New request' | head -1` then stop the dev server (`kill %1`).
Expected: prints `Sign in` — with no token in `localStorage` (a plain `curl` has none), the client-side redirect logic means the initial server-rendered HTML won't show request content; seeing the app respond with the login page content confirms the route builds and mounts without a server error. (Full interactive behavior — the actual requests view — is verified in Task 5 against a real logged-in session.)

- [ ] **Step 4: Commit**

```bash
cd /Users/sushil/Documents/ClaudeProjects/BD-Console
git add frontend/app/requests/page.tsx
git commit -m "feat(fe): restyle requests page with responsive table/card layout and status chips"
```

---

### Task 5: End-to-end verification against the real backend

**Files:** none (verification only)

- [ ] **Step 1: Bring up the full stack**

Run: `cd /Users/sushil/Documents/ClaudeProjects/BD-Console && docker compose up -d --build`
Expected: all three containers (`postgres`, `backend`, `frontend`) reach `Up` status. If `backend` exits because it raced Postgres's startup (a known pre-existing gap, not part of this change), run `docker compose up -d backend` again once `postgres` is healthy.

- [ ] **Step 2: Visually verify Login (desktop width)**

Using a browser automation tool available in your environment (e.g. the `claude-in-chrome` skill, or Playwright if installed), navigate to `http://localhost:3000/login` at a desktop viewport (~1280px) and take a screenshot. Confirm:
- Sand background, white card, gradient accent visible only on the logo mark and the submit button (not a full-page wash).
- Space Grotesk on the "Sign in" heading, IBM Plex Sans on labels/inputs.
- Typing an email ending in `@shaily.com` animates the Role field into view; a non-`@shaily.com` email keeps it hidden.
- Tab through the form — every focused element shows a visible ring.

- [ ] **Step 3: Verify Login functional flow (both paths) against the real backend**

Submit the form as a customer (e.g. name "Test Customer", email `customer@example.com`, no role) — confirm it redirects to `/requests`. Log out (clear `localStorage` or open a private window) and submit again as `name "Test Staff"`, email ending `@shaily.com`, selecting a role — confirm the Role field is required and login succeeds.
Expected: both paths redirect to `/requests` with no console errors.

- [ ] **Step 4: Visually verify Requests (desktop width)**

At the same desktop viewport, screenshot `/requests`. Confirm:
- Header shows the logo, "BD Console", the signed-in name, and the thin gradient band beneath it.
- Submitting a new request shows the button's loading spinner, then the new row appears in the table with a brief highlight and a `StatusChip` (quadrant icon + status text) in the Status column.
- Reload the page — confirm skeleton rows appear briefly before real rows render.

- [ ] **Step 5: Visually verify the empty state**

Log in as a brand-new customer email that has never submitted a request. Screenshot `/requests` and confirm the `EmptyState` message ("No requests yet — submit your first one above.") renders instead of an empty table.

- [ ] **Step 6: Visually verify responsive/mobile layout**

Resize the browser viewport (or use device emulation) to ~375px width. Screenshot both `/login` and `/requests`. Confirm:
- Login card is full-width with comfortable padding, no horizontal scroll.
- Requests page shows the **stacked card list**, not a horizontally-scrolling table — the `<table>` should not be visible at this width.

- [ ] **Step 7: Verify reduced-motion behavior**

Enable "reduce motion" in the OS/browser accessibility settings (or emulate `prefers-reduced-motion: reduce` via browser dev tools), reload `/login` and `/requests`, and confirm the Role field toggle and row highlight no longer animate (they should snap instantly) rather than erroring or looking broken.

- [ ] **Step 8: Verify a 502 still degrades cleanly**

Run: `docker compose stop backend`, then reload `/requests` (or hit `curl -i http://localhost:3000/api/health`).
Expected: `502` with `{"detail":"Backend unavailable"}` from the proxy (pre-existing behavior, confirming this UI pass didn't regress it). Run `docker compose start backend` afterward.

- [ ] **Step 9: Tear down**

Run: `docker compose down`
Expected: all containers stop and are removed.

- [ ] **Step 10: Final commit (if any fixes were needed during verification)**

If Steps 2–8 required any code fixes, commit them now with a message describing what was corrected. If no fixes were needed, this step is a no-op — the feature is already fully committed from Tasks 1–4.

---

## Self-Review Notes

- **Spec coverage:** Visual identity (color/type/gradient rules) → Task 1. Signature quadrant element → Task 2 (`StatusChip`, `EmptyState`, login mark). Component set → Task 2, matches the spec's table exactly. Login page design (animated role field, loading button, inline+banner errors) → Task 3. Requests page design (skeleton, empty state, status chip mapping, highlight-on-add, responsive stacked cards) → Task 4. UX baseline (responsive breakpoint, focus rings, reduced motion) → Tasks 1 (global CSS) and 4 (page-level responsive markup), verified end-to-end in Task 5. Error handling (field-level 422 mapping, banner for 5xx/network) → Task 3 (`ApiError`/`parseError`), consumed by both pages. Testing → Task 5 covers the full manual verification the spec calls for, including the 502 regression check inherited from the earlier proxy fix.
- **Placeholder scan:** none — every step has complete, runnable code or an exact command.
- **Type consistency:** `TextField`/`SelectField`'s `error` prop is defined once in Task 2 and consumed identically in Tasks 3 and 4. `ApiError.fieldErrors` (defined in Task 3) is read the same way in both Login and Requests submit handlers. `StatusChip`, `EmptyState`, `SkeletonRow`/`MobileSkeletonCard`, `Header` prop names match between their Task 2 definitions and Task 4's usage.
- **Scope check:** matches the spec — one design system, two screens, no backend change. Confirmed no task drifts into Phase 2+ screens.
