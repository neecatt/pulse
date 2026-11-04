import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { jobs, accountOf } from "@/lib/mock";
import { StateDot, Spark, Bar } from "@/components/ui-bits";

export const Route = createFileRoute("/jobs/$id")({
  loader: ({ params }) => {
    const job = jobs.find((j) => j.id === params.id);
    if (!job) throw notFound();
    return job;
  },
  head: ({ loaderData }) => ({
    meta: [
      { title: loaderData ? `${loaderData.name} #${loaderData.id} — Pulse` : "Job — Pulse" },
      { name: "description", content: "Slurm job details, training progress and resource usage." },
      { property: "og:title", content: loaderData ? `${loaderData.name} — Pulse` : "Job — Pulse" },
      { property: "og:description", content: "Slurm job details and training progress." },
    ],
  }),
  component: JobPage,
});

function JobPage() {
  const j = Route.useLoaderData();
  const a = accountOf(j.accountId);
  const meta = [
    ["Account", `${a.user}@${a.cluster}`], ["Partition", j.partition], ["Nodes", j.nodes], ["GPUs", j.gpus],
    ["Elapsed", j.elapsed], ["Time limit", j.limit], ["Epoch", j.epoch ?? "—"], ["Last loss", j.loss.at(-1) ?? "—"],
  ];
  return (
    <div className="space-y-8">
      <Link to="/" className="text-xs text-muted-foreground hover:text-foreground">← All jobs</Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="font-mono text-xs text-muted-foreground">#{j.id}</div>
          <h1 className="text-2xl font-medium tracking-tight">{j.name}</h1>
        </div>
        <StateDot state={j.state} />
      </header>

      <div className="space-y-1.5">
        <div className="flex justify-between font-mono text-xs text-muted-foreground"><span>Progress</span><span>{Math.round(j.progress * 100)}%</span></div>
        <Bar value={j.progress} />
      </div>

      <section className="rounded-lg border p-4">
        <div className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">Training loss</div>
        <Spark data={j.loss} className="!h-40 text-run" />
      </section>

      <section className="grid grid-cols-2 gap-4">
        {[["GPU util", j.gpuUtil], ["GPU memory", j.memUtil]].map(([k, v]) => (
          <div key={k} className="rounded-lg border p-4">
            <div className="text-xs text-muted-foreground">{k}</div>
            <div className="my-2 font-mono text-2xl">{v}%</div>
            <Bar value={(v as number) / 100} />
          </div>
        ))}
      </section>

      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border md:grid-cols-4">
        {meta.map(([k, v]) => (
          <div key={k} className="bg-background p-3">
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="mt-0.5 font-mono text-sm">{v}</dd>
          </div>
        ))}
      </dl>

      <section className="rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-relaxed text-muted-foreground">
        <div className="mb-2 uppercase tracking-wider">stdout · tail</div>
        <div>[step 18400] loss={j.loss.at(-1) ?? "-"} lr=2.0e-5 tok/s=41.2k</div>
        <div>[step 18450] loss={j.loss.at(-2) ?? "-"} lr=2.0e-5 tok/s=41.0k</div>
        <div>[ckpt] saved checkpoint-18000</div>
      </section>
    </div>
  );
}
