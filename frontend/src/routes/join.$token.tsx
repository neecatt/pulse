import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import { useAcceptInvite, useInviteInfo, useInviteSignup, useMe } from "@/api/queries";
import type { InviteInfo } from "@/api/types";
import { AuthScreen } from "@/components/AuthScreen";
import { Button } from "@/components/Button";
import { PASSWORD_MIN_LENGTH } from "@/config/constants";

export const Route = createFileRoute("/join/$token")({
  head: () => ({ meta: [{ title: "Join a team — Pulse" }] }),
  component: JoinPage,
});

const inputClass =
  "h-10 w-full rounded-md border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

/** Where an invite link lands, signed in or not. */
function JoinPage() {
  const { token } = Route.useParams();
  const { data: me } = useMe();
  const info = useInviteInfo(token);
  const [signingIn, setSigningIn] = useState(false);

  // Signing in from here comes straight back to this page, now signed in.
  if (!me && signingIn) return <AuthScreen />;

  const body = info.error ? (
    <p className="text-sm text-muted-foreground">{info.error.message}</p>
  ) : !info.data ? null : me ? (
    <AcceptInvite token={token} username={me.username} />
  ) : (
    <SignUpAndJoin token={token} onSignIn={() => setSigningIn(true)} />
  );

  return (
    <div className="grid min-h-[70dvh] place-items-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-2 text-center">
          <div className="inline-flex items-center gap-2 font-mono text-sm font-medium">
            <span className="size-2 animate-pulse rounded-full bg-run" /> pulse
          </div>
          <Heading info={info.data} invalid={Boolean(info.error)} />
        </div>
        {body}
      </div>
    </div>
  );
}

function Heading({ info, invalid }: { info: InviteInfo | undefined; invalid: boolean }) {
  if (invalid) return <h1 className="text-xl font-medium tracking-tight">Invite not valid</h1>;
  if (!info) return null;
  return (
    <>
      <h1 className="text-xl font-medium tracking-tight">Join {info.team}</h1>
      <p className="text-sm text-muted-foreground">
        {info.owner} invited you to follow their team's training jobs live. You can view them; only{" "}
        {info.owner} can change them.
      </p>
    </>
  );
}

function AcceptInvite({ token, username }: { token: string; username: string }) {
  const accept = useAcceptInvite();
  const navigate = useNavigate();
  return (
    <div className="space-y-3">
      <Button
        className="h-10 w-full"
        disabled={accept.isPending}
        onClick={() => accept.mutate(token, { onSuccess: () => void navigate({ to: "/" }) })}
      >
        {accept.isPending ? "Joining…" : `Join as ${username}`}
      </Button>
      {accept.error && <p className="text-xs text-fail">{accept.error.message}</p>}
      <p className="text-center text-xs text-muted-foreground">
        <Link to="/" className="underline underline-offset-4">
          Not now
        </Link>
      </p>
    </div>
  );
}

function SignUpAndJoin({ token, onSignIn }: { token: string; onSignIn: () => void }) {
  const signup = useInviteSignup(token);
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    // Straight to the jobs: the invite is used up, so this page can't show it again.
    signup.mutate(
      { username: username.trim(), password },
      { onSuccess: () => void navigate({ to: "/" }) },
    );
  };

  return (
    <div className="space-y-3">
      <form onSubmit={submit} className="space-y-3">
        <input
          required
          autoFocus
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Choose a username"
          aria-label="Username"
          className={inputClass}
        />
        <input
          required
          type="password"
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={`Password (${PASSWORD_MIN_LENGTH}+ characters)`}
          aria-label="Password"
          className={inputClass}
        />
        {signup.error && <p className="text-xs text-fail">{signup.error.message}</p>}
        <Button type="submit" disabled={signup.isPending} className="h-10 w-full">
          {signup.isPending ? "One moment…" : "Create account and join"}
        </Button>
      </form>
      <p className="text-center text-xs text-muted-foreground">
        Already have an account?{" "}
        <button
          type="button"
          onClick={onSignIn}
          className="text-foreground underline underline-offset-4"
        >
          Sign in first
        </button>
      </p>
    </div>
  );
}
