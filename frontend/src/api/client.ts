import type {
  AuthenticationResponseJSON,
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
  RegistrationResponseJSON,
} from "@simplewebauthn/browser";

import { API_URL } from "@/config/env";

import type {
  Account,
  AssistantAccess,
  AssistantConnection,
  AssistantLogin,
  AssistantChoice,
  AssistantLive,
  AssistantModel,
  AssistantProvider,
  AssistantThread,
  AssistantThreads,
  AssistantConversation,
  ClaudeState,
  ClaudeSetupAction,
  AssistantAudit,
  AccountCheck,
  AccountCreate,
  AccountUpdate,
  AuthStatus,
  Credentials,
  Job,
  JobDetail,
  JobMetrics,
  JobState,
  JobUpdate,
  LoginSession,
  Me,
  MembershipUpdate,
  Passkey,
  PasskeyOptions,
  Health,
  Preferences,
  PreferencesUpdate,
  PulseEvent,
  PushConfig,
  PushSubscriptionJSON,
  Run,
  SetupInfo,
  SiteStats,
  InviteInfo,
  NewTeamInvite,
  TeamOverview,
} from "./types";

const BASE_URL = `${API_URL}/api`;
export const STREAM_URL = `${BASE_URL}/stream`;

export const assistantStreamUrl = (id: number, provider: AssistantProvider) =>
  `${BASE_URL}/assistants/${id}/stream${query({ provider })}`;
export const claudeStreamUrl = (id: number) => `${BASE_URL}/assistants/${id}/claude/stream`;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "Some fields are invalid.";
  } catch {
    // Non-JSON error body; fall through.
  }
  return `Request failed (${response.status})`;
}

const json = (body: unknown) => JSON.stringify(body);

function query(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined);
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

export interface JobFilters {
  account_id?: number;
  state?: JobState;
}

