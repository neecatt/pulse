import {
  type QueryClient,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { FALLBACK_REFRESH_MS } from "@/config/constants";

import { api } from "./client";
import type {
  Account,
  AccountCreate,
  AccountUpdate,
  AuthStatus,
  Credentials,
  JobMetrics,
  JobUpdate,
  Me,
  PreferencesUpdate,
} from "./types";

export const queryKeys = {
  accounts: ["accounts"] as const,
  jobs: ["jobs"] as const,
  job: (id: number) => ["jobs", id] as const,
  // Under ["jobs"], so live updates refresh open charts too.
  jobMetrics: (id: number) => ["jobs", id, "metrics"] as const,
  // Also under ["jobs"], so live updates refresh the runs table.
  runs: (arrayId?: string) => ["jobs", "runs", arrayId ?? "all"] as const,
  events: (limit: number) => ["events", limit] as const,
  preferences: ["preferences"] as const,
  pushConfig: ["push-config"] as const,
  setup: ["setup"] as const,
  authStatus: ["auth-status"] as const,
  loginSessions: ["login-sessions"] as const,
  health: ["health"] as const,
};

/** Sign-in state: whether setup is needed, and who is signed in (or null). */
export function useAuthStatus() {
  return useQuery({
    queryKey: queryKeys.authStatus,
    queryFn: api.auth.status,
    staleTime: Infinity,
  });
}

/** The signed-in user, or null when signed out. */
export function useMe(): { data: Me | null | undefined; isPending: boolean } {
  const { data, isPending } = useAuthStatus();
  return { data: data?.user, isPending };
}

/** Sign in, create the first account, or sign up; then load the app. */
export function useSignIn(mode: "login" | "setup" | "signup") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => api.auth[mode](body),
    onSuccess: (user) => setSignedIn(client, user),
  });
}

export function useSignOut() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.auth.logout,
    onSettled: () => setSignedIn(client, null),
  });
}

/**
 * Record who is signed in (null signs the app out) and drop everything cached for
 * the previous session, so one account's data never shows up for another.
 * The auth-status query itself is kept and updated in place: the root layout is
 * subscribed to it, and replacing it would leave the layout watching a stale copy.
 */
export function setSignedIn(client: QueryClient, user: Me | null): void {
  client.removeQueries({ predicate: (query) => query.queryKey[0] !== queryKeys.authStatus[0] });
  client.setQueryData<AuthStatus>(queryKeys.authStatus, (status) => ({
    setup_required: false,
    signup_allowed: status?.signup_allowed ?? false,
    user,
  }));
}

export function useChangePassword() {
  return useMutation({
    mutationFn: ({ current, next }: { current: string; next: string }) =>
      api.auth.changePassword(current, next),
  });
}

export function useLoginSessions() {
  return useQuery({ queryKey: queryKeys.loginSessions, queryFn: api.auth.sessions });
}

export function useRevokeOtherSessions() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.auth.revokeOthers,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.loginSessions }),
  });
}

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

export function useRuns(arrayId?: string) {
  return useQuery({
    queryKey: queryKeys.runs(arrayId),
    queryFn: () => api.runs.list(arrayId),
    refetchInterval: FALLBACK_REFRESH_MS,
  });
}

export function useJobMetrics(id: number) {
  return useQuery({
    queryKey: queryKeys.jobMetrics(id),
    queryFn: () => api.jobs.metrics(id),
    refetchInterval: FALLBACK_REFRESH_MS,
  });
}

/** Metrics for several jobs at once (compare view); results keep `ids` order. */
export function useJobsMetrics(ids: number[]): {
  data: (JobMetrics | undefined)[];
  isPending: boolean;
} {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: queryKeys.jobMetrics(id),
      queryFn: () => api.jobs.metrics(id),
    })),
    combine: (results) => ({
      data: results.map((r) => r.data),
      isPending: results.some((r) => r.isPending),
    }),
  });
}

export function useUpdateJob(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: JobUpdate) => api.jobs.update(id, body),
    onSuccess: (job) => {
      client.setQueryData(queryKeys.job(id), job);
      void client.invalidateQueries({ queryKey: queryKeys.jobs, exact: true });
    },
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

export function useHealth() {
  return useQuery({ queryKey: queryKeys.health, queryFn: api.health, staleTime: Infinity });
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
    mutationFn: (body: PreferencesUpdate) => api.preferences.update(body),
    onSuccess: (data) => client.setQueryData(queryKeys.preferences, data),
  });
}
