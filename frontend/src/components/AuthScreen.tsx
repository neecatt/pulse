import { useQueryClient } from "@tanstack/react-query";
import { WebAuthnAbortService } from "@simplewebauthn/browser";
import { KeyRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { setSignedIn, useAuthStatus, useSignIn } from "@/api/queries";
import { PASSWORD_MIN_LENGTH } from "@/config/constants";
import {
  isCancelled,
  passkeyAutofillSupported,
  passkeyErrorMessage,
  passkeysSupported,
  signInWithPasskey,
} from "@/lib/passkeys";

import { Button } from "./Button";

const inputClass =
  "h-10 w-full rounded-md border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

type Mode = "login" | "setup" | "signup";

/** Sign-in screen; on a fresh server it creates the admin account instead. */
export function AuthScreen() {
  const { data: status } = useAuthStatus();
  const [signingUp, setSigningUp] = useState(false);
  const mode: Mode = status?.setup_required ? "setup" : signingUp ? "signup" : "login";

  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-2 text-center">
          <div className="inline-flex items-center gap-2 font-mono text-sm font-medium">
            <span className="size-2 animate-pulse rounded-full bg-run" /> pulse
          </div>
          <h1 className="text-xl font-medium tracking-tight">{TITLES[mode]}</h1>
          <p className="text-sm text-muted-foreground">{HINTS[mode]}</p>
        </div>
        {status && mode === "login" && <PasskeySignIn />}
        {status && <CredentialsForm key={mode} mode={mode} />}
        {status?.signup_allowed && mode !== "setup" && (
          <p className="text-center text-xs text-muted-foreground">
            {signingUp ? "Already have an account?" : "New here?"}{" "}
            <button
              type="button"
              onClick={() => setSigningUp(!signingUp)}
              className="text-foreground underline underline-offset-4"
            >
              {signingUp ? "Sign in" : "Create an account"}
            </button>
          </p>
        )}
      </div>
    </div>
  );
}

const TITLES: Record<Mode, string> = {
  login: "Sign in",
  setup: "Set up Pulse",
  signup: "Create an account",
};

const HINTS: Record<Mode, string> = {
  login: "Monitor your Slurm jobs across all your HPC accounts.",
  setup: "Create the admin account for this server. You'll use it to sign in from any device.",
  signup: "Your accounts and jobs are private to you.",
};

function CredentialsForm({ mode }: { mode: Mode }) {
  const signIn = useSignIn(mode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const creating = mode !== "login";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    signIn.mutate({
      username: username.trim(),
      password,
      ...(mode === "setup" ? { setup_code: setupCode.trim() } : {}),
    });
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      {mode === "setup" && (
        <div className="space-y-1.5">
          <input
            required
            autoFocus
            autoComplete="one-time-code"
            autoCapitalize="characters"
            spellCheck={false}
            value={setupCode}
            onChange={(e) => setSetupCode(e.target.value)}
            placeholder="Setup code, e.g. 3F2A-9C1B-77D0"
            aria-label="Setup code"
            className={`${inputClass} font-mono`}
          />
          <p className="text-xs text-muted-foreground">
            Printed in the server log when Pulse starts. With Docker:{" "}
            <code className="font-mono">docker compose logs pulse | grep "setup code"</code>
          </p>
        </div>
      )}
      <input
        required
        autoFocus={mode !== "setup"}
        // "webauthn" lets the browser offer saved passkeys in this field's autofill.
        autoComplete={mode === "login" ? "username webauthn" : "username"}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        placeholder="Username"
        aria-label="Username"
        className={inputClass}
      />
      <input
        required
        type="password"
        autoComplete={creating ? "new-password" : "current-password"}
        minLength={creating ? PASSWORD_MIN_LENGTH : undefined}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder={creating ? `Password (${PASSWORD_MIN_LENGTH}+ characters)` : "Password"}
        aria-label="Password"
        className={inputClass}
      />
      {signIn.error && <p className="text-xs text-fail">{signIn.error.message}</p>}
      <Button type="submit" disabled={signIn.isPending} className="h-10 w-full">
        {signIn.isPending ? "One moment…" : creating ? "Create account" : "Sign in"}
      </Button>
    </form>
  );
}

/**
 * Passkey sign-in: a button, plus a quiet background request so the browser
 * offers passkeys as soon as you tap the username field.
 */
function PasskeySignIn() {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void passkeyAutofillSupported().then((supported) => {
      if (!supported || !active) return;
      signInWithPasskey(true)
        .then((user) => setSignedIn(client, user))
        .catch((e: unknown) => {
          if (active && !isCancelled(e)) setError(passkeyErrorMessage(e));
        });
    });
    return () => {
      active = false;
      WebAuthnAbortService.cancelCeremony();
    };
  }, [client]);

  if (!passkeysSupported()) return null;

  const signIn = async () => {
    setBusy(true);
    setError(null);
    try {
      setSignedIn(client, await signInWithPasskey());
    } catch (e) {
      if (!isCancelled(e)) setError(passkeyErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <Button onClick={signIn} disabled={busy} className="h-10 w-full">
        <KeyRound className="size-4" />
        {busy ? "Waiting for your passkey…" : "Sign in with a passkey"}
      </Button>
      {error && <p className="text-xs text-fail">{error}</p>}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" />
        or with your password
        <span className="h-px flex-1 bg-border" />
      </div>
    </div>
  );
}
