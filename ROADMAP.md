# Roadmap

Features planned for Pulse, grouped by what they give you. Nothing here has a
date yet. Ideas and votes are welcome in the issues; see
[CONTRIBUTING.md](CONTRIBUTING.md) to help build them.

Done so far: **teams** (invite links, read-only sharing of chosen accounts, live
updates and opt-in alerts for members).

Every feature is held to the same rules as the rest of Pulse (see
[AGENTS.md](AGENTS.md)): light to run, live, and simple to use.

## Ground rules for acting on clusters

Pulse is **read-only** on clusters today: it never submits, cancels or changes
anything. Three planned features change that (job actions, the terminal and job
submission), so they share these safeguards:

- **Off unless the admin turns it on**, per server (for example
  `PULSE_ALLOW_JOB_ACTIONS`, `PULSE_ALLOW_TERMINAL`). A default install stays
  read-only.
- **Your own key only.** Actions run as your cluster login with your personal
  Pulse key, so they can do exactly what you could do over SSH, and nothing more.
- **Confirmed and logged.** Every action asks for confirmation and is recorded
  (who, what, when) in an activity log visible to the user and admins.
- **Direct connections only.** The login-node agent stays one-way (it reports,
  it never runs commands sent by the server), so these features need a direct or
  jump-host connection.

## Control from your phone

### Job actions

Cancel, hold, release or requeue a job from its page, using `scancel` and
`scontrol`. Arrays can be acted on as a whole or per task. It covers the most
common reason to reach for a terminal, with one tap and a confirmation instead
of typing commands.

### Terminal

An SSH terminal to a linked cluster, inside the app, for everything Pulse has
no button for: checking a file, editing a config, running a quick command.

- **Usable on a phone:** a key bar for Ctrl, Esc, Tab and the arrows, copy and
  paste, and saved snippets (`squeue --me`, `quota`, …) one tap away.
- **Opens in place:** from a job, the terminal opens in the job's working
  directory.
- **Safe by design:**
  - opening a terminal asks you to confirm with your passkey or password again;
  - sessions close after a period without input;
  - the connection checks the site it comes from, like every other request;
  - session start and end are logged.
- **No outside code:** the terminal emulator is bundled with the app, like the
  fonts.

### Submit jobs

Resubmit a finished or failed job with the same script, or submit from saved
`sbatch` templates with a few fields to fill in (time, GPUs, arguments).
Submitted jobs appear in the list immediately and get the usual alerts.

## Know more about your jobs and clusters

### Queue position and start estimates

For pending jobs: their position in the queue, Slurm's estimated start time
(`squeue --start`) and the reason they're waiting, in plain language. An
optional alert fires when a job is about to start.

### Cluster and quota status

A page per cluster with:

- partition availability: free nodes and GPUs (`sinfo`);
- your fair-share and the GPU hours used from your budget (`sshare`, `sreport`);
- your storage quotas, with a warning before a quota fills up and jobs start
  failing.

### Full log viewer

Open a job's whole output and error files, with search, jump to the first error,
and a live tail that follows new lines. Files are fetched in chunks, so large
logs stay fast on a phone.

## Share and connect

### More alert channels

Send alerts to email, Slack, Discord, Telegram or [ntfy](https://ntfy.sh)
besides Web Push, chosen per alert type. Useful on desktops without push and for
team channels.

### Metrics export

A Prometheus `/metrics` endpoint with job counts, states, queue times and
per-node GPU usage, so Pulse data can go into Grafana or existing monitoring.
It's protected by its own token, separate from user sign-in.
