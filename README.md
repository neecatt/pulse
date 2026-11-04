# Pulse — HPC monitor

Minimal, mobile-first monitoring for Slurm jobs across multiple HPC accounts.
Installable as a PWA on iOS and Android, with push notifications when jobs
start, finish, or fail.

| Package                  | Stack                                               |
| ------------------------ | --------------------------------------------------- |
| [`frontend/`](frontend/) | React 19, Vite, TanStack Router & Query, Tailwind v4 |
| [`backend/`](backend/)   | Python 3.12, FastAPI, SQLAlchemy (async), Web Push  |

## Quick start

```sh
# API (mock cluster by default) — http://127.0.0.1:8000/docs
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pulse serve --reload

# Web app — http://localhost:5173 (proxies /api to the backend)
cd frontend
bun install
bun run dev
```

See [AGENTS.md](AGENTS.md) for conventions and [docs/progress.md](docs/progress.md)
for the development log.
