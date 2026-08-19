"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { login, ApiError } from "@/lib/api";
import { LANDING } from "@/lib/session";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { SelectField } from "@/components/SelectField";
import { RoleMenu } from "@/components/RoleMenu";
import { Card } from "@/components/Card";
import { Banner } from "@/components/Banner";

const CUSTOMER_TITLES = ["R&D Manager", "BD Manager"];

type EntryRole = "customer" | "bd_manager" | "kam";

const ENTRY_ROLE_OPTIONS: { value: EntryRole; label: string; description: string }[] = [
  { value: "customer", label: "Customer", description: "Submit and track a device development request" },
  { value: "bd_manager", label: "BD Login (Admin)", description: "Review requests and assign Key Account Managers" },
  { value: "kam", label: "Key Account Manager", description: "Respond to requests assigned to you" },
];

const ENTRY_ROLE_TO_INTERNAL_ROLE: Record<"bd_manager" | "kam", string> = {
  bd_manager: "BD Manager",
  kam: "Key Account Manager",
};

export default function LoginPage() {
  const router = useRouter();
  const [entryRole, setEntryRole] = useState<EntryRole | "">("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [title, setTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isInternal = entryRole === "bd_manager" || entryRole === "kam";

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = "Enter your name.";
    if (!email.trim()) errors.email = "Enter your email.";
    if (!isInternal) {
      if (!title) errors.title = "Select your role in the organization.";
      if (!phone.trim()) errors.phone = "Enter your phone number.";
    }
    return errors;
  }

  function changeRole() {
    setEntryRole("");
    setFieldErrors({});
    setBannerError("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!entryRole) return;
    setBannerError("");
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      const result = await login(
        name,
        email,
        isInternal ? ENTRY_ROLE_TO_INTERNAL_ROLE[entryRole as "bd_manager" | "kam"] : undefined,
        isInternal ? undefined : title,
        isInternal ? undefined : phone
      );
      localStorage.setItem("bdconsole_token", result.access_token);
      localStorage.setItem("bdconsole_user", JSON.stringify(result.user));
      if (result.session_id) {
        localStorage.setItem("bdconsole_session_id", result.session_id);
      } else {
        localStorage.removeItem("bdconsole_session_id");
      }
      router.push(LANDING[result.user.role as keyof typeof LANDING] ?? "/requests");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors);
      } else if (err instanceof ApiError) {
        setBannerError(err.message);
      } else {
        setBannerError("We couldn't sign you in — check your name and email and try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div
        className="h-1 w-full bg-gradient-to-r from-forest-600 via-lime-500 to-orange-500"
        aria-hidden="true"
      />
      <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-12">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/login-hero.jpg')" }}
          aria-hidden="true"
        />

        <div className="relative z-10 flex w-full flex-col items-center">
          <Card className="w-full max-w-sm">
            <div className="mb-6 flex justify-center">
              <Image src="/shaily-logo.png" alt="Shaily" width={140} height={37} priority />
            </div>
            {!entryRole ? (
              <>
                <h1 className="mb-1 font-display text-xl font-semibold text-forest-900">Sign in</h1>
                <p className="mb-6 font-body text-sm text-ink-700/70">Select how you&apos;d like to sign in.</p>
                <RoleMenu
                  label="Sign in as"
                  value={entryRole}
                  onChange={(v) => setEntryRole(v as EntryRole)}
                  options={ENTRY_ROLE_OPTIONS}
                  placeholder="Select…"
                />
              </>
            ) : (
              <>
                <div className="mb-6 flex items-center justify-between gap-3">
                  <h1 className="font-display text-xl font-semibold text-forest-900">
                    {ENTRY_ROLE_OPTIONS.find((o) => o.value === entryRole)?.label}
                  </h1>
                  <button
                    type="button"
                    onClick={changeRole}
                    className="shrink-0 font-body text-sm font-medium text-forest-600 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-600"
                  >
                    Change role
                  </button>
                </div>
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
                  {!isInternal && (
                    <>
                      <SelectField
                        label="Your role in the organization"
                        name="title"
                        value={title}
                        onChange={setTitle}
                        placeholder="Select…"
                        options={CUSTOMER_TITLES.map((t) => ({ value: t, label: t }))}
                        error={fieldErrors.title}
                      />
                      <TextField
                        label="Phone number"
                        name="phone"
                        type="tel"
                        value={phone}
                        onChange={setPhone}
                        error={fieldErrors.phone}
                      />
                    </>
                  )}
                  {bannerError && <Banner message={bannerError} onDismiss={() => setBannerError("")} />}
                  <Button type="submit" loading={submitting} className="mt-2 w-full">
                    {submitting ? "Signing in…" : "Sign in"}
                  </Button>
                </form>
              </>
            )}
          </Card>
        </div>
      </main>
    </>
  );
}
