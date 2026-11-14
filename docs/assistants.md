# Claude Code and Codex on your cluster

Pulse can connect Claude Code or Codex to a linked cluster from your phone and
chat with it inside Pulse: send prompts, watch replies stream in, and approve
commands and file changes. Your laptop does not need to stay on. Pulse uses the
cluster's own CLI and its existing local conversation history, including chats
started from an SSH terminal.

## Enable

1. Install a current Codex CLI on the cluster, available in the account's login
   PATH. Pulse uses `codex app-server --listen stdio://` over its existing SSH
   connection; it does not install software on the cluster.
2. Link that cluster under **Accounts** using **Direct SSH**. Jump hosts work.
3. Set `PULSE_ASSISTANTS_ENABLED=true` on the Pulse server and restart it.
4. Open **Assistants**, select the cluster and press **Connect Codex**.

If Codex is already signed in on the cluster, Pulse uses that sign-in. Otherwise
Pulse shows **Continue with ChatGPT** and a one-time code. Open the link on your
phone, enter the code and authorize Codex. Return to Pulse; the conversation list
appears automatically. You may need to enable device-code login in ChatGPT's
security settings. No API key is required. Sign-in happens through the official
Codex device flow; Pulse never reads or copies the cluster's credential file or
receives its OAuth tokens.

## Continue or start a chat

Select a saved conversation to read it, then **Continue this conversation** to
work in its saved project directory. Reading history does not resume or execute
anything. **New chat** asks for an absolute project path already on the cluster.

Send a prompt such as “Review the training script and submit it on 4 GPUs for
12 hours.” Replies and tool output stream into the chat. Codex's command and
file-change approval requests appear as cards with **Approve once** and
**Decline**; questions can be answered in place. Unsupported request types fail
closed. Approval requests expire after ten minutes and are declined.

Under the prompt, pick the **model** and **thinking level** for the next message.
The lists come from the cluster's CLI, so they show exactly what your plan offers
there, and only the thinking levels the chosen model supports. Pulse remembers
your choice per assistant on that device. Codex applies it from the next turn.
Claude fixes the thinking level when it starts, so changing either restarts
that conversation's CLI with `--resume` and the new `--model`/`--effort`; the
conversation and its context carry on.

Pulse resumes threads with `untrusted` command approvals, a `workspace-write`
sandbox and the user as reviewer. Normal safe reads and permitted workspace
edits follow Codex's rules; this is not a separate per-command policy engine.
Codex is instructed to show the batch script and resources before submission,
use Slurm for heavy computation, and report job IDs. Review its requests and
scripts before approving. The assistant has the permissions of your cluster
login; the project directory is not an operating-system account boundary.

Submitted jobs appear in **Jobs** on the normal live polling cycle. Pulse does
not guess which jobs belong to a chat. Closing Pulse leaves active assistant
work running on the server; returning reattaches to its live state. Conversation
history stays in Codex's own storage on the cluster. Pulse restarts or lost SSH
connections can interrupt an active turn; reconnect and resume the saved chat.
Already submitted Slurm jobs continue independently.

**Stop turn** interrupts Codex. **Disconnect** closes the assistant connection
without signing Codex out of the cluster or deleting its saved chats. Idle
connections close after `PULSE_ASSISTANT_IDLE_SECONDS` (default 900), except while
a turn is active. Opening a connection needs a Pulse sign-in, password or passkey
confirmation from the last eight hours; once connected, that browser's chats
don't ask again until the connection ends.
Each browser must explicitly connect with its own confirmed Pulse session before
it can read Codex history, see live state or respond to approvals. Confirmation
alone does not inherit another browser's open connection. Claude setup and handoff
links are likewise available only to the Pulse session that opened them.

## Access and data

Only the owner of a real direct SSH account can connect or read its assistant
history. Shared team accounts, demo guests and simulated clusters cannot. The
login-node reporting agent remains one-way and read-only. Pulse reuses its
per-user SSH key, host pins, public-address checks and jump-host connection.

The activity list records who connected, resumed a chat, sent a prompt,
interrupted work or accepted/declined an approval, with time and conversation ID.
Owners see their own records; admins see all records. Prompts, command output
and provider credentials are not written to that audit log. Live text is held
in bounded memory; persistent transcripts belong to Codex on the cluster.
Revoked Pulse sessions and removed accounts lose their connection access;
active connections are checked every 15 seconds. Streams also check their original
session credential before sending updates or keepalives, so deleting and recreating
a session cannot restore a revoked stream or inherit assistant access.

## Claude Code

Select **Claude Code** beside Codex and press **Connect Claude**. Pulse lists the
cluster's recent Claude conversations by their titles; open one to read it, then
**Continue this conversation**, or start a **New chat** in a project directory.
The chat, approvals and audit log work as described above for Codex.

Each open conversation runs the unmodified CLI on the cluster in headless mode
(`claude -p` with stream-json input and output), resumed with `--resume` or
started with a new session id, in the conversation's project directory. Pulse is
its permission prompt (`--permission-prompt-tool stdio`, `--permission-mode
default`): every tool use that your own Claude permission rules don't already
allow becomes an approval card. Commands and file edits show what will run or
change; Claude's multiple-choice questions and plans can be answered in place.
Declining tells Claude you declined. Pulse appends the same HPC guidance as for
Codex; Claude's project instructions and settings still apply. Claude's private
reasoning is never shown or stored by Pulse.

**Sign-in.** If Claude Code isn't signed in on the cluster, press **Sign in on
cluster**. Pulse runs the native `claude auth login` and shows its official
authorization link; if Claude shows a one-time code, enter it in Pulse and it is
passed to the CLI's standard input and discarded. The CLI owns the OAuth
exchange and token storage; Pulse never reads or copies credentials. An
`ANTHROPIC_API_KEY` (or Bedrock/Vertex settings) in the cluster's login
environment works too.

**Which login to use.** Anthropic's terms allow you to sign in to the unmodified
Claude Code with your own subscription, including where a platform runs it for
you, but say products built on Claude Code should use API keys and must not route
requests through subscription credentials on users' behalf
([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)).
On a server only you use, signing in with your own subscription is ordinary use
of your own CLI. On a shared or public Pulse server, have each person use their
own API key on their own cluster account.

Conversations stay in Claude's own storage on the cluster, so they also appear in
`claude --resume` over SSH. Up to eight conversations can be open at once per
cluster; the oldest idle one closes when you open another. Disconnecting,
restarting Pulse, idling for `PULSE_ASSISTANT_IDLE_SECONDS` or losing SSH stops
the CLI processes; saved transcripts and submitted Slurm jobs remain. A bounded,
stdlib-only Python 3 script lists conversations and reads one conversation's
recent messages; it never reads credential files. It considers the 128 most
recently changed project directories and the 512 newest transcripts in them, and
returns up to 50 recent conversations. Custom config directories reported by the
current CLI are respected.

Provider references:

- [Codex app-server](https://learn.chatgpt.com/docs/app-server)
- [Claude Code headless mode](https://code.claude.com/docs/en/headless)
- [Claude authentication](https://code.claude.com/docs/en/authentication)
- [Claude Code integration conditions](https://code.claude.com/docs/en/legal-and-compliance)
