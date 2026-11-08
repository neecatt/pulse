# Claude Code and Codex on your cluster

Pulse can connect Claude Code or Codex to a linked cluster from your phone.
Codex has an embedded chat interface; Claude uses its official Remote Control
interface in the Claude app or browser. Your laptop does not need to stay on. This uses the cluster's
Codex CLI and its existing local conversation history, including chats started
from an SSH terminal.

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
a turn is active. A fresh Pulse password or passkey confirmation is required to
open a connection or resume a chat after ten minutes without authentication.
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

## Claude Code: native sign-in and Remote Control

Select **Claude Code** beside Codex. Pulse lists recent saved Claude conversations
from the cluster. **Continue in Claude** resumes a selected local conversation;
for a new one, enter its project directory and press **Connect Claude**. Pulse
starts the unmodified CLI with `--remote-control`, `--resume` when appropriate,
and manual permissions. It appends HPC guidance to use Slurm, show resource
requests and ask before submitting jobs; Claude's existing project instructions
and native permission rules still apply.

If the CLI is not signed in, press **Sign in on cluster**. Pulse runs the native
`claude auth login` command and displays its official authorization link. Complete
that page in your phone browser. If Claude shows a one-time authorization code,
enter it in Pulse's **One-time code from Claude** field; Pulse forwards it to the
CLI's standard input and discards it. The CLI owns the OAuth exchange and token
storage. Pulse does not offer a separate Claude OAuth client or SDK subscription
login, and never reads or copies provider tokens.

Claude may ask you to trust the project or enable Remote Control. The setup
panel relays those native prompts with Yes/Enter/arrow controls. Pulse never
answers them automatically. Once ready, **Open in Claude** opens the official
`claude.ai/code/...` session on your phone. Sign in there with the same Claude
account. Prompts, history, file diffs and command approvals are handled by
Claude's own UI, while execution and files stay on the HPC. Pulse continues
monitoring submitted Slurm jobs in the usual way.

Requirements: a current Claude Code CLI, an eligible Claude subscription and
Remote Control enabled for your account/organization. API keys and setup-token
credentials do not enable Remote Control; the CLI needs its native subscription
sign-in. CLI login or project setup can be completed through the Pulse panel,
so a laptop is not required. No extra Python packages are installed on the
cluster; a bounded stdlib-only Python 3 script reads recent transcript metadata,
not credential files. It scans at most 128 project directories and 512 candidate
transcripts and returns up to 50 recent conversations. Custom config directories
reported by the current CLI are respected.

Closing Pulse keeps Claude's Remote Control process running. It does not idle
out while you work in Claude's own UI. Disconnecting, restarting Pulse, losing
SSH or revoking the owning Pulse sign-in stops the process; saved transcripts
and submitted Slurm jobs remain. Reconnect to resume. Inactive sign-in/setup
processes expire after the configured assistant idle timeout. Pulse's audit log
records native sign-in and remote-session starts/stops; Claude owns the detailed
conversation/tool history and approval UI. Pulse retains setup output only until
the remote link is ready, then drains it without retaining a second transcript.
Only HTTPS links to the provider's allowed hosts are displayed; Claude session
links must be on `claude.ai/code/`. No third-party page is embedded in Pulse.

Provider references:

- [Codex app-server](https://learn.chatgpt.com/docs/app-server)
- [Claude Remote Control](https://code.claude.com/docs/en/remote-control)
- [Claude authentication](https://code.claude.com/docs/en/authentication)
- [Claude Code integration conditions](https://code.claude.com/docs/en/legal-and-compliance)
