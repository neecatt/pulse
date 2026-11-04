# Deploying Pulse

Pulse ships as one container image, `ghcr.io/neecatt/hpc-monitoring-app`
(multi-architecture: amd64 and arm64). It serves the web app and the API on
port 8000, keeps everything in `/data` (SQLite database and Pulse's SSH key),
and is configured only through `PULSE_*` environment variables.

Pulse needs **HTTPS** for anything beyond a local try-out: browsers only allow
push notifications and home-screen installation on secure origins, and session
cookies are marked `Secure` over HTTPS. Pick one of the setups below.

## 1. Public server with a domain (Docker + Caddy)

You need a machine with Docker, a DNS name (say `pulse.example.org`) pointing
at it, and ports 80 and 443 open. Caddy obtains and renews a Let's Encrypt
certificate automatically.

```sh
git clone https://github.com/neecatt/hpc-monitoring-app.git pulse && cd pulse
cp .env.example .env
```

Edit `.env`: set `PULSE_DOMAIN`, `PULSE_ADMIN_USERNAME` and a long
`PULSE_ADMIN_PASSWORD` (at least 10 characters). Then:

```sh
docker compose up -d
docker compose logs -f pulse       # wait for "Application startup complete"
```

Open `https://pulse.example.org` and sign in. In this setup only Caddy is
exposed; the Pulse container isn't reachable directly, which is why
`compose.yaml` can safely trust Caddy's forwarded headers.

**Without an admin in `.env`**, the first visit asks for a setup code. Find it
with `docker compose logs pulse | grep "setup code"`. This keeps a fresh public
instance from being claimed by whoever finds it first.

## 2. Railway (hosted, no server to manage)

[Railway](https://railway.com) builds the image from this repository and gives
it an `https://….up.railway.app` address, so it works on your phone right away.
`railway.json` already configures the build, a single instance (Pulse uses
SQLite) and the health check. Pulse needs about 70 MB of RAM, which fits
Railway's smallest plan.

1. **Create the service:** in Railway, choose **New Project → Deploy from GitHub
   repo** and pick this repository (or your fork), branch `main`.
2. **Add storage:** right-click the service → **Attach volume**, mount path
   `/data`. Without it, every deploy starts from an empty database and a new SSH
   key.
3. **Set variables** (service → **Variables**):

   | Variable                                            | Value                                            |
   | --------------------------------------------------- | ------------------------------------------------ |
   | `PULSE_ADMIN_USERNAME`                              | your admin username                              |
   | `PULSE_ADMIN_PASSWORD`                              | a long password (10+ characters)                 |
   | `PULSE_TRUSTED_PROXIES`                             | `*` (Railway's proxy is the only way in)         |
   | `PULSE_VAPID_PUBLIC_KEY`, `PULSE_VAPID_PRIVATE_KEY` | from `pulse gen-vapid` (see below)               |
   | `PULSE_VAPID_SUBJECT`                               | `mailto:you@example.org`                         |
   | `PULSE_SLURM_BACKEND`                               | leave unset for real clusters; `mock` for a demo |

   Generate the push keys once on your computer and keep them: new keys would
   disconnect every phone that has notifications on.

   ```sh
   backend/.venv/bin/pulse gen-vapid      # or: docker run --rm ghcr.io/neecatt/hpc-monitoring-app pulse gen-vapid
   ```

4. **Get the address:** service → **Settings → Networking → Generate Domain**.
   Railway sends traffic to the port it gives Pulse in `PORT`; nothing to set.
5. Open the address on your phone, sign in, and install it (see
   [Push notifications](#push-notifications)).

Railway redeploys on every push to `main`. Logs are under the service's
**Deployments** tab.

**Clusters from Railway:**

- **Direct SSH accounts:** connect from Railway's servers. Some HPC centres only
  accept SSH from allow-listed addresses or block cloud providers, and
  Railway's outgoing address isn't fixed on the basic plans.
- **Agent accounts:** work as long as the login node can reach the
  `….up.railway.app` address.

## 3. Private, no domain (Tailscale)

[Tailscale](https://tailscale.com) gives the machine a private HTTPS address
like `https://pulse-server.tail1234.ts.net`, reachable only from your devices.

```sh
docker run -d --name pulse --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v pulse-data:/data --env-file .env \
  -e PULSE_SECURE_COOKIES=always \
  ghcr.io/neecatt/hpc-monitoring-app
tailscale serve --bg 8000
```

Install Tailscale on your phone to use the app there.

- **Agents:** the login-node agent must reach Pulse. A cluster isn't on your
  tailnet, so agent-connected accounts need `tailscale funnel 8000`, which
  makes the address public, or setup 1. Direct SSH accounts work either way.
- **Cookies:** `PULSE_SECURE_COOKIES=always` keeps cookies `Secure`. Docker's
  port forwarding hides that requests arrived over HTTPS, so Pulse can't detect it.

## 4. Without Docker

```sh
git clone https://github.com/neecatt/hpc-monitoring-app.git /opt/pulse && cd /opt/pulse
make install && (cd frontend && bun run build)
cp backend/.env.example backend/.env && chmod 600 backend/.env   # then edit it
sudo cp deploy/pulse.service /etc/systemd/system/ && sudo systemctl enable --now pulse
```

Put a reverse proxy with HTTPS in front of `127.0.0.1:8000`, for example Caddy
with `deploy/Caddyfile` (`PULSE_UPSTREAM=127.0.0.1:8000`). The proxy must not
buffer `/api/stream`, the live update stream.

## Push notifications

```sh
docker compose run --rm pulse pulse gen-vapid
```

Copy the two lines into `.env`, set `PULSE_VAPID_SUBJECT` to a `mailto:` contact
for push services, and restart. Then in the app, **Settings → Enable on this
device**. On iPhone and iPad, add Pulse to the Home Screen first and open it
from there (iOS 16.4+).

## Connecting clusters

- **Direct:** Pulse generates its own SSH key on first start; the app shows it
  with a copy-ready `authorized_keys` command. The host key is pinned on first
  connect.
- **Agent:** for clusters that require 2FA. The install command in the app
  points the agent at the address you opened Pulse on, so open Pulse through
  its public URL before copying the command.

Before adding accounts, check your centre's rules on automated Slurm queries.
Pulse runs `sacct` every 10 s while you're watching (adjustable in Settings),
and once a minute a short `srun --overlap` step in each running job to sample
CPU and GPU usage.

## Users

- **Admin:** the account from `PULSE_ADMIN_USERNAME`/`PASSWORD`, or the one
  created with the setup code.
- **More users:** set `PULSE_ALLOW_SIGNUP=true`, or create them on the server:
  `docker compose exec pulse pulse create-user alice`.
- **Forgotten password:** `docker compose exec pulse pulse reset-password alice`.
  To rotate the admin password, change it in `.env` and restart.

## Backups and upgrades

All state is in the `pulse-data` volume. Back it up with:

```sh
docker compose stop pulse
docker run --rm -v pulse_pulse-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/pulse-backup.tgz -C /data .
docker compose start pulse
```

Upgrade with `docker compose pull && docker compose up -d`. While Pulse is
below 1.0 the database schema may change between versions without automatic
migration; release notes say when a fresh database is needed.

## Security checklist

- HTTPS in front of Pulse (any of the setups above).
- A long admin password, or the setup-code flow; `PULSE_ALLOW_SIGNUP` off
  unless you want open registration.
- `.env` readable only by you: `chmod 600 .env`. Or use Docker secrets, where a
  file `/run/secrets/pulse_admin_password` sets `PULSE_ADMIN_PASSWORD`.
- Only expose port 8000 through the proxy. Trust forwarded headers
  (`PULSE_TRUSTED_PROXIES`) only from the proxy, or clients could spoof their
  address and slip past the login rate limit.
