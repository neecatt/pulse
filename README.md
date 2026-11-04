# Pulse — HPC monitor

Minimal, mobile-first monitoring for Slurm jobs across multiple HPC accounts.
Installable as a PWA on iOS and Android, with push notifications when jobs
start, finish, or fail.

| Package                  | Stack                                                |
| ------------------------ | ---------------------------------------------------- |
| [`frontend/`](frontend/) | React 19, Vite, TanStack Router & Query, Tailwind v4 |
| [`backend/`](backend/)   | Python 3.12, FastAPI, SQLAlchemy (async), Web Push   |

## Quick start

Needs Python 3.12+ and [bun](https://bun.sh).

```sh
make install
make start          # everything on http://localhost:8000 (one process, ~70 MB RAM)
make dev            # or: hot reload on :5173 while developing
```

By default Pulse runs against a simulated cluster, so you can try it without
access to an HPC system. To use real clusters, set `PULSE_SLURM_BACKEND=ssh` in
`backend/.env`. Then add an account by pasting your SSH login
(`jdoe@lumi.csc.fi`) and authorise the key the app shows you. Updates stream
live to the browser while the app is open.

See [AGENTS.md](AGENTS.md) for conventions and [docs/progress.md](docs/progress.md)
for the development log.
