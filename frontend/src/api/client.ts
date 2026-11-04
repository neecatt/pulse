import type {
  Account,
  AccountCheck,
  AccountCreate,
  AccountUpdate,
  Job,
  JobDetail,
  JobState,
  Preferences,
  PulseEvent,
  PushConfig,
  PushSubscriptionJSON,
  SetupInfo,
} from "./types";

const BASE_URL = `${import.meta.env["VITE_API_URL"] ?? ""}/api`;
export const STREAM_URL = `${BASE_URL}/stream`;

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
  },
  jobs: {
    list: (filters: JobFilters = {}) => request<Job[]>(`/jobs${query({ ...filters })}`),
    get: (id: number) => request<JobDetail>(`/jobs/${id}`),
  },
  events: {
    list: (limit = 50) => request<PulseEvent[]>(`/events${query({ limit })}`),
  },
  preferences: {
    get: () => request<Preferences>("/preferences"),
    update: (body: Preferences) =>
      request<Preferences>("/preferences", { method: "PUT", body: json(body) }),
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
