import type { QueryClient } from "@tanstack/react-query";
import { HeadContent, Link, Outlet, createRootRouteWithContext } from "@tanstack/react-router";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
  notFoundComponent: NotFound,
});

function RootLayout() {
  return (
    <>
      <HeadContent />
      <div className="min-h-screen">
        <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
            <Link to="/" className="flex items-center gap-2 font-mono text-sm font-medium">
              <span className="size-2 animate-pulse rounded-full bg-run" /> pulse
            </Link>
            <nav className="flex gap-5 text-sm text-muted-foreground">
              <Link
                to="/"
                activeOptions={{ exact: true }}
                activeProps={{ className: "text-foreground" }}
              >
                Jobs
              </Link>
              <Link to="/accounts" activeProps={{ className: "text-foreground" }}>
                Accounts
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6 md:py-10">
          <Outlet />
        </main>
      </div>
    </>
  );
}

function NotFound() {
  return (
    <div className="py-24 text-center">
      <h1 className="font-mono text-5xl">404</h1>
      <p className="mt-3 text-sm text-muted-foreground">This page doesn't exist.</p>
      <Link to="/" className="mt-6 inline-block text-sm underline underline-offset-4">
        Back to jobs
      </Link>
    </div>
  );
}
