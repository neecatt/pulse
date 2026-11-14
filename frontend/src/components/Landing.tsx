import { Link } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useTryDemo } from "@/api/queries";
import type { AuthStatus, JobState } from "@/api/types";
import { cn } from "@/lib/utils";

import { AccountDot } from "./AccountDot";
import { AuthPanel } from "./AuthScreen";
import { Button } from "./Button";
import { CopyButton } from "./CopyButton";
import { Card } from "./Section";
import { GitHubLink, SiteHeader } from "./SiteHeader";
import { Sparkline } from "./Sparkline";
import { StateBadge } from "./StateBadge";

type Panel = "login" | "signup" | null;

/** The public site's front page (PULSE_DEMO): try the demo, sign up or sign in. */
export function Landing({ status }: { status: AuthStatus }) {
  const demo = useTryDemo();
  const [panel, setPanel] = useState<Panel>(initialPanel);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = "Pulse — your Slurm jobs, live";
    // "?start=…" has done its job; don't carry it into the app after signing in.
    if (window.location.search) window.history.replaceState(null, "", window.location.pathname);
  }, []);

  useEffect(() => {
    if (panel) panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [panel]);

  return (
    <div className="min-h-dvh">
      <SiteHeader>
        <Button variant="ghost" onClick={() => setPanel("login")}>
          Sign in
        </Button>
      </SiteHeader>

      <main className="mx-auto max-w-6xl px-4 pb-16">
        <section className="grid grid-cols-1 items-center gap-10 py-10 md:grid-cols-2 md:py-20">
          {/* On phones an open sign-in or sign-up form takes the hero's place, so
              it's on screen at once instead of below the fold. */}
          <div className={cn("space-y-6", panel && "hidden md:block")}>
            <p className="font-mono text-xs tracking-wider text-muted-foreground uppercase">
              Slurm job monitoring
            </p>
            <h1 className="text-4xl font-medium tracking-tight text-balance md:text-5xl">
              Your Slurm jobs, live, on every device.
            </h1>
            <p className="max-w-md text-muted-foreground">
              Pulse follows every job across all your HPC accounts, plots your training curves and
              tells you the moment something starts, finishes or goes wrong. It connects over SSH,
              and your code stays as it is.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                className="h-10 flex-1 px-4 text-sm whitespace-nowrap sm:flex-none"
                disabled={demo.isPending}
                onClick={() => demo.mutate()}
              >
                {demo.isPending ? "Starting the demo…" : "Try the demo"}
              </Button>
              {status.signup_allowed && (
                <Button
                  variant="ghost"
                  className="h-10 flex-1 px-4 text-sm whitespace-nowrap sm:flex-none"
                  onClick={() => setPanel("signup")}
                >
                  Create your account
                </Button>
              )}
            </div>
            {demo.error ? (
              <p className="text-xs text-fail">{demo.error.message}</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                The demo runs on simulated clusters: no sign-up, and it's deleted after a day.
              </p>
            )}
          </div>

          <div ref={panelRef} className="scroll-mt-6">
            {panel ? (
              <Card className="relative p-6 sm:p-8">
                <button
                  type="button"
                  onClick={() => setPanel(null)}
                  aria-label="Back"
                  className="absolute top-4 left-4 text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="size-4" />
                </button>
                <AuthPanel key={panel} status={status} start={panel} />
              </Card>
            ) : (
              <Preview />
            )}
          </div>
        </section>

        <section className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([title, text, guide]) => (
            <div key={title} className="bg-surface p-5">
              <h2 className="text-sm font-medium">{title}</h2>
              <p className="mt-1.5 text-sm text-muted-foreground">{text}</p>
              {guide && (
                <Link
                  to="/docs/$slug"
                  params={{ slug: guide.slug }}
                  hash={guide.hash}
                  className="mt-2 inline-flex items-center gap-1 text-xs font-medium hover:underline"
                >
                  {guide.label} <ArrowRight className="size-3" />
                </Link>
              )}
            </div>
          ))}
        </section>

        <SelfHost />

        <footer className="mt-12 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>Your accounts and jobs are private to you.</span>
          <span className="flex flex-wrap items-center gap-4">
            <Link
              to="/docs/$slug"
              params={{ slug: "self-hosting" }}
              className="hover:text-foreground"
            >
              Self-hosting guide
            </Link>
            <GitHubLink label="Source on GitHub" />
          </span>
        </footer>
      </main>
    </div>
  );
}

const TRY_LOCALLY = "docker run --rm -p 8000:8000 \\\n  -e PULSE_SLURM_BACKEND=mock neecat/pulse";

