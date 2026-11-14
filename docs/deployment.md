# Self-hosting Pulse

Pulse is one container image, [`neecat/pulse`](https://hub.docker.com/r/neecat/pulse)
on Docker Hub, for amd64 and arm64. It serves the web app and the API from one
process, keeps everything in one `/data` volume (an SQLite database, the SSH keys
it generates and its push keys), and is configured only through `PULSE_*`
environment variables. There's no database server, queue or cache to run next
to it.

## Before you start

You need:

- **A machine or container platform** that can run a Docker image, plus a
  little disk for `/data`. A small VPS, a home server or a platform such as
  Railway, Render or Fly.io all work.
- **Outbound SSH** from that machine to your clusters' login nodes (port 22,
  or the port your centre uses). Clusters that require 2FA use the agent
  instead; see [Connecting clusters](#connecting-clusters).
- **HTTPS** for anything beyond a local try-out. Browsers only allow push
  notifications, passkeys and home-screen installation on secure origins, and
  session cookies are marked `Secure` over HTTPS. Each setup below includes it.

Run **one instance** per `/data` volume. Pulse keeps sign-in challenges and live
connections in memory, so it doesn't scale out to several replicas.

## Try it locally

One command starts Pulse with a simulated cluster, so you can look around
before connecting anything real:

```sh
docker run --rm -p 8000:8000 -e PULSE_SLURM_BACKEND=mock neecat/pulse
```

Open `http://localhost:8000`. The first visit asks for a setup code; it's in
the container's log (`setup code XXXX-XXXX-XXXX`). Nothing is kept after you
stop the container.

## Choose a setup

| Setup                                                             | Best for                            | HTTPS from         |
| ----------------------------------------------------------------- | ----------------------------------- | ------------------ |
| [Docker and Caddy](#1-public-server-with-a-domain-docker--caddy)  | A server you control, with a domain | Caddy (automatic)  |
| [Tailscale](#2-private-no-domain-tailscale)                       | Just you, on your own devices       | Tailscale          |
| [Container platform](#3-container-platforms-railway-render-flyio) | No server to maintain               | The platform       |
| [Without Docker](#4-without-docker)                               | An existing server with systemd     | Your reverse proxy |

## 1. Public server with a domain (Docker + Caddy)

You need a machine with Docker, a DNS name (say `pulse.example.org`) pointing
at it, and ports 80 and 443 open. Caddy obtains and renews a Let's Encrypt
certificate automatically.

```sh
git clone https://github.com/neecatt/pulse.git && cd pulse
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

## 2. Private, no domain (Tailscale)

[Tailscale](https://tailscale.com) gives the machine a private HTTPS address
like `https://pulse-server.tail1234.ts.net`, reachable only from your devices.

```sh
docker run -d --name pulse --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v pulse-data:/data --env-file .env \
  -e PULSE_SECURE_COOKIES=always \
  neecat/pulse
tailscale serve --bg 8000
```

Install Tailscale on your phone to use the app there.

- **Agents:** the login-node agent must reach Pulse. A cluster isn't on your
  tailnet, so agent-connected accounts need `tailscale funnel 8000`, which
  makes the address public, or setup 1. Direct SSH accounts work either way.
- **Cookies:** `PULSE_SECURE_COOKIES=always` keeps cookies `Secure`. Docker's
  port forwarding hides that requests arrived over HTTPS, so Pulse can't detect it.

## 3. Container platforms (Railway, Render, Fly.io)

Platforms that run a Docker image give you HTTPS and a domain without a server
to maintain. Pulse listens on the `PORT` the platform sets.

1. Create a service from the image `neecat/pulse:latest`, or pin a version
   such as `neecat/pulse:0.2.6`. To upgrade without touching the service, turn
   on the platform's image auto-updates (on Railway: the service's image
   settings), and it redeploys whenever `latest` moves.
2. Attach a persistent **volume** mounted at `/data`. Without it, every
   redeploy loses your accounts, SSH keys and pinned host keys.
3. Set the variables:

   ```sh
   PULSE_ADMIN_USERNAME=admin
   PULSE_ADMIN_PASSWORD=a-long-password
   PULSE_PUBLIC_URL=https://your-app.example.app
   PULSE_TRUSTED_PROXIES=*
   ```

   `PULSE_TRUSTED_PROXIES=*` is right when the platform's proxy is the only
   way in: Pulse then sees that requests arrived over HTTPS.

4. Keep it at **one replica**, and deploy.

Health checks can use `/api/health`. If you add your own domain later, update
`PULSE_PUBLIC_URL`; passkeys made on the old domain stop working there.

## 4. Without Docker

```sh
git clone https://github.com/neecatt/pulse.git /opt/pulse && cd /opt/pulse
make install && (cd frontend && bun run build)
cp backend/.env.example backend/.env && chmod 600 backend/.env   # then edit it
sudo cp deploy/pulse.service /etc/systemd/system/ && sudo systemctl enable --now pulse
```

This needs Python 3.12 and [Bun](https://bun.sh). Put a reverse proxy with HTTPS
in front of `127.0.0.1:8000`, for example Caddy with `deploy/Caddyfile`
(`PULSE_UPSTREAM=127.0.0.1:8000`). The proxy must not buffer `/api/stream`, the
live update stream.

## First sign-in

- **With `PULSE_ADMIN_USERNAME` and `PULSE_ADMIN_PASSWORD` set**, sign in with
  them. The password follows the variable: change it there and restart.
- **Without them**, the first visit asks for the one-time setup code printed in
  the log, then lets you create the admin account.

Then open **Accounts**, add a cluster login such as `jdoe@lumi.csc.fi`, and
follow the steps it shows.

## Connecting clusters

- **Direct:** Pulse generates its own SSH key on first start; the app shows it
  with a copy-ready `authorized_keys` command. The host key is pinned on first
  connect.
- **Behind a jump host** (`ProxyJump` in your `~/.ssh/config`): paste the login
  as `ssh -J gateway.example.org you@cluster.example.org`. Pulse connects to the
  gateway, tunnels to the login node and pins both host keys. Pulse's key must
  be accepted on both; centres that manage keys through a web portal (such as
  NHR@FAU) usually apply one upload to both. Prefer this over the agent on
  clusters without cron: nothing has to stay running on the cluster.
- **Agent:** for clusters that require 2FA. The install command in the app
  points the agent at the address you opened Pulse on, so open Pulse through
  its public URL before copying the command. The agent needs Python 3.6 or
  newer on the login node and nothing else.

Before adding accounts, check your centre's rules on automated Slurm queries.
Pulse runs `sacct` every 10 s while you're watching (adjustable in Settings),
and once a minute a short `srun --overlap` step in each running job to sample
CPU and GPU usage.

## Push notifications

Nothing to set up: Pulse generates its push (VAPID) keys on first start and keeps
them in `/data/vapid.json`. In the app, **Settings → Enable on this device**. On
iPhone and iPad, add Pulse to the Home Screen first and open it from there
(iOS 16.4+).

Push services are told `PULSE_PUBLIC_URL` as the contact; set
`PULSE_VAPID_SUBJECT` (`mailto:you@example.org`) to use an email address instead.
To manage the keys yourself, for example to share them between servers, set
`PULSE_VAPID_PUBLIC_KEY` and `PULSE_VAPID_PRIVATE_KEY` (from `pulse gen-vapid`).
Changing the keys disconnects every device until it turns notifications on again.

## Users

- **Admin:** the account from `PULSE_ADMIN_USERNAME`/`PASSWORD`, or the one
  created with the setup code.
- **More users:** set `PULSE_ALLOW_SIGNUP=true`, or create them on the server:
  `docker compose exec pulse pulse create-user alice`. With sign-ups on, people
  create an account with just a username and a passkey (a password is optional,
  and can be added later in Settings as a backup). No email is involved.
- **Passkeys:** after signing in, **Settings → Your account → Add a passkey**,
  once per device. Passkeys only work over HTTPS (or on `localhost`), and are
  tied to the domain you created them on. If Pulse is reachable under several
  names, set `PULSE_PUBLIC_URL` to the one you use.
- **Forgotten password:** `docker compose exec pulse pulse reset-password alice`.
  To rotate the admin password, change it in `.env` and restart.

## Configuration reference

Every setting is optional and comes from an environment variable, an `.env`
file, or a Docker secret in `/run/secrets` (for example
`/run/secrets/pulse_admin_password`).

| Variable                                                                                                  | What it does                                                                              | Default                 |
| --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ----------------------- |
| `PULSE_ADMIN_USERNAME`, `PULSE_ADMIN_PASSWORD`                                                            | Admin account, synced on every start. Unset: create it in the browser with the setup code | _(unset)_               |
| `PULSE_PUBLIC_URL`                                                                                        | The address users open; pins the domain passkeys belong to                                | the request's host      |
| `PULSE_TRUSTED_PROXIES`                                                                                   | Proxies allowed to set `X-Forwarded-*`; `*` behind a platform proxy                       | `127.0.0.1`             |
| `PULSE_SECURE_COOKIES`                                                                                    | `auto`, `always` or `never`                                                               | `auto`                  |
| `PULSE_SESSION_DAYS`                                                                                      | How long a sign-in lasts                                                                  | `30`                    |
| `PULSE_ALLOW_SIGNUP`                                                                                      | Let anyone with the URL create an account                                                 | `false`                 |
| `PULSE_DEMO`                                                                                              | Public landing page and "Try the demo" guests on simulated clusters                       | `false`                 |
| `PULSE_DOMAIN`                                                                                            | Hostname Caddy gets a certificate for (compose only)                                      | _(unset)_               |
| `PULSE_PORT` (or `PORT`)                                                                                  | Port Pulse listens on                                                                     | `8000`                  |
| `PULSE_SLURM_BACKEND`                                                                                     | `ssh` for real clusters, `mock` for a simulated one                                       | `ssh` in the image      |
| `PULSE_SSH_KEY_PATH`                                                                                      | An existing private key for the first account (others always get their own)               | `/data/pulse_ed25519`   |
| `PULSE_SSH_KNOWN_HOSTS`                                                                                   | Strict host-key checking against a `known_hosts` file                                     | pin on first use        |
| `PULSE_SSH_CONNECT_TIMEOUT_SECONDS`                                                                       | SSH connection timeout                                                                    | `10`                    |
| `PULSE_SSH_COMMAND_TIMEOUT_SECONDS`                                                                       | Timeout for each command on the cluster                                                   | `30`                    |
| `PULSE_POLL_INTERVAL_LIVE_SECONDS`                                                                        | Poll interval while someone has Pulse open                                                | `10`                    |
| `PULSE_POLL_INTERVAL_IDLE_SECONDS`                                                                        | Poll interval otherwise                                                                   | `60`                    |
| `PULSE_NODE_STATS_INTERVAL_SECONDS`                                                                       | Per-node usage sampling (each sample starts a job step)                                   | `60`                    |
| `PULSE_STALL_MINUTES`, `PULSE_TIME_LIMIT_WARNING_RATIO`, `PULSE_DIVERGE_PERCENT`, `PULSE_PLATEAU_MINUTES` | Default alert thresholds; users can change their own                                      | `15`, `0.9`, `50`, `60` |
| `PULSE_VAPID_PUBLIC_KEY`, `PULSE_VAPID_PRIVATE_KEY`                                                       | Your own push keys (from `pulse gen-vapid`)                                               | generated in `/data`    |
| `PULSE_VAPID_SUBJECT`                                                                                     | Contact sent with push messages                                                           | `PULSE_PUBLIC_URL`      |
| `PULSE_ASSISTANTS_ENABLED`                                                                                | Claude Code and Codex on directly connected clusters                                      | `false`                 |
| `PULSE_ASSISTANT_IDLE_SECONDS`                                                                            | Close idle assistant connections after this long                                          | `900`                   |

The complete list, with comments, is in
[`backend/.env.example`](https://github.com/neecatt/pulse/blob/main/backend/.env.example).

**Command line:** `pulse serve`, `pulse create-user <name>`, `pulse gen-vapid` and
`pulse reset-password <name>`, which also signs that user out everywhere. In
Docker, prefix them with `docker compose exec pulse` (or `docker exec pulse`).

## A public site with a demo

`PULSE_DEMO=true` turns a server into a public site: signed-out visitors get a
landing page with **Try the demo**, which signs them into a temporary guest
account with two simulated clusters (jobs start, fail and diverge within
minutes). Guests are deleted with everything they had a day later. Real
accounts on the same server keep using real Slurm; guests' accounts are always
simulated, so a visitor can't make the server connect anywhere. Combine it with
`PULSE_ALLOW_SIGNUP=true` so visitors can also create real accounts:

```sh
PULSE_DEMO=true
PULSE_ALLOW_SIGNUP=true
PULSE_PUBLIC_URL=https://pulse.example.org
```

Guests can't create teams or invite links, use the agent, or add more than a
few clusters. New guests and sign-ups are limited per address and in total
(300 an hour each). Behind a proxy, set `PULSE_TRUSTED_PROXIES` as narrowly as
your platform allows: with `*`, a client's own `X-Forwarded-For` is believed,
and only the total limits still hold.

Keep your own monitoring on a **separate** instance (its own volume, sign-ups
off), so nothing you own sits on a server strangers can sign up to. Both run the
same image; for example `pulse.example.org` (public, demo) and
`my.pulse.example.org` (private). Sign-ins and passkeys never carry over between
the two: cookies and passkeys are tied to the exact domain.

## Optional cluster assistants

Set `PULSE_ASSISTANTS_ENABLED=true` and restart Pulse to enable the Assistants tab's
Claude/Codex connections. The cluster must use direct SSH and have the chosen CLI
in its login PATH. Users authorize through the provider's native sign-in from
the app, or reuse the cluster's existing sign-in; no API key is required. Keep `/api/assistants/*/stream` unbuffered
at your proxy, like `/api/stream` (the bundled Caddyfile handles both).
See [the assistant guide](assistants.md) for setup, access controls and limitations.

## Backups and upgrades

All state is in the `pulse-data` volume. Back it up with:

```sh
docker compose stop pulse
docker run --rm -v pulse_pulse-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/pulse-backup.tgz -C /data .
docker compose start pulse
```

Upgrade with `docker compose pull && docker compose up -d`. Tags: `latest` is
the newest release, `0.2` follows its patch releases and `0.2.6` never changes;
pin one of the last two for predictable upgrades. Versions with a suffix
(`0.3.0-rc.1`) are pre-releases for testing, and `staging` always points at the
newest build of either kind. While Pulse is below 1.0 the
database schema may change between versions without automatic migration;
release notes say when a fresh database is needed.

## Troubleshooting

- **"Cross-site request blocked" when signing in or pressing buttons:** Pulse
  is behind a proxy it doesn't trust, so it thinks the page is on plain HTTP.
  Set `PULSE_TRUSTED_PROXIES` to the proxy's address, or `*` when the proxy is
  the only way in.
- **Jobs only change after a reload:** the proxy buffers the live update
  stream. Turn off buffering for `/api/stream` (and `/api/assistants/*/stream`).
- **No setup code in the log:** an admin is already set by
  `PULSE_ADMIN_USERNAME` and `PULSE_ADMIN_PASSWORD`, or the database already
  has users. Use `pulse reset-password <name>` to get back in.
- **Accounts, keys or users vanish after a redeploy:** `/data` isn't on a
  persistent volume.
- **"Presented a different host key than before":** the login node's key
  differs from the one pinned on first connect. Check with your centre that the change is
  expected, then remove and re-add the account.
- **No notifications on iPhone or iPad:** add Pulse to the Home Screen and turn
  notifications on from the app opened there (iOS 16.4+), over HTTPS.
- **A passkey isn't offered:** passkeys belong to the exact domain they were
  created on. Use that address, or set `PULSE_PUBLIC_URL` to it.

## Security checklist

- HTTPS in front of Pulse (any of the setups above).
- A long admin password, or the setup-code flow; `PULSE_ALLOW_SIGNUP` off
  unless you want open registration.
- `.env` readable only by you: `chmod 600 .env`. Or use Docker secrets, where a
  file `/run/secrets/pulse_admin_password` sets `PULSE_ADMIN_PASSWORD`.
- Behind any proxy, set `PULSE_TRUSTED_PROXIES` to the proxy's address (or `*`
  when it's the only way in). Otherwise Pulse thinks it's on plain HTTP, and
  sign-in and other buttons fail with "Cross-site request blocked".
- Only expose port 8000 through the proxy. Trust forwarded headers
  (`PULSE_TRUSTED_PROXIES`) only from the proxy, or clients could spoof their
  address and slip past the login rate limit.
- Read [SECURITY.md](https://github.com/neecatt/pulse/blob/main/SECURITY.md) for
  what Pulse protects against and how to report a problem.
