import { Link } from "@tanstack/react-router";
import { Activity, Bell, Layers, Server, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface NavItem {
  to: "/" | "/activity" | "/accounts" | "/settings";
  label: string;
  icon: LucideIcon;
}

const NAV: NavItem[] = [
  { to: "/", label: "Jobs", icon: Layers },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/accounts", label: "Accounts", icon: Server },
  { to: "/settings", label: "Alerts", icon: Bell },
];

/** Top bar on desktop, bottom tab bar on phones (app-like when installed). */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="pt-safe sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2 font-mono text-sm font-medium">
            <span className="size-2 animate-pulse rounded-full bg-run" /> pulse
          </Link>
          <nav className="hidden gap-6 text-sm text-muted-foreground md:flex">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                activeOptions={{ exact: item.to === "/" }}
                activeProps={{ className: "text-foreground" }}
                className="transition-colors hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pt-6 pb-28 md:pt-10 md:pb-16">{children}</main>

      <nav className="pb-safe fixed inset-x-0 bottom-0 z-20 border-t bg-background/90 backdrop-blur md:hidden">
        <div className="grid grid-cols-4">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: to === "/" }}
              className="flex flex-col items-center gap-1 py-2.5 text-[11px] text-muted-foreground"
              activeProps={{ className: "text-foreground" }}
            >
              <Icon className="size-5" strokeWidth={1.5} />
              {label}
            </Link>
          ))}
        </div>
      </nav>
    </div>
  );
}
