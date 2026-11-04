# Pulse — HPC monitor

Minimal, mobile-first monitoring for Slurm jobs across multiple HPC accounts.
Installable as a PWA on iOS and Android, with push notifications when jobs
start, finish, or fail.

| Package                  | Stack                                               |
| ------------------------ | --------------------------------------------------- |
| [`frontend/`](frontend/) | React 19, Vite, TanStack Router & Query, Tailwind v4 |

## Quick start

```sh
cd frontend
bun install
bun run dev        # http://localhost:5173
```

See [AGENTS.md](AGENTS.md) for conventions and [docs/progress.md](docs/progress.md)
for the development log.
