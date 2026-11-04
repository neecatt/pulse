# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Before you start

For anything bigger than a small fix, open an issue first so we can agree on
the approach. Pulse aims to stay **lightweight, real-time and simple to use**.
Those principles, and where each kind of code and configuration belongs, are in
[AGENTS.md](AGENTS.md); proposals are judged against them.

## Setup

```sh
make install    # Python 3.12+ and bun required
make dev        # runs against a simulated cluster, no HPC access needed
```

## Pull requests

- Branch from `main` as `<type>/<topic>` (`feat/`, `fix/`, `docs/`, ...).
- Use [Conventional Commits](https://www.conventionalcommits.org):
  `type(scope): summary`, scopes `backend`, `frontend`, `docs`, `repo`.
- Add or update tests for behaviour you change, and run `make check` (the same
  checks CI runs).
- Keep changes focused. Update `docs/progress.md`, and `AGENTS.md` if you change
  conventions or layout.
- Don't commit secrets or `.env` files. New settings go into
  `backend/.env.example` with a comment.

## Reporting bugs

Include your Slurm version (`sacct --version`), how Pulse connects (direct or
agent) and what you expected. Output of the failing Slurm command, with names
redacted, helps a lot.
