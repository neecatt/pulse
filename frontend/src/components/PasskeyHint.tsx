import { KeyRound, X } from "lucide-react";

import { usePasskeys } from "@/api/queries";
import { useAddPasskey } from "@/hooks/use-add-passkey";
import { passkeysSupported } from "@/lib/passkeys";
import { updateUiSettings, useUiSettings } from "@/lib/ui-settings";

import { Button } from "./Button";

/** One-time suggestion to add a passkey, for accounts that have none yet. */
export function PasskeyHint() {
  const { passkeyHintDismissed } = useUiSettings();
  const { data: passkeys } = usePasskeys();
  const { add, busy, error } = useAddPasskey();

  if (
    passkeyHintDismissed ||
    !passkeysSupported() ||
    passkeys === undefined ||
    passkeys.length > 0
  ) {
    return null;
  }

  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border bg-surface px-4 py-3 text-sm">
      <KeyRound className="size-4 shrink-0 text-run" />
      <span className="min-w-0 flex-1">
        Sign in faster next time: add a passkey on this device.
        {error && <span className="block text-xs text-fail">{error}</span>}
      </span>
      <Button onClick={add} disabled={busy}>
        {busy ? "Waiting…" : "Add passkey"}
      </Button>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => updateUiSettings({ passkeyHintDismissed: true })}
        className="text-muted-foreground hover:text-foreground"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
