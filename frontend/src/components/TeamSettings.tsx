import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import {
  useCreateInvite,
  useCreateTeam,
  useDeleteTeam,
  useLeaveTeam,
  useRemoveMember,
  useRenameTeam,
  useRevokeInvite,
  useSetTeamAlerts,
  useTeams,
} from "@/api/queries";
import type { OwnedTeam, TeamMembership } from "@/api/types";
import { formatAgo, formatDateTime } from "@/lib/format";

import { Button } from "./Button";
import { CopyButton } from "./CopyButton";
import { Card, Section } from "./Section";
import { SettingRow } from "./SettingRow";
import { Toggle } from "./Toggle";

const inputClass =
  "h-9 w-full rounded-md border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

/** Your team (members, invites) and the teams you're in. */
export function TeamSettings() {
  const { data } = useTeams();
  if (!data) return null;
  return (
    <Section title="Team">
      <div className="space-y-4">
        {data.memberships.map((m) => (
          <Membership key={m.team_id} membership={m} />
        ))}
        {data.owned ? <OwnTeam team={data.owned} /> : <CreateTeam />}
      </div>
    </Section>
  );
}

function CreateTeam() {
  const create = useCreateTeam();
  const [name, setName] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim()) create.mutate(name.trim());
  };
  return (
    <Card className="space-y-3 p-4">
      <div>
        <div className="text-sm">Share your runs with your lab</div>
        <div className="text-xs text-muted-foreground">
          Invite people with a link and choose which accounts they see. They follow those jobs and
          training curves live, read-only.
        </div>
      </div>
      <form onSubmit={submit} className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Team name, e.g. Vision lab"
          maxLength={64}
          aria-label="Team name"
          className={inputClass}
        />
        <Button type="submit" disabled={create.isPending || !name.trim()}>
          Create team
        </Button>
      </form>
      {create.error && <p className="text-xs text-fail">{create.error.message}</p>}
    </Card>
  );
}

function OwnTeam({ team }: { team: OwnedTeam }) {
  const remove = useDeleteTeam();
  const removeMember = useRemoveMember();
  const revoke = useRevokeInvite();
  return (
    <Card className="divide-y">
      <TeamName team={team} />
      <InviteRow />
      {team.members.map((m) => (
        <SettingRow key={m.user_id} label={m.username} hint={`Joined ${formatAgo(m.joined_at)}`}>
          <Button
            variant="ghost"
            disabled={removeMember.isPending}
            onClick={() => {
              if (confirm(`Remove ${m.username} from ${team.name}? They lose access at once.`)) {
                removeMember.mutate(m.user_id);
              }
            }}
          >
            Remove
          </Button>
        </SettingRow>
      ))}
      {team.invites.map((i) => (
        <SettingRow
          key={i.id}
          label="Unused invite link"
          hint={`Created ${formatAgo(i.created_at)} · expires ${formatDateTime(i.expires_at)}`}
        >
          <Button variant="ghost" disabled={revoke.isPending} onClick={() => revoke.mutate(i.id)}>
            Revoke
          </Button>
        </SettingRow>
      ))}
      <SettingRow
        label="Delete team"
        hint="Members lose access, and your accounts stop being shared."
      >
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => {
            if (confirm(`Delete ${team.name}? Members lose access to your jobs at once.`)) {
              remove.mutate(undefined);
            }
          }}
        >
          Delete
        </Button>
      </SettingRow>
    </Card>
  );
}

function TeamName({ team }: { team: OwnedTeam }) {
  const rename = useRenameTeam();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(team.name);
  const count = team.members.length;
  const hint = (
    <>
      {count === 0 ? "No members yet" : `${count} member${count === 1 ? "" : "s"}`} · they see the
      accounts you share on the{" "}
      <Link to="/accounts" className="underline underline-offset-2">
        Accounts
      </Link>{" "}
      page
    </>
  );

  if (editing) {
    return (
      <form
        className="flex gap-2 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) rename.mutate(name.trim(), { onSuccess: () => setEditing(false) });
        }}
      >
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={64}
          aria-label="Team name"
          className={inputClass}
        />
        <Button type="submit" disabled={rename.isPending || !name.trim()}>
          Save
        </Button>
        <Button variant="ghost" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </form>
    );
  }
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 p-4 compact:py-3">
      <div className="min-w-0">
        <div className="text-sm">{team.name}</div>
        <div className="text-xs text-muted-foreground">{hint}</div>
      </div>
      <Button variant="ghost" onClick={() => setEditing(true)}>
        Rename
      </Button>
    </div>
  );
}

/** Create a single-use invite link; it's shown once, so copy it right away. */
function InviteRow() {
  const invite = useCreateInvite();
  const link = invite.data ? `${window.location.origin}/join/${invite.data.token}` : null;
  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <div className="text-sm">Invite someone</div>
          <div className="text-xs text-muted-foreground">
            A link for one person, valid for 7 days. They can create an account with it.
          </div>
        </div>
        <Button
          variant="ghost"
          disabled={invite.isPending}
          onClick={() => invite.mutate(undefined)}
        >
          {link ? "New link" : "Create invite link"}
        </Button>
      </div>
      {link && (
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded-md border bg-muted px-3 py-2 font-mono text-xs">
            {link}
          </code>
          <CopyButton text={link} label="Copy link" />
        </div>
      )}
      {invite.error && <p className="text-xs text-fail">{invite.error.message}</p>}
    </div>
  );
}

function Membership({ membership }: { membership: TeamMembership }) {
  const setAlerts = useSetTeamAlerts();
  const leave = useLeaveTeam();
  return (
    <Card className="divide-y">
      <SettingRow
        label={membership.name}
        hint={`Shared by ${membership.owner} · you can view, not change, their jobs`}
      >
        <Button
          variant="ghost"
          disabled={leave.isPending}
          onClick={() => {
            if (confirm(`Leave ${membership.name}? You'll stop seeing its shared jobs.`)) {
              leave.mutate(membership.team_id);
            }
          }}
        >
          Leave
        </Button>
      </SettingRow>
      <SettingRow
        label="Alerts for this team's jobs"
        hint="Push notifications, using your alert choices below"
      >
        <Toggle
          label={`Alerts for ${membership.name}`}
          checked={membership.alerts}
          onChange={(alerts) => setAlerts.mutate({ teamId: membership.team_id, alerts })}
        />
      </SettingRow>
    </Card>
  );
}
