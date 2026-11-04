# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project

**Pulse** is a minimal HPC monitoring app for Slurm users. It is a responsive web
app that installs to the iOS/Android home screen as a PWA. A user links one or
more HPC accounts (cluster + username), sees every job across all of them in one
place, follows training progress, and gets push notifications when jobs start,
finish, fail, stall, or approach their time limit.

## Product principles (non-negotiable)

Every change is judged against these three rules. If a change breaks one,
redesign it, or raise the trade-off explicitly in the PR.

1. **Lightweight and easy to run.** One process (`make start`), SQLite, no
   external services (no Redis, brokers, Docker or cloud dependencies) unless
   there's no alternative. Add a dependency only when it removes more
   complexity than it adds. Be gentle on clusters: reuse SSH connections, keep
   Slurm calls few and cheap, and throttle anything that creates job steps.
2. **Fast and real-time.** Users see job changes as they happen. The server
   pushes updates over `/api/stream` (Server-Sent Events) right after each
   poll; the UI never waits on a timer to show new data. Polling is adaptive:
   fast while someone is watching, slow otherwise. Pages render from cached
   data immediately and refresh in place, with no full-page spinners.
3. **Simple and intuitive controls.** Anything a user does takes the fewest
   steps possible and needs no documentation:
   - Accept input the way people already write it (an account is just
     `jdoe@lumi.csc.fi`); derive everything else, and make extra fields optional.
   - Do the work for the user (generate keys, pin host keys, test the
     connection immediately) and show progress and results in place.
   - Errors say what went wrong and what to do next, in plain language: never a
     raw stack trace, errno or HTTP code.
   - Sensible defaults everywhere; settings exist only when users genuinely
     differ. No modals-in-modals, wizards or multi-page forms.

## Layout

```
.
├── backend/     Python 3.12 · FastAPI · SQLAlchemy (async) · Web Push
├── frontend/    TypeScript · React 19 · Vite · TanStack Router/Query · Tailwind v4
└── docs/        progress.md (running log), architecture.md
```

The two packages are independent: each has its own tooling and dependencies, and
they talk only over the HTTP API under `/api`. Don't import across them.

## Commands

| Task       | Backend (`cd backend`)                                       | Frontend (`cd frontend`)               |
| ---------- | ------------------------------------------------------------ | -------------------------------------- |
| Install    | `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` | `bun install`                          |
| Dev server | `.venv/bin/uvicorn pulse.main:app --reload`                  | `bun run dev` (proxies `/api` → :8000) |
| Tests      | `.venv/bin/pytest`                                           | `bun run test`                         |
| Lint       | `.venv/bin/ruff check . && .venv/bin/ruff format --check .`  | `bun run lint`                         |
| Types      | `.venv/bin/mypy src`                                         | `bun run typecheck`                    |

Run lint, types, and tests for every package you touched before committing.

## Engineering rules

- **Git workflow.** Remote: `github.com/neecatt/hpc-monitoring-app` (private).
  `main` stays releasable and is only changed through pull requests. Work on a
  short-lived branch named `<type>/<short-topic>` (e.g. `feat/push-retention`),
  push it, open a PR with `gh pr create`, and merge with a merge commit once
  checks pass. Never commit straight to `main`, never force-push or rewrite
  pushed history.