export const api = {
  claude: {
    state: (account: number) => request<ClaudeState>(`/assistants/${account}/claude/state`),
    login: (account: number) =>
      request<ClaudeState>(`/assistants/${account}/claude/login`, { method: "POST" }),
    setup: (account: number, action: ClaudeSetupAction, code = "") =>
      request<void>(`/assistants/${account}/claude/setup`, {
        method: "POST",
        body: json({ action, code }),
      }),
    stop: (account: number) =>
      request<void>(`/assistants/${account}/claude/stop`, { method: "POST" }),
  },
  assistants: {
    access: () => request<AssistantAccess>("/assistants/access"),
    audit: () => request<AssistantAudit[]>("/assistants/audit"),
    state: (account: number, provider: AssistantProvider) =>
      request<AssistantLive>(`/assistants/${account}/state${query({ provider })}`),
    connect: (account: number, provider: AssistantProvider) =>
      request<AssistantConnection>(`/assistants/${account}/connect${query({ provider })}`, {
        method: "POST",
      }),
    /** Codex's device sign-in; Claude signs in with its own CLI (api.claude.login). */
    login: (account: number) =>
      request<AssistantLogin>(`/assistants/${account}/login`, { method: "POST" }),
    disconnect: (account: number, provider: AssistantProvider) =>
      request<void>(`/assistants/${account}/disconnect${query({ provider })}`, { method: "POST" }),
    threads: (account: number, provider: AssistantProvider, cursor?: string) =>
      request<AssistantThreads>(`/assistants/${account}/threads${query({ provider, cursor })}`),
    history: (account: number, provider: AssistantProvider, id: string) =>
      request<AssistantConversation>(
        `/assistants/${account}/threads/${encodeURIComponent(id)}${query({ provider })}`,
      ),
    create: (account: number, provider: AssistantProvider, work_dir: string) =>
      request<AssistantThread>(`/assistants/${account}/threads${query({ provider })}`, {
        method: "POST",
        body: json({ work_dir, confirmed: true }),
      }),
    resume: (account: number, provider: AssistantProvider, id: string) =>
      request<AssistantThread>(
        `/assistants/${account}/threads/${encodeURIComponent(id)}/resume${query({ provider })}`,
        { method: "POST" },
      ),
    models: (account: number, provider: AssistantProvider) =>
      request<AssistantModel[]>(`/assistants/${account}/models${query({ provider })}`),
    turn: (
      account: number,
      provider: AssistantProvider,
      id: string,
      prompt: string,
      choice: AssistantChoice = {},
    ) =>
      request<void>(
        `/assistants/${account}/threads/${encodeURIComponent(id)}/turn${query({ provider })}`,
        { method: "POST", body: json({ prompt, ...choice }) },
      ),
    interrupt: (account: number, provider: AssistantProvider, id: string) =>
      request<void>(
        `/assistants/${account}/threads/${encodeURIComponent(id)}/interrupt${query({ provider })}`,
        { method: "POST" },
      ),
    decide: (
      account: number,
      provider: AssistantProvider,
      id: string,
      decision: "accept" | "decline",
      answers: Record<string, string[]>,
    ) =>
      request<void>(
        `/assistants/${account}/approvals/${encodeURIComponent(id)}${query({ provider })}`,
        { method: "POST", body: json({ decision, answers }) },
      ),
  },
  auth: {
    reauthenticate: (password: string) =>
      request<void>("/auth/reauth", { method: "POST", body: json({ password }) }),
    status: () => request<AuthStatus>("/auth/status"),
    me: () => request<Me>("/auth/me"),
    setup: (body: Credentials) => request<Me>("/auth/setup", { method: "POST", body: json(body) }),
    signup: (body: Credentials) =>
      request<Me>("/auth/signup", { method: "POST", body: json(body) }),
    login: (body: Credentials) => request<Me>("/auth/login", { method: "POST", body: json(body) }),
    logout: () => request<void>("/auth/logout", { method: "POST" }),
    demo: () => request<Me>("/auth/demo", { method: "POST" }),
    changePassword: (current_password: string, new_password: string) =>
      request<void>("/auth/password", {
        method: "POST",
        body: json({ current_password, new_password }),
      }),
    sessions: () => request<LoginSession[]>("/auth/sessions"),
    revokeOthers: () => request<void>("/auth/sessions/revoke-others", { method: "POST" }),
  },
  passkeys: {
    reauthOptions: () =>
      request<PasskeyOptions<PublicKeyCredentialRequestOptionsJSON>>(
        "/auth/passkeys/reauth/options",
        { method: "POST" },
      ),
    reauthenticate: (challenge_id: string, credential: AuthenticationResponseJSON) =>
      request<void>("/auth/passkeys/reauth/verify", {
        method: "POST",
        body: json({ challenge_id, credential }),
      }),
    list: () => request<Passkey[]>("/auth/passkeys"),
    registerOptions: () =>
      request<PasskeyOptions<PublicKeyCredentialCreationOptionsJSON>>(
        "/auth/passkeys/register/options",
        { method: "POST" },
      ),
    register: (challenge_id: string, credential: RegistrationResponseJSON, name: string) =>
      request<Passkey>("/auth/passkeys/register/verify", {
        method: "POST",
        body: json({ challenge_id, credential, name }),
      }),
    remove: (id: number) => request<void>(`/auth/passkeys/${id}`, { method: "DELETE" }),
    signupOptions: (username: string) =>
      request<PasskeyOptions<PublicKeyCredentialCreationOptionsJSON>>(
        "/auth/passkeys/signup/options",
        { method: "POST", body: json({ username }) },
      ),
    signup: (challenge_id: string, credential: RegistrationResponseJSON, name: string) =>
      request<Me>("/auth/passkeys/signup/verify", {
        method: "POST",
        body: json({ challenge_id, credential, name }),
      }),
    loginOptions: () =>
      request<PasskeyOptions<PublicKeyCredentialRequestOptionsJSON>>(
        "/auth/passkeys/login/options",
        { method: "POST" },
      ),
    login: (challenge_id: string, credential: AuthenticationResponseJSON) =>
      request<Me>("/auth/passkeys/login/verify", {
        method: "POST",
        body: json({ challenge_id, credential }),
      }),
  },
  health: () => request<Health>("/health"),
  siteStats: () => request<SiteStats>("/stats"),
  setup: () => request<SetupInfo>("/setup"),
  accounts: {
    list: () => request<Account[]>("/accounts"),
    create: (body: AccountCreate) =>
      request<Account>("/accounts", { method: "POST", body: json(body) }),
    update: (id: number, body: AccountUpdate) =>
      request<Account>(`/accounts/${id}`, { method: "PATCH", body: json(body) }),
    remove: (id: number) => request<void>(`/accounts/${id}`, { method: "DELETE" }),
    check: (id: number) => request<AccountCheck>(`/accounts/${id}/check`, { method: "POST" }),
    issueAgentToken: (id: number) =>
      request<{ token: string }>(`/accounts/${id}/agent-token`, { method: "POST" }),
    share: (id: number, teamId: number, shared: boolean) =>
      request<void>(`/accounts/${id}/shares/${teamId}`, { method: shared ? "PUT" : "DELETE" }),
  },
  jobs: {
    list: (filters: JobFilters = {}) => request<Job[]>(`/jobs${query({ ...filters })}`),
    get: (id: number) => request<JobDetail>(`/jobs/${id}`),
    metrics: (id: number) => request<JobMetrics>(`/jobs/${id}/metrics`),
    update: (id: number, body: JobUpdate) =>
      request<JobDetail>(`/jobs/${id}`, { method: "PATCH", body: json(body) }),
    share: (id: number, teamId: number, shared: boolean) =>
      request<void>(`/jobs/${id}/shares/${teamId}`, { method: shared ? "PUT" : "DELETE" }),
  },
  runs: {
    list: (arrayId?: string) => request<Run[]>(`/runs${query({ array_id: arrayId })}`),
  },
  events: {
    list: (limit = 50) => request<PulseEvent[]>(`/events${query({ limit })}`),
  },
  preferences: {
    get: () => request<Preferences>("/preferences"),
    update: (body: PreferencesUpdate) =>
      request<Preferences>("/preferences", { method: "PATCH", body: json(body) }),
  },
  teams: {
    overview: () => request<TeamOverview>("/teams"),
    create: (name: string) =>
      request<TeamOverview>("/teams", { method: "POST", body: json({ name }) }),
    rename: (name: string) =>
      request<TeamOverview>("/teams/mine", { method: "PATCH", body: json({ name }) }),
    remove: () => request<void>("/teams/mine", { method: "DELETE" }),
    removeMember: (userId: number) =>
      request<void>(`/teams/mine/members/${userId}`, { method: "DELETE" }),
    invite: () => request<NewTeamInvite>("/teams/mine/invites", { method: "POST" }),
    revokeInvite: (id: number) => request<void>(`/teams/mine/invites/${id}`, { method: "DELETE" }),
    updateMembership: (teamId: number, body: MembershipUpdate) =>
      request<TeamOverview>(`/teams/${teamId}/membership`, { method: "PATCH", body: json(body) }),
    leave: (teamId: number) => request<void>(`/teams/${teamId}/membership`, { method: "DELETE" }),
    inviteInfo: (token: string) =>
      request<InviteInfo>(`/teams/invites/${encodeURIComponent(token)}`),
    accept: (token: string) =>
      request<TeamOverview>(`/teams/invites/${encodeURIComponent(token)}/accept`, {
        method: "POST",
      }),
    signup: (token: string, body: Credentials) =>
      request<Me>(`/teams/invites/${encodeURIComponent(token)}/signup`, {
        method: "POST",
        body: json(body),
      }),
  },
  push: {
    config: () => request<PushConfig>("/push/config"),
    subscribe: (sub: PushSubscriptionJSON) =>
      request<void>("/push/subscriptions", { method: "POST", body: json(sub) }),
    unsubscribe: (endpoint: string) =>
      request<void>("/push/subscriptions", { method: "DELETE", body: json({ endpoint }) }),
    test: () => request<{ delivered: number }>("/push/test", { method: "POST" }),
  },
};
