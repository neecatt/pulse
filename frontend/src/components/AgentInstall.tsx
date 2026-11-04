import { agentInstallCommand, isLocalOrigin } from "@/lib/agent";

import { CopyButton } from "./CopyButton";

/** Copy-paste instructions for installing the agent with a freshly issued token. */
export function AgentInstall({ token }: { token: string }) {
  const command = agentInstallCommand(token);
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        Sign in to the cluster's login node as usual (with your 2FA) and run this once. It needs
        only Python 3, installs nothing system-wide, and reports your jobs every few seconds while
        you're watching.
      </p>
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 truncate rounded-md bg-muted/60 px-3 py-2 font-mono text-xs">
          {command}
        </code>
        <CopyButton text={command} />
      </div>
      {isLocalOrigin() && (
        <p className="text-xs text-pend">
          This address is only reachable from this computer. Open Pulse through an address the
          cluster can reach, then copy the command again.
        </p>
      )}
    </div>
  );
}
