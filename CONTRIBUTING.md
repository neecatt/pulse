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

## Releasing (maintainers)

1. **Bump the version** in `backend/pyproject.toml`, `backend/src/pulse/__init__.py`
   and `frontend/package.json`, note the changes in `docs/progress.md`, and merge
   that as a pull request.
2. **Publish** from an up-to-date `main`, signed in to Docker Hub (`docker login`)
   and GitHub (`gh auth login`):

   ```sh
   make release VERSION=0.2.0 NOTES=notes.md   # NOTES optional: else notes come from the merged PRs
   DRY_RUN=1 make release VERSION=0.2.0        # print the steps without doing them
   ```

   It runs the checks, builds and pushes `neecat/pulse:0.2.0`, `:0.2` and
   `:latest` for amd64 and arm64, and only then pushes the `v0.2.0` tag and
   creates the GitHub release, so a release never exists without its image. A
   version with a suffix (`0.2.0-rc.1`) publishes only its own tag and is marked
   as a pre-release.

## Reporting bugs

Include your Slurm version (`sacct --version`), how Pulse connects (direct or
agent) and what you expected. Output of the failing Slurm command, with names
redacted, helps a lot.
