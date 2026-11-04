import type { QueryClient } from "@tanstack/react-query";
import { HeadContent, Link, Outlet, createRootRouteWithContext } from "@tanstack/react-router";

import { AppShell } from "@/components/layout/AppShell";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
  notFoundComponent: NotFound,
});

function RootLayout() {
  return (
    <>
      <HeadContent />
      <AppShell>
        <Outlet />
      </AppShell>
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
