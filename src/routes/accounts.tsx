import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { accounts as initial, jobs } from "@/lib/mock";

export const Route = createFileRoute("/accounts")({
  head: () => ({
    meta: [
      { title: "Accounts & alerts — Pulse" },
      { name: "description", content: "Connect multiple HPC cluster accounts and choose which ones send job alerts." },
      { property: "og:title", content: "Accounts & alerts — Pulse" },
      { property: "og:description", content: "Manage HPC accounts and push alerts." },
    ],
  }),
  component: Accounts,
});

const alertTypes = ["Job started", "Job finished", "Job failed", "Training stalled (no log output 15 min)", "Near time limit"];

function Accounts() {
  const [list, setList] = useState(initial);
  const [alerts, setAlerts] = useState<Record<string, boolean>>(Object.fromEntries(alertTypes.map((a) => [a, true])));

  return (
    <div className="space-y-10">
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-lg font-medium">Accounts</h1>
          <button className="rounded-md bg-foreground px-3 py-1.5 text-xs text-background">+ Add account</button>
        </div>
        <ul className="divide-y rounded-lg border">
          {list.map((a) => (
            <li key={a.id} className="flex items-center gap-3 p-4">
              <span className="size-2.5 rounded-sm" style={{ background: a.color }} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{a.user}@{a.cluster}</div>
                <div className="truncate font-mono text-xs text-muted-foreground">{a.host} · {jobs.filter((j) => j.accountId === a.id).length} jobs</div>
              </div>
              <Toggle on={a.notify} onChange={(v) => setList(list.map((x) => (x.id === a.id ? { ...x, notify: v } : x)))} label="Alerts" />
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">Accounts connect via SSH key or a lightweight agent on the login node.</p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Push notifications</h2>
        <ul className="divide-y rounded-lg border">
          {alertTypes.map((t) => (
            <li key={t} className="flex items-center justify-between p-4 text-sm">
              {t}
              <Toggle on={!!alerts[t]} onChange={(v) => setAlerts({ ...alerts, [t]: v })} />
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border p-4 text-sm text-muted-foreground">
        <div className="mb-1 font-medium text-foreground">Install on your phone</div>
        iPhone: Share → Add to Home Screen. Android: menu → Install app.
      </section>
    </div>
  );
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button onClick={() => onChange(!on)} aria-label={label ?? "toggle"} aria-pressed={on}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${on ? "bg-run" : "bg-muted"}`}>
      <span className={`absolute top-0.5 size-4 rounded-full bg-background transition-all ${on ? "left-[18px]" : "left-0.5"}`} />
    </button>
  );
}
