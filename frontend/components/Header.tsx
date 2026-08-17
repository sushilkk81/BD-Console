"use client";
import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Notification, listNotifications, markNotificationRead } from "@/lib/api";

type Role = "BD Manager" | "Key Account Manager" | "Customer";

const NAV: Record<Role, { label: string; href: string }[]> = {
  "BD Manager": [
    { label: "Command centre", href: "/dashboard/manager" },
    { label: "KAM & assignments", href: "/dashboard/manager/kams" },
    { label: "Customer activity", href: "/dashboard/manager/customers" },
  ],
  "Key Account Manager": [{ label: "My workspace", href: "/dashboard/kam" }],
  Customer: [{ label: "Requests", href: "/requests" }],
};

const POLL_INTERVAL_MS = 30_000;

function NotificationBell({ token }: { token: string }) {
  const router = useRouter();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);

  function load() {
    listNotifications(token).then(setNotifications).catch(() => {
      // a failed poll should never break header rendering — just skip this cycle
    });
  }

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    window.addEventListener("focus", load);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", load);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  async function handleClick(n: Notification) {
    setOpen(false);
    try {
      await markNotificationRead(token, n.id);
    } finally {
      router.push(n.link_path);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
        className="relative rounded-full p-2 text-ink-700/70 transition-colors hover:bg-sand-50 hover:text-forest-600"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             aria-hidden="true">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-orange-500 px-1 font-mono text-[10px] text-white">
            {unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 rounded-xl border border-ink-700/10 bg-white shadow-lg">
          {notifications.length === 0 ? (
            <p className="p-4 font-body text-sm text-ink-700/70">No notifications yet.</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {notifications.map((n) => (
                <li key={n.id} className="border-b border-ink-700/5 last:border-0">
                  <button
                    type="button"
                    onClick={() => handleClick(n)}
                    className={`w-full px-4 py-3 text-left font-body text-sm transition-colors hover:bg-sand-50 ${
                      n.is_read ? "text-ink-700/60" : "text-ink-700"
                    }`}
                  >
                    {n.message}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function Header({ userName, role, token }: { userName?: string; role?: Role; token?: string }) {
  const links = role ? NAV[role] : [];
  return (
    <header className="border-b border-ink-700/10 bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <Image src="/shaily-logo.png" alt="Shaily" width={140} height={37} priority />
          <span className="font-display text-base font-medium text-forest-900">BD Console</span>
        </div>
        {links.length > 0 && (
          <nav className="flex flex-wrap gap-3 sm:gap-5" aria-label="Primary">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="font-body text-sm text-ink-700/70 transition-colors hover:text-forest-600"
              >
                {l.label}
              </Link>
            ))}
          </nav>
        )}
        <div className="flex items-center gap-3">
          {role === "BD Manager" && token && <NotificationBell token={token} />}
          {userName && <span className="font-body text-sm text-ink-700/70">{userName}</span>}
        </div>
      </div>
      <div
        className="h-1 w-full bg-gradient-to-r from-forest-600 via-lime-500 to-orange-500"
        aria-hidden="true"
      />
    </header>
  );
}
