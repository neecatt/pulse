import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { queryKeys } from "@/api/queries";
import { ApiError } from "@/api/client";
import { addPasskey, isCancelled, passkeyErrorMessage } from "@/lib/passkeys";

/** Add a passkey on this device; cancelling the prompt isn't an error. */
export function useAddPasskey() {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);

  const add = async () => {
    setBusy(true);
    setError(null);
    setNeedsVerification(false);
    try {
      await addPasskey();
      setNeedsVerification(false);
      await client.invalidateQueries({ queryKey: queryKeys.passkeys });
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setNeedsVerification(true);
      else if (!isCancelled(e)) setError(passkeyErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return {
    add,
    busy,
    error,
    needsVerification,
    clearVerification: () => setNeedsVerification(false),
  };
}