/** Open source: how to run your own, with the guide and the code one click away. */
function SelfHost() {
  return (
    <section className="mt-12 grid items-center gap-8 rounded-lg border bg-surface p-6 md:grid-cols-2 md:p-10">
      <div className="space-y-4">
        <p className="font-mono text-xs tracking-wider text-muted-foreground uppercase">
          Open source · MIT
        </p>
        <h2 className="text-2xl font-medium tracking-tight text-balance">
          Run Pulse on your own server.
        </h2>
        <p className="max-w-md text-sm text-muted-foreground">
          One container and one volume, with no database to run. Put it behind Caddy, Tailscale or a
          platform like Railway, and your SSH keys and job data stay on your machine.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/docs/$slug"
            params={{ slug: "self-hosting" }}
            className="inline-flex h-10 items-center gap-1.5 rounded-md bg-foreground px-4 text-sm font-medium text-background hover:bg-foreground/90"
          >
            Read the self-hosting guide <ArrowRight className="size-4" />
          </Link>
          <GitHubLink
            label="View on GitHub"
            className="h-10 border px-4 text-sm font-medium text-foreground hover:bg-muted"
          />
        </div>
      </div>
      <div className="min-w-0 space-y-2">
        <p className="text-xs text-muted-foreground">Try it locally with a simulated cluster:</p>
        <div className="flex items-start gap-2 rounded-lg border bg-background p-3">
          <pre className="min-w-0 flex-1 overflow-x-auto font-mono text-[13px] leading-6">
            {TRY_LOCALLY}
          </pre>
          <CopyButton text={TRY_LOCALLY} />
        </div>
        <p className="text-xs text-muted-foreground">
          Then open <span className="font-mono">localhost:8000</span>.
        </p>
      </div>
    </section>
  );
}

/** "?start=signup" opens the sign-up form (the demo's "Create your account" links here). */
function initialPanel(): Panel {
  const start = new URLSearchParams(window.location.search).get("start");
  return start === "signup" || start === "login" ? start : null;
}

type Guide = { label: string; slug: string; hash: string };

const FEATURES: [string, string, Guide?][] = [
  ["Live, not refreshed", "Jobs change on screen the moment Slurm reports them."],
  [
    "Curves without code changes",
    "Reads TensorBoard files, metric JSONL or CSV, and the loss lines in your logs.",
  ],
  [
    "Alerts on your phone",
    "Started, finished, failed, stalled, NaN loss, near the time limit. Add Pulse to your home screen.",
    { label: "Turning on alerts", slug: "self-hosting", hash: "push-notifications" },
  ],
  [
    "Every cluster in one list",
    "Add a login as jdoe@lumi.csc.fi. Pulse makes your SSH key and checks the connection.",
  ],
  [
    "Works behind 2FA",
    "Where outside SSH isn't allowed, a small agent on the login node reports in instead.",
    { label: "Ways to connect", slug: "self-hosting", hash: "connecting-clusters" },
  ],
  ["Share with your lab", "Your team follows the runs you choose, live and read-only."],
];

/** A still of the jobs list, drawn with the app's own components. */
function Preview() {
  return (
    <div aria-hidden>
      <Card className="divide-y">
        {PREVIEW.map((job) => (
          <div key={job.name} className="flex items-center gap-4 px-4 py-3">
            <AccountDot color={job.account} className="size-2" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{job.name}</div>
              <div className="truncate font-mono text-[11px] text-muted-foreground">{job.meta}</div>
            </div>
            <Sparkline
              data={job.curve}
              className={`hidden w-24 sm:block ${job.state === "FAILED" ? "text-fail" : "text-run"}`}
            />
            <StateBadge state={job.state} className="shrink-0 justify-end sm:w-24" />
          </div>
        ))}
      </Card>
      {/* A push notification arriving over the app, drawn the way phones show them. */}
      <div className="relative z-10 mx-3 -mt-3 flex items-start gap-3 rounded-2xl border bg-surface/90 p-3 shadow-lg backdrop-blur sm:mx-8">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-foreground">
          <span className="size-2.5 rounded-full bg-run" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex justify-between gap-3 text-[11px] text-muted-foreground">
            <span className="tracking-wider uppercase">Pulse</span>
            <span>now</span>
          </div>
          <div className="text-sm font-medium">ana · LUMI</div>
          <div className="text-sm text-muted-foreground">mixtral-eval failed — OUT_OF_MEMORY</div>
        </div>
      </div>
    </div>
  );
}

function curve(length: number, rate: number, wobble = 0.03): number[] {
  return Array.from(
    { length },
    (_, i) => 0.3 + 2.2 * Math.exp(-i / rate) + wobble * Math.sin(i * 1.7),
  );
}

const PREVIEW: { name: string; meta: string; account: number; state: JobState; curve: number[] }[] =
  [
    {
      name: "llama-7b-sft",
      meta: "LUMI · gpu · 8n/32g · 14h 02m · ep 7/10",
      account: 0,
      state: "RUNNING",
      curve: curve(28, 9),
    },
    {
      name: "vit-l-pretrain",
      meta: "Leonardo · gpu · 4n/16g · 3h 10m · ep 4/10",
      account: 1,
      state: "RUNNING",
      curve: curve(20, 6, 0.05),
    },
    {
      name: "mixtral-eval",
      meta: "LUMI · gpu-small · 1n/8g · 43m",
      account: 0,
      state: "FAILED",
      curve: [...curve(10, 5), 1.2, 2.4, 3.1],
    },
    {
      name: "diffusion-ft",
      meta: "Leonardo · gpu · 2n/8g · queued 12m",
      account: 1,
      state: "PENDING",
      curve: [],
    },
  ];
