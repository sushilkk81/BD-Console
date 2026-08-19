"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, ApiError } from "@/lib/api";
import { LANDING } from "@/lib/session";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { SelectField } from "@/components/SelectField";
import { Card } from "@/components/Card";
import { Banner } from "@/components/Banner";

const INTERNAL_ROLES = ["BD Manager", "Key Account Manager"];
const CUSTOMER_TITLES = ["R&D Manager", "BD Manager"];

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [title, setTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isInternal = email.toLowerCase().endsWith("@shaily.com");

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = "Enter your name.";
    if (!email.trim()) errors.email = "Enter your email.";
    if (isInternal && !role) errors.role = "Select your role.";
    if (!isInternal && email.trim()) {
      if (!title) errors.title = "Select your role in the organization.";
      if (!phone.trim()) errors.phone = "Enter your phone number.";
    }
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
      const result = await login(name, email, isInternal ? role : undefined, isInternal ? undefined : title,
                                  isInternal ? undefined : phone);
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
            aria-hidden={!isInternal}
            inert={!isInternal ? true : undefined}
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
          <div
            className={`grid transition-[grid-template-rows,opacity] duration-200 motion-reduce:transition-none ${
              !isInternal && email.trim() ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
            }`}
            aria-hidden={isInternal || !email.trim()}
            inert={isInternal || !email.trim() ? true : undefined}
          >
            <div className="overflow-hidden flex flex-col gap-4">
              <SelectField
                label="Your role in the organization"
                name="title"
                value={title}
                onChange={setTitle}
                placeholder="Select…"
                options={CUSTOMER_TITLES.map((t) => ({ value: t, label: t }))}
                error={fieldErrors.title}
              />
              <TextField label="Phone number" name="phone" type="tel" value={phone} onChange={setPhone}
                         error={fieldErrors.phone} />
            </div>
          </div>
          {bannerError && <Banner message={bannerError} onDismiss={() => setBannerError("")} />}
          <Button type="submit" loading={submitting} className="mt-2 w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
      </main>
    </>
  );
}
