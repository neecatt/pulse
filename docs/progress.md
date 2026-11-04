# Progress

Running log of what has been built, newest first. Each entry names the branch
it landed on.

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
