import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { api } from "@/api/client";
import { useHealth, usePreferences, useSetup, useUpdatePreferences } from "@/api/queries";
import type { EventKind, Monitoring } from "@/api/types";
import { Button } from "@/components/Button";
import { CopyButton } from "@/components/CopyButton";
import { Card, Section } from "@/components/Section";
import { Segmented } from "@/components/Segmented";
import { SettingRow } from "@/components/SettingRow";
import { Toggle } from "@/components/Toggle";
import { usePush } from "@/hooks/use-push";
import { EVENT_LABELS } from "@/lib/labels";
import type { PushStatus } from "@/lib/push";
import { updateUiSettings, useUiSettings, type UiSettings } from "@/lib/ui-settings";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings — Pulse" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  return (
    <div className="space-y-10">
      <Appearance />
      <JobsDisplay />
      <Notifications />
      <MonitoringSettings />
      <ConnectionInfo />
      <InstallHelp />
    </div>
  );
}

// Appearance & display (this device)

function Appearance() {
  const ui = useUiSettings();
  return (
    <Section title="Appearance · this device">
      <Card className="divide-y">
        <SettingRow label="Theme">
          <Segmented<UiSettings["theme"]>
            label="Theme"
            value={ui.theme}
            onChange={(theme) => updateUiSettings({ theme })}
            options={[
              { value: "system", label: "System" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
          />
        </SettingRow>
        <SettingRow label="Density" hint="Compact fits more jobs on screen">
          <Segmented<UiSettings["density"]>
            label="Density"
            value={ui.density}
            onChange={(density) => updateUiSettings({ density })}
            options={[
              { value: "comfortable", label: "Comfortable" },
              { value: "compact", label: "Compact" },
            ]}
          />
        </SettingRow>
        <SettingRow label="Event times" hint="“5m ago” or the time of day">
          <Segmented<UiSettings["timeFormat"]>
            label="Event times"
            value={ui.timeFormat}
            onChange={(timeFormat) => updateUiSettings({ timeFormat })}
            options={[
              { value: "relative", label: "Relative" },
              { value: "clock", label: "Clock" },
            ]}
          />
        </SettingRow>
      </Card>
    </Section>
  );
}

function JobsDisplay() {
  const ui = useUiSettings();
  return (
    <Section title="Jobs list · this device">
      <Card className="divide-y">
        <SettingRow label="Open on" hint="Which jobs the list shows first">
          <Segmented<UiSettings["defaultView"]>
            label="Open on"
            value={ui.defaultView}
            onChange={(defaultView) => updateUiSettings({ defaultView })}
            options={[
              { value: "active", label: "Active" },
              { value: "all", label: "All" },
            ]}
          />
        </SettingRow>
        <SettingRow label="Finished jobs" hint="How far back the All view goes">
          <Segmented<UiSettings["historyHours"]>
            label="Finished jobs"
            value={ui.historyHours}
            onChange={(historyHours) => updateUiSettings({ historyHours })}
            options={[
              { value: 6, label: "6 h" },
              { value: 24, label: "24 h" },
              { value: 48, label: "48 h" },
            ]}
          />
        </SettingRow>
        <SettingRow label="Loss sparklines" hint="Mini training curve on running jobs">
          <Toggle
            label="Loss sparklines"
            checked={ui.showSparklines}
            onChange={(showSparklines) => updateUiSettings({ showSparklines })}
          />
        </SettingRow>
      </Card>
    </Section>
  );
}

// Notifications

const ALERT_HINTS: Record<EventKind, string> = {
  job_started: "Leaves the queue and begins running",
  job_completed: "Finishes successfully",
  job_failed: "Fails, runs out of memory, or times out",
  job_cancelled: "Is cancelled",
  job_time_limit: "Gets close to its time limit",
  job_stalled: "Stops writing output",
  job_nan: "Produces a NaN or infinite loss",
  job_diverging: "Loss climbs well above its best",
  job_plateau: "Loss stops improving",
};

const PUSH_STATUS_TEXT: Record<PushStatus, string> = {
  unsupported: "This browser doesn't support push notifications.",
  "needs-install":
    "On iPhone and iPad, add Pulse to your Home Screen first, then open it from there.",
  denied: "Notifications are blocked. Allow them for this site in your browser settings.",
  off: "Get notified on this device when jobs change state.",
  on: "This device receives notifications.",
};

function Notifications() {
  const push = usePush();
  const { data } = usePreferences();
  const update = useUpdatePreferences();
  const [testResult, setTestResult] = useState<string | null>(null);

  const sendTest = async () => {
    const { delivered } = await api.push.test();
    setTestResult(delivered ? `Sent to ${delivered} device(s).` : "No devices reached.");
  };

  return (
    <Section title="Notifications">
      <div className="space-y-4">
        <Card className="space-y-3 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm">
              {push.status ? PUSH_STATUS_TEXT[push.status] : "Checking notification support…"}
            </p>
            {push.status === "off" && (
              <Button onClick={push.enable} disabled={push.busy || !push.serverEnabled}>
                Enable on this device
              </Button>
            )}
            {push.status === "on" && (
              <div className="flex shrink-0 gap-2">
                <Button variant="ghost" onClick={sendTest}>
                  Send test
                </Button>
                <Button variant="ghost" onClick={push.disable} disabled={push.busy}>
                  Turn off
                </Button>
              </div>
            )}
          </div>
          {!push.serverEnabled && push.status === "off" && (
            <p className="text-xs text-muted-foreground">
              The server has no push keys yet. Run{" "}
              <code className="font-mono">pulse gen-vapid</code> and add the output to{" "}
              <code className="font-mono">backend/.env</code>.
            </p>
          )}
          {push.error && <p className="text-xs text-fail">{push.error}</p>}
          {testResult && <p className="text-xs text-muted-foreground">{testResult}</p>}
        </Card>

        <Card className="divide-y">
          {(Object.keys(EVENT_LABELS) as EventKind[]).map((kind) => (
            <SettingRow key={kind} label={EVENT_LABELS[kind]} hint={ALERT_HINTS[kind]}>
              <Toggle
                label={EVENT_LABELS[kind]}
                checked={data?.alerts[kind] ?? true}
                disabled={!data}
                onChange={(enabled) => update.mutate({ alerts: { [kind]: enabled } })}
              />
            </SettingRow>
          ))}
        </Card>
        <p className="text-xs text-muted-foreground">
          Applies to every account with alerts on. Mute a single account on the Accounts page.
        </p>
      </div>
    </Section>
  );
}

// Monitoring (server-side, applies everywhere)

interface Choice<K extends keyof Monitoring> {
  key: K;
  label: string;
  hint: string;
  options: { value: number; label: string }[];
}

const MONITORING_CHOICES: Choice<keyof Monitoring>[] = [
  {
    key: "live_refresh_seconds",
    label: "Refresh while open",
    hint: "Faster means more Slurm queries on your clusters",
    options: [
      { value: 5, label: "5 s" },
      { value: 10, label: "10 s" },
      { value: 30, label: "30 s" },
      { value: 60, label: "1 min" },
    ],
  },
  {
    key: "idle_refresh_seconds",
    label: "Refresh in background",
    hint: "When no device has Pulse open; sets notification delay",
    options: [
      { value: 60, label: "1 min" },
      { value: 300, label: "5 min" },
      { value: 900, label: "15 min" },
    ],
  },
  {
    key: "stall_minutes",
    label: "Stalled after",
    hint: "No new output for this long triggers an alert",
    options: [
      { value: 10, label: "10 min" },
      { value: 15, label: "15 min" },
      { value: 30, label: "30 min" },
      { value: 60, label: "1 h" },
    ],
  },
  {
    key: "time_limit_warning_percent",
    label: "Time-limit warning at",
    hint: "Share of the job's time limit used",
    options: [
      { value: 80, label: "80%" },
      { value: 90, label: "90%" },
      { value: 95, label: "95%" },
    ],
  },
  {
    key: "diverge_percent",
    label: "Diverging when loss is",
    hint: "Smoothed loss this far above its best",
    options: [
      { value: 25, label: "+25%" },
      { value: 50, label: "+50%" },
      { value: 100, label: "+100%" },
    ],
  },
  {
    key: "plateau_minutes",
    label: "Plateau after",
    hint: "No new best loss for this long",
    options: [
      { value: 30, label: "30 min" },
      { value: 60, label: "1 h" },
      { value: 180, label: "3 h" },
    ],
  },
];

function MonitoringSettings() {
  const { data } = usePreferences();
  const update = useUpdatePreferences();
  return (
    <Section title="Monitoring · all devices">
      <Card className="divide-y">
        {MONITORING_CHOICES.map((choice) => {
          const value = data?.monitoring[choice.key];
          // Show a custom value (set via the API or env) alongside the presets.
          const options =
            value === undefined || choice.options.some((o) => o.value === value)
              ? choice.options
              : [...choice.options, { value, label: String(value) }];
          return (
            <SettingRow key={choice.key} label={choice.label} hint={choice.hint}>
              <Segmented<number>
                label={choice.label}
                value={value ?? -1}
                disabled={!data}
                options={options}
                onChange={(v) => update.mutate({ monitoring: { [choice.key]: v } })}
              />
            </SettingRow>
          );
        })}
      </Card>
    </Section>
  );
}

// Connection & about

function ConnectionInfo() {
  const { data: setup } = useSetup();
  const { data: health } = useHealth();
  const demo = setup?.slurm_backend === "mock";
  return (
    <Section title="Connection">
      <Card className="divide-y">
        <SettingRow
          label="Cluster access"
          hint={
            demo
              ? "Simulated cluster. Set PULSE_SLURM_BACKEND=ssh to use real clusters."
              : "Pulse signs in over SSH; 2FA clusters use the agent."
          }
        >
          <span className="font-mono text-xs text-muted-foreground">
            {setup ? (demo ? "Demo" : "SSH") : "—"}
          </span>
        </SettingRow>
        {setup?.ssh_public_key && (
          <SettingRow
            label="Pulse's SSH key"
            hint="Authorise this on clusters you connect directly"
          >
            <CopyButton text={setup.ssh_public_key} label="Copy key" />
          </SettingRow>
        )}
        <SettingRow label="Version">
          <span className="font-mono text-xs text-muted-foreground">
            {health ? `Pulse ${health.version}` : "—"}
          </span>
        </SettingRow>
      </Card>
    </Section>
  );
}

function InstallHelp() {
  return (
    <Section title="Install on your phone">
      <Card className="space-y-2 p-4 text-sm text-muted-foreground">
        <p>
          <span className="text-foreground">iPhone / iPad</span>: open in Safari, tap Share, then
          “Add to Home Screen”.
        </p>
        <p>
          <span className="text-foreground">Android</span>: open in Chrome, tap ⋮, then “Install
          app”.
        </p>
      </Card>
    </Section>
  );
}
