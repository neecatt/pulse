import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { api } from "@/api/client";
import { usePreferences, useUpdatePreferences } from "@/api/queries";
import type { EventKind } from "@/api/types";
import { Button } from "@/components/Button";
import { Card, Section } from "@/components/Section";
import { Toggle } from "@/components/Toggle";
import { usePush } from "@/hooks/use-push";
import { EVENT_LABELS } from "@/lib/labels";
import type { PushStatus } from "@/lib/push";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Alerts — Pulse" }] }),
  component: SettingsPage,
});

const ALERT_HINTS: Record<EventKind, string> = {
  job_started: "Leaves the queue and begins running",
  job_completed: "Finishes successfully",
  job_failed: "Fails, runs out of memory, or times out",
  job_cancelled: "Is cancelled",
  job_time_limit: "Reaches 90% of its time limit",
  job_stalled: "Writes no output for 15 minutes",
};

function SettingsPage() {
  return (
    <div className="space-y-10">
      <DevicePush />
      <AlertPreferences />
      <InstallHelp />
    </div>
  );
}

const STATUS_TEXT: Record<PushStatus, string> = {
  unsupported: "This browser doesn't support push notifications.",
  "needs-install":
    "On iPhone and iPad, add Pulse to your Home Screen first, then open it from there.",
  denied: "Notifications are blocked. Allow them for this site in your browser settings.",
  off: "Get notified on this device when jobs change state.",
  on: "This device receives notifications.",
};

function DevicePush() {
  const push = usePush();
  const [testResult, setTestResult] = useState<string | null>(null);

  const sendTest = async () => {
    const { delivered } = await api.push.test();
    setTestResult(delivered ? `Sent to ${delivered} device(s).` : "No devices reached.");
  };

  return (
    <Section title="This device">
      <Card className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm">
            {push.status ? STATUS_TEXT[push.status] : "Checking notification support…"}
          </p>
          {push.status === "off" && (
            <Button onClick={push.enable} disabled={push.busy || !push.serverEnabled}>
              Enable
            </Button>
          )}
          {push.status === "on" && (
            <div className="flex shrink-0 gap-2">
              <Button variant="ghost" onClick={sendTest}>
                Test
              </Button>
              <Button variant="ghost" onClick={push.disable} disabled={push.busy}>
                Disable
              </Button>
            </div>
          )}
        </div>
        {!push.serverEnabled && push.status === "off" && (
          <p className="text-xs text-muted-foreground">
            The server has no VAPID keys configured — run{" "}
            <code className="font-mono">pulse gen-vapid</code> to enable push.
          </p>
        )}
        {push.error && <p className="text-xs text-fail">{push.error}</p>}
        {testResult && <p className="text-xs text-muted-foreground">{testResult}</p>}
      </Card>
    </Section>
  );
}

function AlertPreferences() {
  const { data } = usePreferences();
  const update = useUpdatePreferences();

  return (
    <Section title="Notify me when a job…">
      <Card className="divide-y">
        {(Object.keys(EVENT_LABELS) as EventKind[]).map((kind) => (
          <div key={kind} className="flex items-center justify-between gap-4 p-4">
            <div>
              <div className="text-sm">{EVENT_LABELS[kind]}</div>
              <div className="text-xs text-muted-foreground">{ALERT_HINTS[kind]}</div>
            </div>
            <Toggle
              label={EVENT_LABELS[kind]}
              checked={data?.alerts[kind] ?? true}
              disabled={!data}
              onChange={(enabled) =>
                data && update.mutate({ alerts: { ...data.alerts, [kind]: enabled } })
              }
            />
          </div>
        ))}
      </Card>
      <p className="mt-2 text-xs text-muted-foreground">
        Applies to every account with alerts turned on.
      </p>
    </Section>
  );
}

function InstallHelp() {
  return (
    <Section title="Install on your phone">
      <Card className="space-y-2 p-4 text-sm text-muted-foreground">
        <p>
          <span className="text-foreground">iPhone / iPad</span> — open in Safari, tap Share, then
          “Add to Home Screen”.
        </p>
        <p>
          <span className="text-foreground">Android</span> — open in Chrome, tap ⋮, then “Install
          app”.
        </p>
      </Card>
    </Section>
  );
}
