import type { QueryClient } from "@tanstack/react-query";
import {
  HeadContent,
  Link,
  Outlet,
  createRootRouteWithContext,
  useRouterState,
} from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { AuthScreen } from "@/components/AuthScreen";
import { PasskeyHint } from "@/components/PasskeyHint";
import { AppShell } from "@/components/layout/AppShell";
import { useLiveUpdates } from "@/hooks/use-live-updates";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
  notFoundComponent: NotFound,
});

function RootLayout() {
  const { data: me, isPending } = useMe();
  // Invite links work signed out: the page offers to create an account.
  const joining = useRouterState({ select: (s) => s.location.pathname.startsWith("/join/") });
  return (
    <>
      <HeadContent />
      {isPending ? null : me ? <SignedInApp /> : joining ? <Outlet /> : <AuthScreen />}
    </>
  );
}

/** Mounted only while signed in, so the live stream never runs without a session. */
function SignedInApp() {
  const live = useLiveUpdates();
  return (
    <AppShell live={live}>
      <PasskeyHint />
      <Outlet />
    </AppShell>
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
