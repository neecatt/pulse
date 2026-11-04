const API_ORIGIN = import.meta.env["VITE_API_URL"] ?? window.location.origin;

/** One command that downloads, verifies and schedules the login-node agent. */
export function agentInstallCommand(token: string): string {
  return (
    `curl -fsSL ${API_ORIGIN}/api/agent/script -o ~/.pulse-agent.py && ` +
    `python3 ~/.pulse-agent.py install ${API_ORIGIN} ${token}`
  );
}

/** Agents run on the cluster, so they can't reach a Pulse that only listens locally. */
export function isLocalOrigin(): boolean {
  const host = new URL(API_ORIGIN).hostname;
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}
