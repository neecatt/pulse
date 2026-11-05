# Progress

Running log of what has been built, newest first. Each entry names the branch
it landed on.

## 2026-11-05 — Release 0.2.0

- Teams (see below): invite links, sharing accounts or single jobs with a team,
  live read-only views and opt-in alerts for teammates, with a security pass on
  what teammates can see.

## 2026-11-05 — Teams (`feat/teams`)

- An owner creates a team and invites members with single-use links (7 days,
  hashed; joining works with sign-ups off, rate-limited like sign-ups). Any
  member shares their own accounts with a team, or just single jobs. Members
  see what's shared (jobs, runs, metrics, activity) live and read-only, with
  opt-in push alerts ("alice · jdoe@LUMI").
- Visibility lives in `services.teams` (`visible_jobs`, `visible_events`,
  `visible_account_ids`); writes stay owner-only. Poll results carry each
  account's viewers for live updates and the polling interval; teammates who see
  only some of an account's jobs get only those jobs' events and alerts.
- UI: Settings → Team (create, invite link, members, unused links, leave,
  alerts), a switch per team on each of your accounts and jobs, a "Shared with
  you" list on Accounts, `/join/<token>` (works signed out), read-only notes on
  teammates' jobs.
- Tests: 13 backend tests (visibility, read-only, access ending on unshare,
  removal, leaving and team deletion, strangers, invite misuse, live updates,
  opt-in alerts, single-job sharing and its live updates). End to end in a
  browser: owner and a phone-sized member.

## 2026-11-05 — Releasing without CI (`feat/local-release`)

- `make release VERSION=x.y.z [NOTES=file]` publishes from a maintainer's
  machine. It checks for a clean, up-to-date `main` with the version bumped,
  runs `make check`, then builds and pushes the multi-arch image, and only
  after that pushes the tag and creates the GitHub release. Pre-releases skip
  `latest`. `DRY_RUN=1` prints the steps. Checked with ShellCheck and dry runs
  in a throwaway clone.

## 2026-11-05 — Roadmap (`docs/roadmap`)

- `ROADMAP.md` lists planned features: job actions, an in-app terminal, job
  submission, queue estimates, cluster and quota status, a full log viewer,
  more alert channels, teams and a Prometheus export. Features that act on a
  cluster share ground rules: admin opt-in, the user's own key, confirmation
  and an activity log, direct connections only.
- v0.1.4 was built and pushed from a laptop because GitHub Actions is blocked
  by an account billing lock; GitHub Releases v0.1.0–v0.1.4 were created by hand.

## 2026-11-05 — Release 0.1.4

- Security hardening before going public (see below): per-user SSH keys,
  request size limits, outgoing-connection limits, bounded memory, option
  injection and agent fixes, updated image packages.

## 2026-11-05 — Security review before going public (`fix/security-hardening`)

Scans: gitleaks over every branch (no secrets, no keys or databases ever
committed), pip-audit (clean), bandit (no real issues), Trivy on the frontend
packages (Vite dev-server CVEs) and on the image (Debian base only; pip and
setuptools updated). Manual review of auth, sessions, passkeys, CSRF, access
control, SSH commands, the agent, file parsers and outgoing connections.

Fixed:

- **Shared SSH key (high, multi-user).** Any user could add another user's
  cluster login and read their jobs. Each user now has their own key; the first
  account keeps the original one.
- **Unbounded request bodies (high).** Anyone could make the server buffer a
  huge body. 1 MB limit (16 MB for agent reports); the agent keeps reports
  under 12 MB.
- **SSRF via push endpoints and account hosts (medium).** Push only to the
  browsers' push services, without redirects. Non-admins can only connect to
  public addresses, resolved once and connected to by address.
- **Option injection (medium).** A cluster path starting with `-` reached
  `find`/`tail` as an option. Paths must be absolute; job ids are quoted.
- **Unbounded memory (medium).** The login limiter and passkey challenges
  grew without limit. Both are bounded; sign-ups are limited per address, and
  wrong setup codes count toward the address's login limit.
- **Caches keyed by job id (medium).** Node usage and metric-file listings
  mixed up jobs with the same id on different clusters or users.
- **Smaller fixes:** self-referencing YAML no longer recurses forever; the dev
  origin isn't trusted in production; the agent skips symlinks and requires an
  http(s) server; notification clicks stay on Pulse; the data directory is
  mode 700; the image installs Debian updates; Vite 8.1.6; made-up names
  replace a real cluster login in the tests.

`SECURITY.md` now documents the security model and its known limits.

## 2026-11-05 — Release 0.1.3

- Fixes direct SSH (and jump hosts) failing from the Docker image with
  `Permission denied: '/root/.ssh/crt'`.

