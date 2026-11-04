import type { JobDetail, NodeStats } from "@/api/types";
import { RUN_COLORS } from "@/config/constants";
import { formatPercent } from "@/lib/format";

import { MetricChart, type ChartSeries } from "./MetricChart";
import { Card } from "./Section";

const CHARTS = [
  { key: "cpu", title: "CPU" },
  { key: "mem", title: "Memory" },
  { key: "gpu", title: "GPU utilisation" },
  { key: "gpu_mem", title: "GPU memory" },
] as const;

/** Per-node CPU, memory and GPU usage over time, plus a live per-GPU grid. */
export function NodeUsage({ job }: { job: JobDetail }) {
  const nodes = Object.keys(job.node_stats).sort();
  const color = (i: number) => RUN_COLORS[i % RUN_COLORS.length] ?? "var(--foreground)";
  const charts = CHARTS.map((chart) => ({
    ...chart,
    series: nodes
      .map((node, i): ChartSeries => ({
        key: node,
        label: node,
        color: color(i),
        points: (job.series[`sys/${node}/${chart.key}`] ?? []).map((p) => ({
          x: Date.parse(p.t),
          y: p.v,
        })),
      }))
      .filter((s) => s.points.length > 0),
  })).filter((chart) => chart.series.length > 0);

  if (nodes.length === 0) return null;
  const hasGpus = nodes.some((n) => (job.node_stats[n]?.gpus.length ?? 0) > 0);

  return (
    <div className="space-y-4">
      {nodes.length > 1 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs">
          {nodes.map((node, i) => (
            <span key={node} className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: color(i) }} />
              {node}
            </span>
          ))}
        </div>
      )}
      {hasGpus && <GpuGrid nodes={nodes} stats={job.node_stats} />}
      <div className="grid gap-4 lg:grid-cols-2">
        {charts.map((chart) => (
          <Card key={chart.key} className="p-4">
            <div className="mb-3 font-mono text-xs">{chart.title}</div>
            <MetricChart xAxis="time" domain={[0, 100]} unit="%" series={chart.series} />
          </Card>
        ))}
      </div>
    </div>
  );
}

/** Latest utilisation of every GPU, one row per node. */
function GpuGrid({ nodes, stats }: { nodes: string[]; stats: Record<string, NodeStats> }) {
  return (
    <Card className="space-y-2 p-4">
      <div className="flex items-baseline justify-between font-mono text-xs">
        <span>GPUs now</span>
        <span className="text-muted-foreground">utilisation · memory</span>
      </div>
      {nodes.map((node) => {
        const s = stats[node];
        if (!s?.gpus.length) return null;
        return (
          <div key={node} className="flex items-center gap-3">
            <span className="w-16 shrink-0 truncate font-mono text-[11px] text-muted-foreground">
              {node}
            </span>
            <div className="flex flex-1 flex-wrap gap-1">
              {s.gpus.map((gpu, i) => (
                <span
                  key={i}
                  title={`${node} GPU ${i}: ${formatPercent(gpu.util)} util, ${formatPercent(gpu.mem)} memory`}
                  className="grid h-9 min-w-12 flex-1 place-items-center rounded font-mono text-[10px] leading-tight"
                  style={{
                    background: `color-mix(in oklch, var(--run) ${Math.round(gpu.util * 0.6)}%, var(--muted))`,
                  }}
                >
                  <span>{formatPercent(gpu.util)}</span>
                  <span className="opacity-60">{formatPercent(gpu.mem)}</span>
                </span>
              ))}
            </div>
            <span className="hidden w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground sm:block">
              cpu {formatPercent(s.cpu)}
            </span>
          </div>
        );
      })}
    </Card>
  );
}
