import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { queryKeys } from "@/api/queries";
import { addPasskey, isCancelled, passkeyErrorMessage } from "@/lib/passkeys";

/** Add a passkey on this device; cancelling the prompt isn't an error. */
export function useAddPasskey(): { add: () => Promise<void>; busy: boolean; error: string | null } {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setBusy(true);
    setError(null);
    try {
      await addPasskey();
      await client.invalidateQueries({ queryKey: queryKeys.passkeys });
    } catch (e) {
      if (!isCancelled(e)) setError(passkeyErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return { add, busy, error };
}