## 2026-11-05 — Direct SSH from the Docker image (`fix/ssh-ambient-config`)

- Every direct connection from the image failed with `Permission denied:
'/root/.ssh/crt'`: the entrypoint dropped to the pulse user but kept
  `HOME=/root`, and asyncssh reads `~/.ssh` defaults (X.509 certs, config,
  agent). Tests run with a readable home, so they never saw it.
- The entrypoint now sets `HOME=/home/pulse`, and `asyncssh.connect` gets
  `config=None`, `agent_path=None` and no X.509 paths: Pulse uses only its own
  key and host-key pins, whatever environment it runs in.
- Tests: an unreadable `HOME` (the container's case) and a hostile
  `~/.ssh/config` plus `SSH_AUTH_SOCK`; both failed before the fix.

## 2026-11-05 — Release 0.1.2

- Push notifications without setup (generated VAPID keys), sturdier push
  delivery, and the README banner and support links.

## 2026-11-05 — Push keys without setup (`feat/auto-push-keys`)

- Pulse generates its VAPID key pair on first start and keeps it in
  `data_dir/vapid.json` (mode 600), like its SSH key, so push notifications work
  without running `pulse gen-vapid`. Keys set in the environment still win;
  setting only one of the two is refused at startup.
- Push contact (`sub`) defaults to `PULSE_PUBLIC_URL`; compose now sets
  `PULSE_PUBLIC_URL=https://$PULSE_DOMAIN` unless overridden.
- `/api/push/config` returns only the public key (push is always on); the
  "server has no push keys" hint is gone.
- Delivery no longer raises on a malformed subscription (dropped) or an
  unreachable push service (logged, kept), which could otherwise surface as
  an error on the cluster account being polled.

## 2026-11-04 — Release 0.1.1

- Fixes v0.1.0 failing on databases created before jump hosts (in-place column
  upgrade, see below). New README with screenshots.

## 2026-11-04 — Upgrade old databases in place (`fix/schema-upgrade`)

- v0.1.0 failed on databases created before jump hosts (`no such column:
accounts.jump_host`): `create_all` creates tables but never adds columns.
  Startup now adds missing columns and fills existing rows with each column's
  default (scalar or callable, JSON included). Additive changes only; anything
  else still needs a real migration.
- Test: an old-schema database is upgraded, keeps its rows, and a second start
  is a no-op. Also checked against a copy of a real pre-jump-host database.

## 2026-11-04 — Docker Hub and license (`feat/docker-hub`)

- Images publish to Docker Hub as `neecat/pulse` (GHCR kept as a mirror):
  version tags plus `latest` for releases (`git tag v1.2.3`), `edge` for every
  push to `main`; pre-release tags never become `latest`. The Docker Hub
  description is synced from the README. Docker Hub is skipped until the
  `DOCKERHUB_TOKEN` secret exists, so forks and PRs don't fail.
- MIT license (`LICENSE`, image labels, package metadata).
- Release steps in `CONTRIBUTING.md`.

## 2026-11-04 — Jump hosts (`feat/jump-hosts`)

- Direct accounts can go through a jump host (`ssh -J` / `ProxyJump`), as on
  NHR@FAU's `alex`. Paste `ssh -J gateway user@cluster`; Pulse connects to the
  gateway, tunnels to the login node, reuses both connections and pins both host
  keys. Errors say which hop failed.
- This is the reliable option for clusters without cron, where the agent
  can't keep running: nothing stays on the cluster.
- Agent: errors now go to `~/.config/pulse-agent/agent.log` (rotated at 64 KB),
  since cron discards output; the stale-agent message explains the no-cron case.
- Tested against two in-process SSH servers (a forwarding jump host and a fake
  cluster): tunnel used, connections reused, jump host key pinned, unreachable
  jump host named in the error.

## 2026-11-04 — Platform-neutral main (`chore/remove-railway`)

- `main` stays generic for open-source self-hosting. Railway-specific setup
  (`railway.json`, no `VOLUME` in the Dockerfile, the Railway guide) lives on
  the `deploy/railway` branch, which Railway builds from and which merges in
  `main` to pick up changes.
- Kept on `main` because they're generic: listening on a platform's `PORT`, and
  the entrypoint taking ownership of root-owned volumes and bind mounts.

## 2026-11-04 — Passkeys (`feat/passkeys`)

- Sign in with a passkey (Face ID, Touch ID, Windows Hello, security keys) as
  well as a password. The sign-in screen has a passkey button, and the
  username field offers saved passkeys through browser autofill (WebAuthn
  conditional mediation), so signing in is a tap. After a password sign-in, a
  one-time hint offers to add one; Settings lists and removes them.
- Server: `webauthn` library; discoverable credentials (no username needed);
  single-use challenges with a 5-minute TTL; origin and domain checked, so a
  passkey response replayed from another site is rejected; optional
  `PULSE_PUBLIC_URL` pins the domain.
- Tests: a software authenticator (`tests/softauthn.py`) drives registration
  and sign-in through real verification (phishing origin, replay, removed and
  foreign passkeys, per-user isolation). In the browser, Chrome's virtual
  authenticator ran password sign-in → add passkey → sign out → automatic
  passkey sign-in.
- Also: settings validation errors no longer echo rejected values (a
  too-short `PULSE_ADMIN_PASSWORD` used to appear in the log).

## 2026-11-04 — Railway deployment (`feat/railway`)

- `railway.json`: Dockerfile build, one replica (SQLite and in-memory live
  updates need a single instance), health check on `/api/health`.
- Pulse listens on the platform's `PORT` (Railway, Render, Fly, Heroku) unless
  `PULSE_PORT` is set. Testing caught the image's built-in `PULSE_PORT` default
  overriding it, which would have failed every Railway deploy; that default is
  removed.
- The image starts through an entrypoint that takes ownership of root-owned
  volumes (as Railway mounts them), then drops to the unprivileged `pulse` user.
- Verified by running the image as Railway would: `PORT`, a root-owned `/data`,
  proxied HTTPS giving `Secure` cookies and HSTS.
- Guide: `docs/deployment.md` → Railway.

## 2026-11-04 — Self-hosting: image, HTTPS, CI (`feat/deployment`)

- **Container image:** a multi-stage `Dockerfile` (Bun installs and Node builds
  the web app; slim Python runtime, non-root, `/data` volume, health check).
  257 MB, runs in about 70 MB of RAM. Verified locally: setup code in the logs,
  sign-in, live stream, security headers, data and sessions surviving a
  restart, healthy status.
- **HTTPS:** `compose.yaml` runs Pulse behind Caddy with automatic Let's Encrypt
  certificates; only Caddy is exposed. `docs/deployment.md` also covers
  Tailscale (private HTTPS, no domain), running without Docker (systemd
  unit), push setup, users, backups and a security checklist.
- **Hardening:** first-run setup needs a one-time code from the server log;
  short env admin passwords fail at startup; CSP and other security headers,
  HSTS over HTTPS; forwarded headers trusted only from configured proxies;
  fonts bundled (no Google Fonts), and no inline scripts.
- **CI:** checks for both packages plus an image build on every PR; multi-arch
  images (amd64, arm64) published to GHCR from `main` and `v*` tags; Dependabot.
- **Open source:** README for new users, `CONTRIBUTING.md`, `SECURITY.md`
  (private vulnerability reporting). A license is still to be chosen.

## 2026-11-04 — Authentication (`feat/auth`)

- Username/password sign-in with scrypt hashes (standard library) and revocable
  cookie sessions. The admin account comes from `PULSE_ADMIN_*` env vars or
  Docker secrets and follows them on restart; otherwise first-run setup in the
  browser.
- Sign-up off by default; login rate limiting; CSRF origin check; per-user data
  isolation tested; `pulse create-user` / `reset-password` CLI.
- UI: sign-in and setup screens; Settings → Your account (password, devices,
  sign out).

## 2026-11-04 — Analysis, phase 2 (`feat/analysis`)

- **Runs page** (`/runs`):
  - Sortable table with the primary metric, a validation metric and the
    hyperparameters that actually vary (picked automatically; a column picker
    customises them).
  - Sweep chips narrow it to one job array; select runs to compare.
  - **Parallel coordinates:** one axis per hyperparameter, log scale chosen
    automatically for values like learning rates, and the metric axis. Lines
    are coloured best to worst, and hover is synced with the table.
- **Sweeps:** job array tasks (`123_4`) group by array id. On the jobs list a
  sweep is one collapsible row with task counts by state and an "Analyse" link.
- **Metric alerts** (new event kinds, configurable in Settings):
  - NaN/Inf loss.
  - Diverging: smoothed loss more than X% above its best smoothed value, so
    noise and one-off good batches don't trigger it.
  - Plateau: no new best loss for N minutes.
  - Backed by running per-metric summaries, so no history scans.
- **Per-node usage:** one `srun` step samples CPU, memory and every GPU on
  each node at most once a minute (also for CPU-only jobs). The job page shows
  per-node CPU/memory/GPU charts and a live per-GPU grid.
- Mock cluster: a 6-task learning-rate sweep where one unstable task diverges,
  then goes NaN, about 5 and 15 minutes after startup.
- 110 backend tests, 58 frontend tests.

## 2026-11-04 — Configuration and constants (`feat/analysis`)

- Each kind of value now has one home (rule in `AGENTS.md`):
  - `pulse/constants.py` and `src/config/constants.ts` hold the shared limits
    that were scattered across about 15 modules.
  - Operator tunables (SSH command timeout and keepalive, metric discovery and
    node-stats intervals, push TTL/timeout) moved into `Settings`, so `.env`
    can override them.
  - `src/config/env.ts` is the only reader of build-time env vars.
  - New `frontend/.env.example`; `backend/.env.example` documents every setting.
- Lint guards: `os.environ`/`os.getenv` outside `Settings` (ruff TID251) and
  `import.meta.env` outside `config/env.ts` (ESLint) fail the build.
- Audit: no secrets were hardcoded. VAPID keys, database URL and SSH settings
  were already env-only, the generated SSH key lives in gitignored `data/`, and
  agent tokens are stored as hashes.
- Extracted a `useCopy` hook (copy feedback was implemented twice).

## 2026-11-04 — Training metrics, phase 1 (`feat/metrics`)

Monitoring features from TensorBoard and W&B, without users changing their
training code.

- **Collection:** TensorBoard event files (scalars, PyTorch and TF2 styles),
  `metrics*.jsonl`, `metrics*.csv`/`progress.csv` (e.g. Lightning
  CSVLogger), and `step=… loss=…` stdout lines. Hyperparameters come from
  `hparams.yaml`/`config.yaml`/`.json`, including W&B's config format.
- **Efficient:** files are discovered at most once a minute per job and then
  read incrementally by byte offset (256 KB per file per poll); points are
  deduplicated by step. It works the same over direct SSH (one command per
  job) and through the agent, which persists the server's offsets between
  cron runs.
- **UI:**
  - One chart per metric, grouped by prefix (`train/`, `val/`).
  - Smoothing slider (debiased EMA, raw line shown faint), log scale, step or
    time x-axis, and a hover/touch readout. Chart settings are remembered per
    device.
  - Hyperparameters table.
  - Notes and tags on jobs; tags show on the list and are searchable.
  - Search the jobs list by name, id, tag, partition or cluster.
  - Compare: select up to 6 jobs to overlay their curves and diff their
    hyperparameters (only the differences, by default).
- Charts are a dependency-free SVG component; the frontend gained no new
  runtime dependencies. The backend gained PyYAML.
- 91 backend tests (event files generated by tensorboardX, incremental SSH
  reads against a fake server, agent chunks end to end) and 51 frontend tests.

**Next (phase 2):** runs table with hyperparameter columns, parallel
coordinates, job arrays as sweeps, per-node CPU/memory/GPU timeline, and alerts
on metric values (NaN, divergence, plateau).

## 2026-11-04 — Settings (`feat/settings`)

- New **Settings** tab (replaces "Alerts"); every option applies instantly:
  - Appearance, per device: theme (System / Light / Dark), density
    (Comfortable / Compact), and event times (relative / clock).
  - Jobs list, per device: default view, finished-job history (6/24/48 h),
    and loss sparklines on or off.
  - Notifications: device push on/off/test, plus per-event toggles.
  - Monitoring, per user, server-side: refresh while open (5 s–1 min), refresh
    in the background (1–15 min), stall threshold, and time-limit warning %.
  - Connection: demo/SSH mode, Pulse's SSH key, and version.
- The poller now schedules each account by its owner's refresh settings
  (5 s tick) and uses their alert thresholds; agents follow the same pace.
- The theme applies before first paint (no flash) and follows OS changes in
  System mode.

## 2026-11-04 — Login-node agent (`feat/login-node-agent`)

- For clusters where Pulse can't sign in unattended (2FA, SSH certificates).
  When adding an account, choose **Via agent** and the app shows one command
  to paste on the login node; it switches to "Connected" when the first report
  arrives.
- `pulse_agent.py`: one file, Python 3.6+ stdlib only, no root, no daemon.
  Cron starts it every minute; each run reports for ~55 s at the pace the
  server returns (10 s while you're watching, 60 s otherwise) under a lock.
  It samples GPUs at most once a minute, and has `status`, `uninstall` and
  `loop` commands (`loop` for nodes without cron).
- Server: per-account agent token (hash stored; reissuing revokes the old one);
  reports go through the same ingest path as polling, so events, push and live
  updates are identical. Silent agents get flagged after 3 minutes.
- Verified end to end: the browser created an agent account, the copied
  command ran in a sandbox with fake Slurm binaries, and the UI flipped to
  Connected live.

**Caveats:** the cluster must be able to reach Pulse over HTTP(S), so it needs
a public address, not `localhost`. Load-balanced login aliases run cron on
whichever node you installed on.

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
