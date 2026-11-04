import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { accounts, jobs, events, accountOf } from "@/lib/mock";
import { StateDot, Spark, Bar } from "@/components/ui-bits";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Pulse — Slurm jobs across all your HPC accounts" },
      { name: "description", content: "Monitor Slurm jobs and training runs across multiple HPC accounts, with alerts on start and stop." },
      { property: "og:title", content: "Pulse — HPC job monitor" },
      { property: "og:description", content: "All your Slurm jobs, every cluster, one glance." },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const [filter, setFilter] = useState<string>("all");
  const list = jobs.filter((j) => filter === "all" || j.accountId === filter);
  const running = jobs.filter((j) => j.state === "RUNNING");
  const gpus = running.reduce((s, j) => s + j.gpus, 0);
  const util = Math.round(running.reduce((s, j) => s + j.gpuUtil, 0) / (running.length || 1));

  const stats = [
    { k: "Running", v: running.length },
    { k: "Pending", v: jobs.filter((j) => j.state === "PENDING").length },
    { k: "GPUs in use", v: gpus },
    { k: "Avg GPU util", v: `${util}%` },
  ];

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border md:grid-cols-4">
        {stats.map((s) => (
          <div key={s.k} className="bg-background p-4">
            <div className="text-xs text-muted-foreground">{s.k}</div>
            <div className="mt-1 font-mono text-2xl">{s.v}</div>
          </div>
        ))}
      </section>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {[{ id: "all", label: "All accounts" }, ...accounts.map((a) => ({ id: a.id, label: `${a.user}@${a.cluster}` }))].map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`shrink-0 rounded-full border px-3 py-1 text-xs transition-colors ${filter === f.id ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        <section className="divide-y rounded-lg border">
          {list.map((j) => {
            const a = accountOf(j.accountId);
            return (
              <Link key={j.id} to="/jobs/$id" params={{ id: j.id }} className="grid grid-cols-[1fr_auto] items-center gap-4 p-4 transition-colors hover:bg-muted/50 md:grid-cols-[1fr_160px_120px]">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="size-2 shrink-0 rounded-sm" style={{ background: a.color }} />
                    <span className="truncate font-medium">{j.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">#{j.id}</span>
                  </div>
                  <div className="mt-1 font-mono text-xs text-muted-foreground">
                    {a.cluster} · {j.partition} · {j.nodes}n/{j.gpus}g · {j.elapsed}
                  </div>
                  <div className="mt-2 md:hidden"><Bar value={j.progress} /></div>
                </div>
                <div className="hidden text-muted-foreground md:block"><Spark data={j.loss} /></div>
                <div className="text-right"><StateDot state={j.state} /></div>
              </Link>
            );
          })}
        </section>

        <aside>
          <h2 className="mb-3 text-xs uppercase tracking-wider text-muted-foreground">Recent events</h2>
          <ul className="space-y-3">
            {events.map((e, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="mt-1.5 size-2 shrink-0 rounded-sm" style={{ background: accountOf(e.accountId).color }} />
                <div className="flex-1">
                  <div>{e.text}</div>
                  <div className="mt-0.5 flex gap-2"><StateDot state={e.kind} /><span className="font-mono text-[11px] text-muted-foreground">{e.t} ago</span></div>
                </div>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
