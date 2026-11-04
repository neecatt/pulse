import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { Account, AccountCreate, AccountUpdate, Preferences } from "./types";

// Live data arrives over the /api/stream channel (see useLiveUpdates); this is
// only a safety net in case the stream is down.
const FALLBACK_REFRESH_MS = 60_000;

export const queryKeys = {
  accounts: ["accounts"] as const,
  jobs: ["jobs"] as const,
  job: (id: number) => ["jobs", id] as const,
  events: (limit: number) => ["events", limit] as const,
  preferences: ["preferences"] as const,
  pushConfig: ["push-config"] as const,
  setup: ["setup"] as const,
};

export function useAccounts() {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: api.accounts.list,
    refetchInterval: FALLBACK_REFRESH_MS,
  });
}

export function useJobs() {
  return useQuery({
    queryKey: queryKeys.jobs,
    queryFn: () => api.jobs.list(),
    refetchInterval: FALLBACK_REFRESH_MS,
  });
}

export function useJob(id: number) {
  return useQuery({
    queryKey: queryKeys.job(id),
    queryFn: () => api.jobs.get(id),
    refetchInterval: FALLBACK_REFRESH_MS,
  });
}

export function useEvents(limit = 50) {
  return useQuery({
    queryKey: queryKeys.events(limit),
    queryFn: () => api.events.list(limit),
    refetchInterval: FALLBACK_REFRESH_MS,
  });
}

export function usePreferences() {
  return useQuery({ queryKey: queryKeys.preferences, queryFn: api.preferences.get });
}

export function useSetup() {
  return useQuery({ queryKey: queryKeys.setup, queryFn: api.setup, staleTime: Infinity });
}

export function usePushConfig() {
  return useQuery({
    queryKey: queryKeys.pushConfig,
    queryFn: api.push.config,
    staleTime: Infinity,
  });
}

/** Lookup table for rendering account labels and colours next to jobs and events. */
export function useAccountMap(): Map<number, Account> {
  const { data = [] } = useAccounts();
  return new Map(data.map((a) => [a.id, a]));
}

export function useCreateAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: AccountCreate) => api.accounts.create(body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.accounts }),
  });
}

export function useUpdateAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: AccountUpdate & { id: number }) => api.accounts.update(id, body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.accounts }),
  });
}

export function useDeleteAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.accounts.remove(id),
    onSuccess: () => client.invalidateQueries(),
  });
}

export function useCheckAccount() {
  return useMutation({ mutationFn: (id: number) => api.accounts.check(id) });
}

export function useIssueAgentToken() {
  return useMutation({ mutationFn: (id: number) => api.accounts.issueAgentToken(id) });
}

export function useUpdatePreferences() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Preferences) => api.preferences.update(body),
    onSuccess: (data) => client.setQueryData(queryKeys.preferences, data),
  });
}
