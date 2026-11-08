import { startAuthentication } from "@simplewebauthn/browser";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import { queryKeys, useMe, usePasskeys } from "@/api/queries";
import { Button } from "@/components/Button";
import { Card } from "@/components/Section";
import { passkeysSupported, passkeyErrorMessage } from "@/lib/passkeys";

/** Confirm this browser's existing session without changing the signed-in user. */
export function SessionReauth({
  message = "Confirm it’s you before opening a cluster assistant.",
  onVerified,
}: {
  message?: string;
  onVerified?: () => void;
}) {
  const client = useQueryClient();
  const { data: me } = useMe();
  const { data: passkeys = [] } = usePasskeys();
  const [password, setPassword] = useState("");
  const verify = useMutation({
    mutationFn: async (method: "password" | "passkey") => {
      if (method === "password") {
        await api.auth.reauthenticate(password);
      } else {
        const { challenge_id, options } = await api.passkeys.reauthOptions();
        const credential = await startAuthentication({ optionsJSON: options });
        await api.passkeys.reauthenticate(challenge_id, credential);
      }
    },
    onSuccess: () => {
      setPassword("");
      void client.invalidateQueries({ queryKey: queryKeys.assistantAccess });
      onVerified?.();
    },
  });
  return (
    <Card className="space-y-3 p-4">
      <p className="text-sm">{message}</p>
      {passkeysSupported() && passkeys.length > 0 && (
        <Button disabled={verify.isPending} onClick={() => verify.mutate("passkey")}>
          Use passkey
        </Button>
      )}
      {me?.has_password && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            verify.mutate("password");
          }}
        >
          <input
            aria-label="Current password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm"
          />
          <Button type="submit" disabled={verify.isPending}>
            Confirm password
          </Button>
        </form>
      )}
      {verify.error && (
        <p role="alert" className="text-sm text-fail">
          {passkeyErrorMessage(verify.error)}
        </p>
      )}
    </Card>
  );
}
