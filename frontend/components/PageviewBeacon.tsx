"use client";
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { recordPageview } from "@/lib/api";

export function PageviewBeacon() {
  const pathname = usePathname();

  useEffect(() => {
    const token = localStorage.getItem("bdconsole_token");
    const sessionId = localStorage.getItem("bdconsole_session_id");
    const rawUser = localStorage.getItem("bdconsole_user");
    if (!token || !sessionId || !rawUser) return;
    let user: { role: string };
    try {
      user = JSON.parse(rawUser) as { role: string };
    } catch {
      return;
    }
    if (user.role !== "Customer") return;
    recordPageview(token, sessionId, pathname).catch(() => {
      // fire-and-forget — a beacon failure must never surface to the customer
    });
  }, [pathname]);

  return null;
}
