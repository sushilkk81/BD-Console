import Image from "next/image";
import Link from "next/link";

type Role = "BD Manager" | "Key Account Manager" | "Customer";

const NAV: Record<Role, { label: string; href: string }[]> = {
  "BD Manager": [
    { label: "Command centre", href: "/dashboard/manager" },
    { label: "KAM & assignments", href: "/dashboard/manager/kams" },
  ],
  "Key Account Manager": [{ label: "My workspace", href: "/dashboard/kam" }],
  Customer: [{ label: "Requests", href: "/requests" }],
};

export function Header({ userName, role }: { userName?: string; role?: Role }) {
  const links = role ? NAV[role] : [];
  return (
    <header className="border-b border-ink-700/10 bg-white">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <Image src="/shaily-logo.png" alt="Shaily" width={140} height={37} priority />
          <span className="font-display text-base font-medium text-forest-900">BD Console</span>
        </div>
        {links.length > 0 && (
          <nav className="hidden gap-5 sm:flex" aria-label="Primary">
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
        {userName && <span className="font-body text-sm text-ink-700/70">{userName}</span>}
      </div>
      <div
        className="h-1 w-full bg-gradient-to-r from-forest-600 via-lime-500 to-orange-500"
        aria-hidden="true"
      />
    </header>
  );
}
