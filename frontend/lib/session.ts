"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export type Role = "BD Manager" | "Key Account Manager" | "Customer";
export type SessionUser = { id: number; org_id: number; name: string; email: string; role: Role };

export const LANDING: Record<Role, string> = {
  "BD Manager": "/dashboard/manager",
  "Key Account Manager": "/dashboard/kam",
  Customer: "/requests",
};

export function useRoleGuard(role: Role) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    const t = localStorage.getItem("bdconsole_token");
    const rawUser = localStorage.getItem("bdconsole_user");
    if (!t || !rawUser) {
      router.replace("/login");
      return;
    }
    const parsed = JSON.parse(rawUser) as SessionUser;
    if (parsed.role !== role) {
      router.replace(LANDING[parsed.role] ?? "/login");
      return;
    }
    setToken(t);
    setUser(parsed);
  }, [router, role]);

  return { token, user };
}
