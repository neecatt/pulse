# Security policy

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through GitHub:
**Security → Report a vulnerability** on this repository. Include steps to
reproduce and the version or commit you tested.

You'll get an acknowledgement within a week. Once a fix is released, the report
is published with credit, unless you prefer otherwise.

## Supported versions

Pulse is pre-1.0. Security fixes go into the latest release only.

## Scope

In scope: the Pulse server, the web app, the container image and the login-node
agent. Please don't test against instances you don't own.

## Security model

What Pulse protects, and how, so you can judge it and report anything that
falls short.

- **Sign-in.** Passwords are hashed with scrypt; sessions are random 256-bit
  tokens in an HttpOnly, SameSite=Lax cookie (Secure over HTTPS), stored only as
  hashes. Failed sign-ins are limited per address and per username, sign-ups per
  address. Password changes and password confirmations share the sign-in limits.
  Adding or removing passkeys requires recent authentication; registration and
  confirmation challenges are single-use, expiring and bound to the browser's
  session token hash. Live streams recheck that same credential before each
  update and on idle keepalives, and close after revocation or expiry.
- **Requests.** State-changing requests from other websites are refused (Origin
  check), responses carry a strict Content Security Policy and HSTS, and request
  bodies over 1 MB (16 MB for agent reports) are refused before they're read.
  There's no public API map (`/docs`, `/openapi.json`) and no server banner.
- **Site stats** (admins only) keep daily totals and nothing identifying: no
  cookies, no addresses, no third parties. Visitors are told apart within a day
  by a salted hash kept only in memory.
- **The image** runs as an unprivileged user, keeps `/data` private to it, and
  ships without pip or setuptools, which Pulse doesn't need at runtime.
- **Users are isolated.** Every endpoint returns only the signed-in user's data,
  plus, read-only, the accounts or single jobs a teammate chose to share with a
  team you're both in. Live updates and alerts follow the same rule, job by job.
  Teammates see a shared account only as its owner and cluster, never its
  cluster login (also removed from paths in logs and hyperparameters), host,
  jump host, errors or settings. Only an account's owner can change it or its
  jobs. Team invites are single-use (even under concurrent use), expire after 7
  days and are stored as hashes.
  Each user has their own SSH key, so adding someone else's cluster login gets
  you nowhere. Users who aren't admins can only connect to public internet
  addresses, and push messages only go to the browsers' push services, so a user
  can't point the server at its own network.
- **Demo guests** (`PULSE_DEMO`) only ever get simulated clusters, whatever
  host they type: the server decides, and never opens a connection for them,
  even after `PULSE_DEMO` is switched off. Guests can't create teams or invite
  links (an invite makes a real account even with sign-ups off), use the agent
  (no uploads), or add more than 5 clusters; their clusters are polled only
  while someone is watching. They're limited per address and in total, capped
  at 1,000 alive, and deleted with all their data after a day.
- **Sign-up** (password or passkey) is limited per address and in total, so a
  forged `X-Forwarded-For` behind a permissive proxy can't create accounts in
  bulk. A passkey sign-up creates the account only after the passkey verifies.
  A passkey-only account can add a first password only within 10 minutes of
  signing in, so a stolen session can't be turned into a lasting password.
- **Clusters.** By default, Pulse runs read-only Slurm commands with its own key and pins
  each server's host key on first connect. It ignores `~/.ssh/config` and any
  SSH agent. Values from the cluster are quoted, and paths must be absolute
  before they reach a command. The agent runs no shell, reads only files it
  found itself (no symlinks), and sends raw output for the server to parse.
- **Optional assistants** are off by default. Only an owned, real direct SSH
  account can run Codex's app-server or Claude Code's headless mode; demo
  guests, shared accounts and reporting agents cannot. A fresh password or
  passkey confirmation is required to open connections or resume chats. Each
  browser must explicitly connect before reading assistant state/history or
  sending prompts and approvals; another browser's connection grants no access.
  Codex's official device-login links/codes are shown in Pulse; its OAuth tokens
  and transcripts stay with the cluster CLI. Claude uses its own CLI login;
  an optional one-time authorization code is passed to that CLI without storage,
  and sign-in links are allowlisted. Both run with Pulse as their permission
  prompt (Codex `untrusted`, Claude `default` mode): command, file-change and tool
  approval cards require a user response, and unsupported request types fail
  closed. Normal reads and permitted
  edits still follow the native workspace/permission rules. Assistants have the
  SSH user's permissions when actions are approved. This opt-in feature changes
  Pulse's default read-only cluster model; see `docs/assistants.md`.
- **Data at rest.** The data directory is readable by Pulse's user only; SSH and
  push keys are created with mode 600. The container runs Pulse as an
  unprivileged user.

Known limits:

- With `PULSE_TRUSTED_PROXIES=*`, client addresses come from `X-Forwarded-For`.
  If your proxy passes that header through from clients instead of setting it,
  the per-address limits can be dodged (the per-username limit still applies).
- Ten wrong passwords for a username lock password sign-in for that username for
  15 minutes, whoever typed them. Passkeys keep working.
- An admin can connect Pulse to any address, including private networks:
  admins are trusted with the server.
