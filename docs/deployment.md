# Deploying Pulse

Pulse ships as one container image, [`neecat/pulse`](https://hub.docker.com/r/neecat/pulse)
on Docker Hub (multi-architecture: amd64 and arm64). Use `latest` or a
version tag such as `0.2.2`. It runs on any Docker host, and on
container platforms that set a `PORT` variable: Pulse listens on it. It serves the web app and the API on
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

## 3. Without Docker

```sh
git clone https://github.com/neecatt/pulse.git /opt/pulse && cd /opt/pulse
make install && (cd frontend && bun run build)
cp backend/.env.example backend/.env && chmod 600 backend/.env   # then edit it
sudo cp deploy/pulse.service /etc/systemd/system/ && sudo systemctl enable --now pulse
```

Put a reverse proxy with HTTPS in front of `127.0.0.1:8000`, for example Caddy
with `deploy/Caddyfile` (`PULSE_UPSTREAM=127.0.0.1:8000`). The proxy must not
buffer `/api/stream`, the live update stream.

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
  its public URL before copying the command.

Before adding accounts, check your centre's rules on automated Slurm queries.
Pulse runs `sacct` every 10 s while you're watching (adjustable in Settings),
and once a minute a short `srun --overlap` step in each running job to sample
CPU and GPU usage.

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

Keep your own monitoring on a **separate** instance (its own volume, sign-ups
off), so nothing you own sits on a server strangers can sign up to. Both run the
same image; for example `pulse.example.org` (public, demo) and
`my.pulse.example.org` (private). Sign-ins and passkeys never carry over between
the two: cookies and passkeys are tied to the exact domain.

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
- Behind any proxy, set `PULSE_TRUSTED_PROXIES` to the proxy's address (or `*`
  when it's the only way in). Otherwise Pulse thinks it's on plain HTTP, and
  sign-in and other buttons fail with "Cross-site request blocked".
- Only expose port 8000 through the proxy. Trust forwarded headers
  (`PULSE_TRUSTED_PROXIES`) only from the proxy, or clients could spoof their
  address and slip past the login rate limit.
