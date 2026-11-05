import { useState, type FormEvent } from "react";

import {
  useChangePassword,
  useLoginSessions,
  useMe,
  usePasskeys,
  useRevokeOtherSessions,
  useSignOut,
} from "@/api/queries";
import { PASSWORD_MIN_LENGTH } from "@/config/constants";
import { describeDevice } from "@/lib/device";
import { formatAgo } from "@/lib/format";

import { Button } from "./Button";
import { PasskeySettings } from "./PasskeySettings";
import { Card, Section } from "./Section";
import { SettingRow } from "./SettingRow";

const inputClass =
  "h-9 w-full rounded-md border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

/** Who's signed in, password, devices and sign-out. */
export function AccountSettings() {
  const { data: me } = useMe();
  const signOut = useSignOut();
  if (!me) return null;

  if (me.is_guest) {
    return (
      <Section title="Your account">
        <Card className="divide-y">
          <SettingRow
            label="Demo account"
            hint="Simulated clusters, deleted a day after you started. Sign out to create your own account."
          >
            <Button variant="ghost" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
              Sign out
            </Button>
          </SettingRow>
        </Card>
      </Section>
    );
  }

  return (
    <Section title="Your account">
      <Card className="divide-y">
        <SettingRow label={me.username} hint={me.is_admin ? "Administrator" : "Member"}>
          <Button variant="ghost" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
            Sign out
          </Button>
        </SettingRow>
        {me.password_from_env ? (
          <SettingRow
            label="Password"
            hint="Managed by PULSE_ADMIN_PASSWORD on the server. Change it there and restart."
          >
            <span />
          </SettingRow>
        ) : (
          <PasswordChange hasPassword={me.has_password} />
        )}
        <PasskeySettings />
        <Devices />
      </Card>
    </Section>
  );
}

/** Change the password, or set a first one as a backup after a passkey sign-up. */
function PasswordChange({ hasPassword }: { hasPassword: boolean }) {
  const change = useChangePassword();
  const { data: passkeys = [] } = usePasskeys();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    change.mutate(
      { current, next },
      {
        onSuccess: () => {
          setOpen(false);
          setCurrent("");
          setNext("");
        },
      },
    );
  };

  if (!open) {
    const hint = change.isSuccess
      ? "Saved. Your other devices were signed out."
      : hasPassword
        ? undefined
        : passkeys.length <= 1
          ? "You sign in with a passkey only. Add a password (or a second passkey) as a backup."
          : "Optional: you sign in with your passkeys.";
    return (
      <SettingRow label="Password" hint={hint}>
        <Button variant="ghost" onClick={() => setOpen(true)}>
          {hasPassword ? "Change" : "Set a password"}
        </Button>
      </SettingRow>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-3 p-4">
      {hasPassword && (
        <input
          required
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          placeholder="Current password"
          aria-label="Current password"
          className={inputClass}
        />
      )}
      <input
        required
        type="password"
        autoComplete="new-password"
        minLength={PASSWORD_MIN_LENGTH}
        value={next}
        onChange={(e) => setNext(e.target.value)}
        placeholder={`New password (${PASSWORD_MIN_LENGTH}+ characters)`}
        aria-label="New password"
        className={inputClass}
      />
      {change.error && <p className="text-xs text-fail">{change.error.message}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={change.isPending}>
          {change.isPending ? "Saving…" : hasPassword ? "Change password" : "Set password"}
        </Button>
      </div>
    </form>
  );
}

function Devices() {
  const { data: sessions = [] } = useLoginSessions();
  const revoke = useRevokeOtherSessions();
  const others = sessions.filter((s) => !s.current).length;
  return (
    <div className="space-y-2 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm">Signed-in devices</div>
          <div className="text-xs text-muted-foreground">
            {sessions.length} {sessions.length === 1 ? "device" : "devices"}
          </div>
        </div>
        {others > 0 && (
          <Button variant="ghost" onClick={() => revoke.mutate()} disabled={revoke.isPending}>
            Sign out others
          </Button>
        )}
      </div>
      <ul className="space-y-1 font-mono text-[11px] text-muted-foreground">
        {sessions.map((s) => (
          <li key={s.id} className="flex justify-between gap-3">
            <span className="truncate">{describeDevice(s.user_agent)}</span>
            <span className="shrink-0">
              {s.current ? "this device" : formatAgo(s.last_seen_at)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
