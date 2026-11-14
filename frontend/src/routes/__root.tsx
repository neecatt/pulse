import type { QueryClient } from "@tanstack/react-query";
import {
  HeadContent,
  Link,
  Outlet,
  createRootRouteWithContext,
  useRouterState,
} from "@tanstack/react-router";

import { useAuthStatus, useSignOut } from "@/api/queries";
import type { Me } from "@/api/types";
import { AuthScreen } from "@/components/AuthScreen";
import { Button } from "@/components/Button";
import { Landing } from "@/components/Landing";
import { DEMO_GUEST_TTL_MS, HOUR_MS } from "@/config/constants";
import { PasskeyHint } from "@/components/PasskeyHint";
import { AppShell } from "@/components/layout/AppShell";
import { useLiveUpdates } from "@/hooks/use-live-updates";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
  notFoundComponent: NotFound,
});

function RootLayout() {
  const { data: status, isPending } = useAuthStatus();
  // Invite links work signed out: the page offers to create an account.
  const joining = useRouterState({ select: (s) => s.location.pathname.startsWith("/join/") });
  // Guides are public and have their own layout, signed in or not.
  const docs = useRouterState({ select: (s) => s.location.pathname.startsWith("/docs") });
  const me = status?.user;
  return (
    <>
      <HeadContent />
      {docs ? (
        <Outlet />
      ) : isPending || !status ? null : me ? (
        <SignedInApp me={me} />
      ) : joining ? (
        <Outlet />
      ) : status.demo ? (
        <Landing status={status} />
      ) : (
        <AuthScreen />
      )}
    </>
  );
}

/** Mounted only while signed in, so the live stream never runs without a session. */
function SignedInApp({ me }: { me: Me }) {
  const live = useLiveUpdates();
  return (
    <AppShell live={live}>
      {me.is_guest ? <DemoBanner me={me} /> : <PasskeyHint />}
      <Outlet />
    </AppShell>
  );
}

/** Reminds a demo guest it's temporary, and offers a real account. */
function DemoBanner({ me }: { me: Me }) {
  const signOut = useSignOut();
  const hoursLeft = Math.max(
    1,
    Math.ceil((new Date(me.created_at).getTime() + DEMO_GUEST_TTL_MS - Date.now()) / HOUR_MS),
  );
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border bg-surface px-4 py-3 text-sm">
      <span className="size-2 shrink-0 rounded-full bg-pend" />
      <span className="min-w-0 flex-1">
        You're exploring a demo on simulated clusters. It's deleted in about {hoursLeft}{" "}
        {hoursLeft === 1 ? "hour" : "hours"}.
      </span>
      <Button
        disabled={signOut.isPending}
        onClick={() =>
          signOut.mutate(undefined, {
            onSettled: () => window.location.assign("/?start=signup"),
          })
        }
      >
        Create your account
      </Button>
    </div>
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
