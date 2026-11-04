# Pulse

**A lightweight, self-hosted monitor for Slurm jobs and training runs.**
One place for every job across all your HPC accounts, live on your phone and
desktop, with push notifications when something needs you.

- **All your clusters at once.** Link as many HPC accounts as you have; jobs from
  all of them stream into one live view.
- **Training metrics without code changes.** Reads TensorBoard event files,
  `metrics*.jsonl`/`.csv` logs and `step=… loss=…` lines your jobs already
  write: smoothed charts, run comparison, a runs table with parallel
  coordinates for sweeps, and hyperparameters from your config files.
- **Alerts that matter.** Job started, finished, failed, near its time limit or
  stalled, and loss NaN, diverging or plateaued, as push notifications on iOS,
  Android and desktop.
- **Per-node usage.** CPU, memory and every GPU on every node of a job.
- **Works with 2FA clusters.** Where Pulse can't sign in unattended, a tiny
  agent on the login node reports instead (Python 3.6+, standard library only).
- **Passkeys.** Sign in with Face ID, Touch ID or your screen lock; passwords
  stay as a fallback.
- **Light to run.** One container, SQLite, about 70 MB of RAM. Installs as an
  app on your phone's home screen.

## Try it

A demo with a simulated cluster, no HPC access needed:

```sh
docker run --rm -p 8000:8000 -e PULSE_SLURM_BACKEND=mock neecat/pulse
```

Open http://localhost:8000 and enter the setup code printed in the container's
output to create your account.

## Deploy

```sh
git clone https://github.com/neecatt/hpc-monitoring-app.git pulse && cd pulse
cp .env.example .env        # set PULSE_DOMAIN and the admin password
docker compose up -d        # Pulse + Caddy with automatic HTTPS
```

HTTPS is required for push notifications and for installing the app on a phone.
[docs/deployment.md](docs/deployment.md) covers this setup, a private one
with Tailscale (no domain needed), running without Docker, backups and upgrades.

## Connecting clusters

In **Accounts → Add account**, paste the login you use with ssh
(`jdoe@cluster.example.org`) and pick how Pulse connects:

|               | How it works                                                                                                                                                | Use when                                      |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **Direct**    | Pulse signs in over SSH with its own key and runs read-only Slurm commands, through a jump host if needed (`ssh -J …`). The app shows the key to authorise. | You can `ssh` with a key, without 2FA prompts |
| **Via agent** | You paste one command on the login node; a small script reports to Pulse from there.                                                                        | The cluster requires 2FA or SSH certificates  |

Pulse polls every 10 s while you have it open and every 60 s otherwise; both are
adjustable. Per-node usage is sampled at most once a minute through a short
`srun` step, which needs Slurm 20.11 or newer.

## Configuration

Everything is set with `PULSE_*` environment variables (or a `.env` file, or
Docker secrets in `/run/secrets`). The essentials:

| Variable                                            | Purpose                                                                                                      |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `PULSE_ADMIN_USERNAME`, `PULSE_ADMIN_PASSWORD`      | Admin account; the password follows the variable. Unset: create it in the browser with the logged setup code |
| `PULSE_SLURM_BACKEND`                               | `ssh` (default in the image) or `mock` for a demo                                                            |
| `PULSE_VAPID_PUBLIC_KEY`, `PULSE_VAPID_PRIVATE_KEY` | Push notifications; generate with `pulse gen-vapid`                                                          |
| `PULSE_ALLOW_SIGNUP`                                | Let others create their own accounts (each sees only their own data)                                         |
| `PULSE_DOMAIN`                                      | Your public hostname, for the bundled Caddy (compose only)                                                   |

All settings with defaults: [backend/.env.example](backend/.env.example).

## Development

Needs Python 3.12+ and [bun](https://bun.sh).

```sh
make install     # dependencies for both packages
make dev         # API on :8000 and web app with hot reload on :5173 (simulated cluster)
make check       # lint, type checks and tests, as CI runs them
make demo        # build and run the Docker image locally
```

The repository has two independent packages: `backend/` (Python, FastAPI,
SQLAlchemy) and `frontend/` (React, TanStack, Tailwind). They talk only over the
HTTP API. [AGENTS.md](AGENTS.md) describes the architecture and conventions, and
[CONTRIBUTING.md](CONTRIBUTING.md) how to propose changes.

## Images

[`neecat/pulse`](https://hub.docker.com/r/neecat/pulse) on Docker Hub (also mirrored
to `ghcr.io/neecatt/hpc-monitoring-app`), for amd64 and arm64:

| Tag                      | Contents                                          |
| ------------------------ | ------------------------------------------------- |
| `latest`, `1.2`, `1.2.3` | Releases. Pin a version for predictable upgrades  |
| `edge`                   | The newest code on `main`, untested in production |

## Security

Please report vulnerabilities privately; see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
