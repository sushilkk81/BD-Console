import Image from "next/image";

// `role` is accepted here (typed only, unused) so pages can start passing it ahead
// of a later task that adds role-specific nav links on top of this prop.
export function Header({ userName, role }: { userName?: string; role?: string }) {
  void role;
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