- **Conventional Commits.** `type(scope): summary` in the imperative, ≤72 chars.
  Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`,
  `chore`, `style`. Scopes: `backend`, `frontend`, `docs`, `repo`. One logical
  change per commit; explain the _why_ in the body when it isn't obvious.
- **Keep it small.** No speculative abstractions, no unused dependencies, no
  dead code. Prefer deleting to commenting-out.
- **Typed boundaries.** Backend request/response bodies are Pydantic schemas in
  `pulse/schemas.py`; frontend mirrors them in `src/api/types.ts`. Change both in
  the same branch.
- **Secrets.** Never commit `.env`, SSH keys, or VAPID private keys. Config comes
  from environment variables (`PULSE_*`, see `backend/.env.example`).
- **Tests.** Pure logic (Slurm parsing, job-state diffing) gets unit tests. New
  endpoints get an API test.
- **Docs.** Append to `docs/progress.md` when you finish a meaningful piece of
  work, and update this file when commands, layout, or conventions change.

## Backend notes

- `pulse/slurm/` is the only code that knows about Slurm. `SlurmClient` is the
  interface; `MockSlurmClient` simulates a cluster (default, `PULSE_SLURM_BACKEND=mock`),
  `SshSlurmClient` runs `sacct --json` over SSH (`PULSE_SLURM_BACKEND=ssh`).
- `pulse/services/poller.py` polls each account, stores snapshots, turns state
  changes into `Event`s (rules in `services/events.py`), and publishes one live
  update per cycle through `services/broadcaster.py` to `/api/stream`. The
  interval is 10 s while any client is connected and 60 s otherwise.
- `SshSlurmClient` keeps one connection per account open, authenticates with a
  key Pulse generates in `data/` (shown in the UI via `/api/setup`), and pins
  each account's host key on first connect.
- `pulse/services/notifier.py` fans events out to Web Push subscriptions.
- Accounts connect either `direct` (Pulse polls over SSH) or via `agent`:
  `pulse/agent/pulse_agent.py` is a single-file, **Python 3.6+ stdlib-only**
  script that users install on the login node of clusters that require 2FA.
  Keep it dumb: it ships raw `sacct`/`scontrol`/log/`nvidia-smi` output to
  `POST /api/agent/report` and the server does all the parsing (`SACCT_FIELDS`
  must match `slurm/parsing.py`; a test enforces this). Don't use syntax or
  stdlib features newer than 3.6 in that file.
- `pulse/metrics/` reads training metrics from files jobs already write, so
  users never change their code: TensorBoard event files (a hand-written
  TFRecord/protobuf reader, no TensorFlow), `*metric*.jsonl`/`.csv`,
  `key=value` stdout lines with a step, and hyperparameters from
  `hparams.yaml`/`config.*`. Files are read **incrementally**: the server keeps
  a byte offset per file (`metric_files`), clients send only newer bytes, and
  parsers consume complete records only. Points are unique per
  (job, metric, step). Discovery rules live in `metrics/discovery.py` and are
  mirrored in the agent (a test keeps them equal).
- Auth is a single-user stub (`api/deps.py:get_current_user`). Every query is
  already scoped by `user_id`, so real auth only needs to replace that dependency.

## Frontend notes

```
src/
├── api/          types.ts (mirrors schemas.py), client.ts (fetch), queries.ts (TanStack Query hooks)
├── components/   small presentational components; layout/AppShell.tsx (top bar + mobile tab bar)
├── hooks/        use-push.ts (device push state + enable/disable)
├── lib/          format.ts, labels.ts, push.ts (service worker + PushManager), utils.ts
└── routes/       / (jobs), /jobs/$jobId, /activity, /accounts, /settings
```

- File-based routes live in `src/routes/`; `src/routeTree.gen.ts` is generated
  by the router plugin on `dev`/`build`. Commit it, never hand-edit it.
- Server data goes through the hooks in `src/api/queries.ts`; no ad-hoc `fetch`
  in components. `hooks/use-live-updates.ts` listens on `/api/stream` and
  invalidates the affected queries; timed refetching is only a 60 s fallback.
- Styling: Tailwind v4 with tokens in `src/styles.css` (light + dark via
  `prefers-color-scheme`). Keep the UI minimal: monospace for data, neutral
  chrome, colour only for job state (`run`/`pend`/`fail`) and account identity
  (`acc-0`…`acc-5`, matching `PALETTE_SIZE` in the backend).
- Non-component constants go in `src/lib/` so React fast refresh keeps working.
- Settings: per-device display preferences (theme, density, time format,
  default view, history window, sparklines) live in `lib/ui-settings.ts`
  (localStorage, `useUiSettings()`); `index.html` applies the theme before
  first paint. Dark mode keys off `[data-theme="dark"]`, and compact density
  uses the `compact:` variant. Per-user monitoring settings (refresh speeds,
  alert thresholds) are server-side in `/api/preferences`. Every setting
  applies immediately, with no Save button.
- Metrics UI: `MetricChart` is a dependency-free SVG chart (multi-series,
  TensorBoard-style smoothing, log scale, step/time axis, hover readout);
  `MetricsPanel` groups metrics by prefix; `/compare?ids=1,2` overlays runs
  and diffs hyperparameters. Keep charts dependency-free.
- `public/sw.js` is the service worker (push + notification clicks). iOS only
  delivers Web Push to PWAs that were added to the home screen (iOS 16.4+), and
  permission must be requested from a user gesture.
