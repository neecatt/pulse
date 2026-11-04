import { useCallback, useEffect, useState } from "react";

import { usePushConfig } from "@/api/queries";
import { disablePush, enablePush, getPushStatus, type PushStatus } from "@/lib/push";

/** Push state for this device plus actions to toggle it. */
export function usePush() {
  const { data: config } = usePushConfig();
  const [status, setStatus] = useState<PushStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPushStatus().then((s) => !cancelled && setStatus(s));
    return () => {
      cancelled = true;
    };
  }, []);

  const run = useCallback(async (action: () => Promise<PushStatus>) => {
    setBusy(true);
    setError(null);
    try {
      setStatus(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }, []);

  const publicKey = config?.public_key ?? null;
  return {
    status,
    busy,
    error,
    serverEnabled: Boolean(config?.enabled && publicKey),
    enable: () => (publicKey ? run(() => enablePush(publicKey)) : Promise.resolve()),
    disable: () => run(disablePush),
  };
}
