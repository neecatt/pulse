# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project

**Pulse** is a minimal HPC monitoring app for Slurm users. It is a responsive web
app that installs to the iOS/Android home screen as a PWA. A user links one or
more HPC accounts (cluster + username), sees every job across all of them in one
place, follows training progress, and gets push notifications when jobs start,
finish, fail, stall, or approach their time limit.

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
- `pulse/services/poller.py` polls each account, stores snapshots, and turns
  state changes into `Event`s via the pure `diff_jobs()` in `services/events.py`.
- `pulse/services/notifier.py` fans events out to Web Push subscriptions.
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
  in components. Live views refetch every 15 s.
- Styling: Tailwind v4 with tokens in `src/styles.css` (light + dark via
  `prefers-color-scheme`). Keep the UI minimal: monospace for data, neutral
  chrome, colour only for job state (`run`/`pend`/`fail`) and account identity
  (`acc-0`…`acc-5`, matching `PALETTE_SIZE` in the backend).
- Non-component constants go in `src/lib/` so React fast refresh keeps working.
- `public/sw.js` is the service worker (push + notification clicks). iOS only
  delivers Web Push to PWAs that were added to the home screen (iOS 16.4+), and
  permission must be requested from a user gesture.
