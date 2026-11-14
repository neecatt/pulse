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
  AssistantProvider,
  AuthStatus,
  Credentials,
  JobMetrics,
  JobUpdate,
  Me,
  MembershipUpdate,
  PreferencesUpdate,
} from "./types";

/** A team you can share with, from your side. */
export interface ShareTeam {
  id: number;
  name: string;
  /** You share all your jobs with it already. */
  shareAll: boolean;
}

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
  passkeys: ["passkeys"] as const,
  teams: ["teams"] as const,
  invite: (token: string) => ["invite", token] as const,
  health: ["health"] as const,
  siteStats: ["site-stats"] as const,
  assistants: ["assistants"] as const,
  assistantState: (account: number, provider: AssistantProvider) =>
    ["assistants", account, provider, "state"] as const,
  assistantThreads: (account: number, provider: AssistantProvider) =>
    ["assistants", account, provider, "threads"] as const,
  assistantHistory: (account: number, provider: AssistantProvider, id: string) =>
    ["assistants", account, provider, "history", id] as const,
  assistantAccess: ["assistant-access"] as const,
  claudeState: (account: number) => ["assistants", account, "claude-state"] as const,
  assistantAudit: ["assistant-audit"] as const,
};

export function useAssistantAccess() {
  return useQuery({
    queryKey: queryKeys.assistantAccess,
    queryFn: api.assistants.access,
    refetchInterval: FALLBACK_REFRESH_MS,
  });
}

export function useAssistantAudit() {
  return useQuery({ queryKey: queryKeys.assistantAudit, queryFn: api.assistants.audit });
}

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
    demo: status?.demo ?? false,
    user,
  }));
}

/** "Try the demo": sign in as a new guest with simulated clusters. */
export function useTryDemo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.auth.demo,
    onSuccess: (user) => setSignedIn(client, user),
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ current, next }: { current: string; next: string }) =>
      api.auth.changePassword(current, next),
    // A passkey-only account has a backup password from now on.
    onSuccess: () =>
      client.setQueryData<AuthStatus>(queryKeys.authStatus, (status) =>
        status?.user ? { ...status, user: { ...status.user, has_password: true } } : status,
      ),
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

export function usePasskeys() {
  return useQuery({ queryKey: queryKeys.passkeys, queryFn: api.passkeys.list });
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

export function useShareJob(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ teamId, shared }: { teamId: number; shared: boolean }) =>
      api.jobs.share(id, teamId, shared),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.job(id) }),
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

/** Visitors, demos and sign-ups; admins only. */
export function useSiteStats(enabled: boolean) {
  return useQuery({ queryKey: queryKeys.siteStats, queryFn: api.siteStats, enabled });
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

export function useShareAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, teamId, shared }: { id: number; teamId: number; shared: boolean }) =>
      api.accounts.share(id, teamId, shared),
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

// Teams

export function useTeams() {
  return useQuery({ queryKey: queryKeys.teams, queryFn: api.teams.overview });
}

/** A team change that only affects the team page. */
function useTeamMutation<T, R>(fn: (arg: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.teams }),
  });
}

/** A team change that also changes which jobs and accounts you can see. */
function useAccessMutation<T, R>(fn: (arg: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => client.invalidateQueries() });
}

export const useCreateTeam = () => useTeamMutation(api.teams.create);
export const useRenameTeam = () => useTeamMutation(api.teams.rename);
export const useRemoveMember = () => useTeamMutation(api.teams.removeMember);
export const useCreateInvite = () => useTeamMutation(() => api.teams.invite());
export const useRevokeInvite = () => useTeamMutation(api.teams.revokeInvite);
export const useUpdateMembership = () =>
  useTeamMutation(({ teamId, ...body }: MembershipUpdate & { teamId: number }) =>
    api.teams.updateMembership(teamId, body),
  );
export const useDeleteTeam = () => useAccessMutation(() => api.teams.remove());
export const useLeaveTeam = () => useAccessMutation(api.teams.leave);
export const useAcceptInvite = () => useAccessMutation(api.teams.accept);

/** Every team you can share with (your own and the ones you joined), and
 * whether you already share all your jobs with it. */
export function useMyTeams(): ShareTeam[] {
  const { data } = useTeams();
  if (!data) return [];
  const joined = data.memberships.map((m) => ({
    id: m.team_id,
    name: m.name,
    shareAll: m.share_all,
  }));
  const { owned } = data;
  return owned
    ? [{ id: owned.id, name: owned.name, shareAll: owned.share_all }, ...joined]
    : joined;
}

/** The team an invite link is for; works signed out. */
export function useInviteInfo(token: string) {
  return useQuery({
    queryKey: queryKeys.invite(token),
    queryFn: () => api.teams.inviteInfo(token),
    retry: false,
  });
}

/** Create an account through an invite and sign in with it. */
export function useInviteSignup(token: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => api.teams.signup(token, body),
    onSuccess: (user) => setSignedIn(client, user),
  });
}
