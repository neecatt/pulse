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
  address. Passkeys use single-use, expiring challenges.
- **Requests.** State-changing requests from other websites are refused (Origin
  check), responses carry a strict Content Security Policy and HSTS, and request
  bodies over 1 MB (16 MB for agent reports) are refused before they're read.
- **Users are isolated.** Every endpoint returns only the signed-in user's data,
  plus, read-only, the accounts a teammate chose to share with their team. Only
  an account's owner can change it or its jobs. Team invites are single-use,
  expire after 7 days and are stored as hashes.
  Each user has their own SSH key, so adding someone else's cluster login gets
  you nowhere. Users who aren't admins can only connect to public internet
  addresses, and push messages only go to the browsers' push services, so a user
  can't point the server at its own network.
- **Clusters.** Pulse runs read-only Slurm commands with its own key and pins
  each server's host key on first connect. It ignores `~/.ssh/config` and any
  SSH agent. Values from the cluster are quoted, and paths must be absolute
  before they reach a command. The agent runs no shell, reads only files it
  found itself (no symlinks), and sends raw output for the server to parse.
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
