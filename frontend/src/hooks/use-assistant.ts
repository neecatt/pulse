import { useEffect } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, assistantStreamUrl, claudeStreamUrl } from "@/api/client";
import { queryKeys } from "@/api/queries";
import type { AssistantLive, ClaudeState } from "@/api/types";
import { applyAssistantLive } from "@/lib/assistant";

export function useAssistant(account: number, enabled: boolean) {
  const client = useQueryClient();
  const state = useQuery({
    queryKey: queryKeys.assistantState(account),
    queryFn: () => api.assistants.state(account),
    enabled,
  });
  const connected = state.data?.connection.connected ?? false;
  useEffect(() => {
    if (!enabled || !connected) return;
    let disposed = false;
    let previous: AssistantLive | undefined;
    const source = new EventSource(assistantStreamUrl(account));
    source.onmessage = (event: MessageEvent<string>) => {
      const live = applyAssistantLive(
        client.getQueryData<AssistantLive>(queryKeys.assistantState(account)),
        JSON.parse(event.data) as AssistantLive,
      );
      if (previous) {
        for (const id of Object.keys(previous.active)) {
          if (!(id in live.active)) {
            void client.invalidateQueries({ queryKey: queryKeys.assistantHistory(account, id) });
            void client.invalidateQueries({ queryKey: queryKeys.assistantThreads(account) });
          }
        }
      }
      if (live.connection.signed_in && !previous?.connection.signed_in) {
        void client.invalidateQueries({ queryKey: queryKeys.assistantThreads(account) });
      }
      previous = live;
      client.setQueryData(queryKeys.assistantState(account), live);
      if (!live.connection.connected) source.close();
    };
    source.onerror = () => {
      void api.assistants
        .state(account)
        .then((live) => {
          if (disposed) return;
          client.setQueryData(queryKeys.assistantState(account), live);
          if (!live.connection.connected) source.close();
        })
        .catch(() => {
          if (!disposed) source.close();
        });
    };
    return () => {
      disposed = true;
      source.close();
    };
  }, [account, enabled, connected, client]);
  return state;
}

export function useAssistantThreads(account: number, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: queryKeys.assistantThreads(account),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.assistants.threads(account, pageParam),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export function useClaude(account: number) {
  const client = useQueryClient();
  const state = useQuery({
    queryKey: queryKeys.claudeState(account),
    queryFn: () => api.claude.state(account),
  });
  const running = state.data?.running ?? false;
  const connectionId = state.data?.connection_id;
  useEffect(() => {
    if (!running) return;
    let disposed = false;
    const source = new EventSource(claudeStreamUrl(account));
    source.onmessage = (event: MessageEvent<string>) => {
      const value = JSON.parse(event.data) as ClaudeState;
      const current = client.getQueryData<ClaudeState>(queryKeys.claudeState(account));
      if (
        value.connection_id !== connectionId ||
        (current && current.connection_id !== connectionId)
      )
        return;
      client.setQueryData(queryKeys.claudeState(account), value);
      if (!value.running) {
        source.close();
        void client.invalidateQueries({ queryKey: queryKeys.claudeThreads(account) });
      }
    };
    source.onerror = () => {
      void api.claude
        .state(account)
        .then((value) => {
          if (disposed) return;
          client.setQueryData(queryKeys.claudeState(account), value);
          if (!value.running) source.close();
        })
        .catch(() => {
          if (!disposed) source.close();
        });
    };
    return () => {
      disposed = true;
      source.close();
    };
  }, [account, running, connectionId, client]);
  return state;
}

export function useClaudeThreads(account: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.claudeThreads(account),
    queryFn: () => api.claude.threads(account),
    enabled,
    staleTime: 60000,
  });
}

export function useAssistantHistory(account: number, id: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.assistantHistory(account, id),
    queryFn: () => api.assistants.history(account, id),
    enabled,
  });
}

/** Keep server calls out of components, and refresh the relevant cached views. */
export function useAssistantAction<T, R>(account: number, action: (input: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: action,
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["assistants", account] });
      void client.invalidateQueries({ queryKey: queryKeys.assistantAccess });
      void client.invalidateQueries({ queryKey: queryKeys.assistantAudit });
    },
  });
}
