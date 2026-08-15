"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

const INTERNAL_ROLES = ["BD Manager", "Key Account Manager"];

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState("");

  const isInternal = email.toLowerCase().endsWith("@shaily.com");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const result = await login(name, email, isInternal ? role : undefined);
      localStorage.setItem("bdconsole_token", result.access_token);
      localStorage.setItem("bdconsole_user", JSON.stringify(result.user));
      router.push("/requests");
    } catch (err) {
      setError("Login failed. Check your details and try again.");
    }
  }

  return (
    <main>
      <h1>Sign in to the BD Console</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        {isInternal && (
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value)} required>
              <option value="">Select…</option>
              {INTERNAL_ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
        )}
        {error && <p role="alert">{error}</p>}
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}
