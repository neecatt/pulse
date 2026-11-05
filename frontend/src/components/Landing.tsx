import { ArrowLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useTryDemo } from "@/api/queries";
import type { AuthStatus, JobState } from "@/api/types";
import { cn } from "@/lib/utils";

import { AccountDot } from "./AccountDot";
import { AuthPanel } from "./AuthScreen";
import { Button } from "./Button";
import { Card } from "./Section";
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
      <header className="pt-safe mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-2 font-mono text-sm font-medium">
          <span className="size-2 animate-pulse rounded-full bg-run" /> pulse
        </div>
        <Button variant="ghost" onClick={() => setPanel("login")}>
          Sign in
        </Button>
      </header>

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
          {FEATURES.map(([title, text]) => (
            <div key={title} className="bg-surface p-5">
              <h2 className="text-sm font-medium">{title}</h2>
              <p className="mt-1.5 text-sm text-muted-foreground">{text}</p>
            </div>
          ))}
        </section>

        <footer className="mt-12 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>Your accounts and jobs are private to you.</span>
          <span>
            Open source. Run your own:{" "}
            <code className="font-mono whitespace-nowrap text-foreground">
              docker run neecat/pulse
            </code>
          </span>
        </footer>
      </main>
    </div>
  );
}

/** "?start=signup" opens the sign-up form (the demo's "Create your account" links here). */
function initialPanel(): Panel {
  const start = new URLSearchParams(window.location.search).get("start");
  return start === "signup" || start === "login" ? start : null;
}

const FEATURES: [string, string][] = [
  ["Live, not refreshed", "Jobs change on screen the moment Slurm reports them."],
  [
    "Curves without code changes",
    "Reads TensorBoard files, metric JSONL or CSV, and the loss lines in your logs.",
  ],
  [
    "Alerts on your phone",
    "Started, finished, failed, stalled, NaN loss, near the time limit. Add Pulse to your home screen.",
  ],
  [
    "Every cluster in one list",
    "Add a login as jdoe@lumi.csc.fi. Pulse makes your SSH key and checks the connection.",
  ],
  [
    "Works behind 2FA",
    "Where outside SSH isn't allowed, a small agent on the login node reports in instead.",
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
