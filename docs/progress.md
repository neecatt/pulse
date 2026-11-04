# Progress

Running log of what has been built, newest first. Each entry names the branch
it landed on.

## 2026-11-04 — Live updates and quick setup (`feat/live-updates-and-quick-setup`)

- Product principles added to `AGENTS.md`: lightweight, real-time, simple.
- **Real-time:** Server-Sent Events at `/api/stream`. The poller publishes one
  update per user per cycle and the UI refreshes in place. A change reaches
  the browser ~50 ms after a poll completes, measured locally. Polling is
  adaptive: 10 s while the app is open anywhere, 60 s otherwise, and
  immediate when the app opens. A pulsing dot in the header shows the live
  connection.
- **Efficient over SSH:** one persistent connection per account with
  keepalives; GPU sampling (which starts a job step) at most once a minute.
- **Easy setup:** add an account by pasting an SSH login (`jdoe@host`,
  `ssh -p 2222 jdoe@host`, …). Pulse generates its own ed25519 key and shows
  a copy-ready `authorized_keys` command, pins the host key on first connect,
  names the cluster from the hostname, tests the connection immediately, and
  explains failures in plain language.
- **One process:** the API can serve the built web app (`PULSE_STATIC_DIR`);
  `make start` does that. The whole app runs in ~70 MB RAM.
- The SSH client is now tested against an in-process asyncssh server that
  fakes the Slurm CLI (auth, reuse, host-key pinning, error messages).
- 55 backend and 32 frontend tests.

**Caveat:** some centres require MFA or certificate-based SSH (for example
step-ca with 2FA), which blocks unattended access with a static key. Those need
a small agent on the login node that pushes to Pulse (not built yet).

## 2026-11-04 — Frontend dashboard (`feat/frontend-dashboard`)

- Created the private GitHub repo and pushed the history; work now lands via PRs.
- Replaced the mock data with a typed API layer (`src/api`) and TanStack Query
  hooks that refresh every 15 s.
- Pages: Jobs dashboard (stats, account filter, active/all toggle, loss
  sparklines, recent activity), job detail (time used, epoch/loss/GPU stats,
  loss and GPU charts, Slurm metadata, log tail), Activity (events by day),
  Accounts (add / alerts toggle / test connection / remove), Alerts (device
  push, per-event preferences, install help).
- PWA: service worker for Web Push and notification clicks, manifest with
  192/512 icons, safe-area insets, a bottom tab bar on phones, and iOS
  home-screen detection before asking for push.
- Light and dark themes follow the system setting.
- Checked in a browser against the mock backend at 390 px and 1280 px.

**Next up:** real authentication, Alembic migrations, metric retention, offline
caching in the service worker, and trying SSH mode on a real cluster.

## 2026-11-04 — Backend API (`feat/backend-api`)

- FastAPI app (`backend/src/pulse`) with async SQLAlchemy on SQLite. Tables:
  users, accounts, jobs (latest snapshot), job_metrics (time series), events,
  push_subscriptions.
- `SlurmClient` interface with two implementations:
  - `MockSlurmClient`: deterministic simulated cluster whose jobs start, finish,
    fail (OOM), stall and near their time limit within ~10 minutes of startup.
  - `SshSlurmClient`: one SSH connection per poll; `sacct -X -P` (epoch times
    via `SLURM_TIME_FORMAT=%s`), `scontrol` for StdOut, `tail` for loss/epoch,
    `srun --overlap nvidia-smi` for GPU usage (best effort).
- Poller: polls all accounts concurrently every 30 s, upserts jobs, records
  metrics, and emits events for start / complete / fail / cancel, 90% of time
  limit, and no log output for 15 min. The first poll of an account seeds
  silently, and one-shot warnings are latched per job.
- Web Push notifier (VAPID via pywebpush) that respects per-user alert
  preferences and per-account mute, and prunes expired (404/410) subscriptions.
- REST API under `/api`: accounts CRUD + connection check, jobs list/detail,
  events, preferences, push config/subscribe/unsubscribe/test, health.
- `pulse serve` and `pulse gen-vapid` CLI commands.
- 36 tests (parsers, event rules, mock timeline, API, notifier); ruff and strict
  mypy are clean.

**Known gaps:** authentication is a single-user stub; schema is created with
`create_all` (no migrations yet); job_metrics has no retention policy.

## 2026-11-04 — Project structure (`chore/project-structure`)

- Imported the Lovable prototype as the baseline commit.
- Moved the web app into `frontend/`; reserved `backend/` for the API.
- Removed every Lovable dependency: `@lovable.dev/vite-tanstack-config`,
  `.lovable/`, the Lovable error-reporting hooks, and the bunfig exemptions.
- Switched from TanStack Start (SSR + Nitro) to a client-side Vite SPA with
  TanStack Router file routes. The app is a PWA backed by a separate API, so
  SSR added a server runtime without a benefit.
- Removed ~45 unused shadcn/Radix components and their dependencies.
- Added `AGENTS.md` (conventions), `CLAUDE.md`, `.editorconfig`, and a combined
  `.gitignore` for Node and Python.
