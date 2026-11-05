import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { queryKeys, usePasskeys } from "@/api/queries";
import { useAddPasskey } from "@/hooks/use-add-passkey";
import { formatAgo } from "@/lib/format";
import { passkeysSupported } from "@/lib/passkeys";

import { Button } from "./Button";
import { useConfirm } from "@/hooks/use-confirm";

/** Passkeys on this account: add one for this device, or remove old ones. */
export function PasskeySettings() {
  const client = useQueryClient();
  const { data: passkeys = [] } = usePasskeys();
  const { add, busy, error } = useAddPasskey();
  const supported = passkeysSupported();
  const confirm = useConfirm();

  const remove = (id: number, name: string) =>
    confirm.ask({
      title: `Remove the passkey "${name}"?`,
      description: "You can still sign in with your password.",
      action: "Remove passkey",
      danger: true,
      onConfirm: () => {
        void api.passkeys
          .remove(id)
          .then(() => client.invalidateQueries({ queryKey: queryKeys.passkeys }));
      },
    });

  return (
    <div className="space-y-2 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm">Passkeys</div>
          <div className="text-xs text-muted-foreground">
            {supported
              ? "Sign in with Face ID, Touch ID or your screen lock instead of a password."
              : "Passkeys need a secure connection: open Pulse over HTTPS (or on localhost)."}
          </div>
        </div>
        {supported && (
          <Button variant="ghost" onClick={add} disabled={busy}>
            {busy ? "Waiting…" : "Add a passkey"}
          </Button>
        )}
      </div>
      {error && <p className="text-xs text-fail">{error}</p>}
      {passkeys.length > 0 && (
        <ul className="space-y-1 font-mono text-[11px] text-muted-foreground">
          {passkeys.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3">
              <span className="truncate">{p.name}</span>
              <span className="flex shrink-0 items-center gap-3">
                {p.last_used_at ? `used ${formatAgo(p.last_used_at)}` : "not used yet"}
                <button
                  type="button"
                  onClick={() => remove(p.id, p.name)}
                  className="text-fail hover:underline"
                >
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {confirm.dialog}
    </div>
  );
}
