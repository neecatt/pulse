import { useEffect } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, assistantStreamUrl, claudeStreamUrl } from "@/api/client";
import { queryKeys } from "@/api/queries";
import type { AssistantLive, AssistantProvider, ClaudeState } from "@/api/types";
import { applyAssistantLive } from "@/lib/assistant";

export function useAssistant(account: number, provider: AssistantProvider, enabled: boolean) {
  const client = useQueryClient();
  const state = useQuery({
    queryKey: queryKeys.assistantState(account, provider),
    queryFn: () => api.assistants.state(account, provider),
    enabled,
  });
  const connected = state.data?.connection.connected ?? false;
  useEffect(() => {
    if (!enabled || !connected) return;
    let disposed = false;
    let previous: AssistantLive | undefined;
    const source = new EventSource(assistantStreamUrl(account, provider));
    source.onmessage = (event: MessageEvent<string>) => {
      const live = applyAssistantLive(
        client.getQueryData<AssistantLive>(queryKeys.assistantState(account, provider)),
        JSON.parse(event.data) as AssistantLive,
      );
      if (previous) {
        for (const id of Object.keys(previous.active)) {
          if (!(id in live.active)) {
            void client.invalidateQueries({
              queryKey: queryKeys.assistantHistory(account, provider, id),
            });
            void client.invalidateQueries({
              queryKey: queryKeys.assistantThreads(account, provider),
            });
          }
        }
      }
      if (live.connection.signed_in && !previous?.connection.signed_in) {
        void client.invalidateQueries({ queryKey: queryKeys.assistantThreads(account, provider) });
      }
      previous = live;
      client.setQueryData(queryKeys.assistantState(account, provider), live);
      if (!live.connection.connected) source.close();
    };
    source.onerror = () => {
      void api.assistants
        .state(account, provider)
        .then((live) => {
          if (disposed) return;
          client.setQueryData(queryKeys.assistantState(account, provider), live);
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
  }, [account, provider, enabled, connected, client]);
  return state;
}

export function useAssistantThreads(
  account: number,
  provider: AssistantProvider,
  enabled: boolean,
) {
  return useInfiniteQuery({
    queryKey: queryKeys.assistantThreads(account, provider),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.assistants.threads(account, provider, pageParam),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

/** Claude Code's native sign-in running on the cluster. */
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
      if (!value.running) source.close();
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

/** The models the cluster's CLI offers. They change only when the CLI is updated. */
export function useAssistantModels(account: number, provider: AssistantProvider, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.assistantModels(account, provider),
    queryFn: () => api.assistants.models(account, provider),
    enabled,
    staleTime: 30 * 60_000,
  });
}

export function useAssistantHistory(
  account: number,
  provider: AssistantProvider,
  id: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.assistantHistory(account, provider, id),
    queryFn: () => api.assistants.history(account, provider, id),
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
