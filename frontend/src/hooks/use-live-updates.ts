import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { STREAM_URL } from "@/api/client";
import { queryKeys } from "@/api/queries";
import type { LiveUpdate } from "@/api/types";

/**
 * Subscribes to the server's live update stream and refreshes affected queries
 * as soon as a poll finishes. Returns whether the stream is connected.
 * EventSource reconnects on its own after network drops or the phone sleeping.
 */
export function useLiveUpdates(): boolean {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource(STREAM_URL);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message: MessageEvent<string>) => {
      const update = JSON.parse(message.data) as LiveUpdate;
      if (update.type === "access") {
        void client.invalidateQueries();
        return;
      }
      // ["jobs"] is a prefix of every job query, so open job pages refresh too.
      void client.invalidateQueries({ queryKey: queryKeys.jobs });
      void client.invalidateQueries({ queryKey: queryKeys.accounts });
      if (update.events.length > 0) void client.invalidateQueries({ queryKey: ["events"] });
    };
    return () => source.close();
  }, [client]);

  return connected;
}
