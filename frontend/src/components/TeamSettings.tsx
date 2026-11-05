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
  useTeams,
  useUpdateMembership,
} from "@/api/queries";
import type { OwnedTeam, TeamMembership } from "@/api/types";
import { formatAgo, formatDateTime } from "@/lib/format";

import { Button } from "./Button";
import { useConfirm } from "@/hooks/use-confirm";
import { CopyButton } from "./CopyButton";
import { Card, Section } from "./Section";
import { SettingRow } from "./SettingRow";
import { Toggle } from "./Toggle";

const inputClass =
  "h-8 w-full min-w-0 rounded-md border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

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
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 p-4 compact:py-3">
        <div className="min-w-0 flex-1">
          <div className="text-sm">Share your runs with your lab</div>
          <div className="text-xs text-muted-foreground">
            Invite people with a link. They follow the jobs you share, live and read-only.
          </div>
        </div>
        <form onSubmit={submit} className="flex w-full gap-2 sm:w-auto">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Team name"
            maxLength={64}
            aria-label="Team name"
            className={`${inputClass} sm:w-48`}
          />
          <Button type="submit" className="shrink-0" disabled={create.isPending || !name.trim()}>
            Create team
          </Button>
        </form>
      </div>
      {create.error && <p className="px-4 pb-4 text-xs text-fail">{create.error.message}</p>}
    </Card>
  );
}

function OwnTeam({ team }: { team: OwnedTeam }) {
  const remove = useDeleteTeam();
  const removeMember = useRemoveMember();
  const revoke = useRevokeInvite();
  const confirm = useConfirm();
  return (
    <Card className="divide-y">
      <TeamName team={team} />
      <InviteRow />
      {team.members.map((m) => (
        <SettingRow key={m.user_id} label={m.username} hint={`Joined ${formatAgo(m.joined_at)}`}>
          <Button
            variant="ghost"
            disabled={removeMember.isPending}
            onClick={() =>
              confirm.ask({
                title: `Remove ${m.username}?`,
                description: `They stop seeing everything shared with ${team.name} at once, and what they shared is withdrawn.`,
                action: "Remove",
                danger: true,
                onConfirm: () => removeMember.mutate(m.user_id),
              })
            }
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
      <ShareAllRow teamId={team.id} teamName={team.name} shareAll={team.share_all} />
      <AlertsRow teamId={team.id} teamName={team.name} alerts={team.alerts} />
      <SettingRow label="Delete team" hint="Members lose access, and nothing stays shared.">
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() =>
            confirm.ask({
              title: `Delete ${team.name}?`,
              description:
                "Members lose access to everything shared with the team at once. Your jobs and accounts stay as they are.",
              action: "Delete team",
              danger: true,
              onConfirm: () => remove.mutate(undefined),
            })
          }
        >
          Delete
        </Button>
      </SettingRow>
      {confirm.dialog}
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
      {count === 0 ? "No members yet" : `${count} member${count === 1 ? "" : "s"}`} · pick single
      accounts on the{" "}
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

/** Share every job of every account you have (and add later) with a team. */
function ShareAllRow(props: { teamId: number; teamName: string; shareAll: boolean }) {
  const update = useUpdateMembership();
  return (
    <SettingRow
      label="Share all my jobs"
      hint="Every account you have, and any you add later. Teammates see them read-only."
    >
      <Toggle
        label={`Share all my jobs with ${props.teamName}`}
        checked={props.shareAll}
        disabled={update.isPending}
        onChange={(shareAll) => update.mutate({ teamId: props.teamId, share_all: shareAll })}
      />
    </SettingRow>
  );
}

function AlertsRow(props: { teamId: number; teamName: string; alerts: boolean }) {
  const update = useUpdateMembership();
  return (
    <SettingRow
      label="Alerts for teammates' jobs"
      hint="Push notifications, using your alert choices below"
    >
      <Toggle
        label={`Alerts for ${props.teamName}`}
        checked={props.alerts}
        onChange={(alerts) => update.mutate({ teamId: props.teamId, alerts })}
      />
    </SettingRow>
  );
}

function Membership({ membership }: { membership: TeamMembership }) {
  const leave = useLeaveTeam();
  const confirm = useConfirm();
  return (
    <Card className="divide-y">
      <SettingRow
        label={membership.name}
        hint={`Run by ${membership.owner} · teammates' shared jobs are view-only`}
      >
        <Button
          variant="ghost"
          disabled={leave.isPending}
          onClick={() =>
            confirm.ask({
              title: `Leave ${membership.name}?`,
              description:
                "You stop seeing its shared jobs at once, and what you shared with it is withdrawn.",
              action: "Leave team",
              danger: true,
              onConfirm: () => leave.mutate(membership.team_id),
            })
          }
        >
          Leave
        </Button>
      </SettingRow>
      <ShareAllRow
        teamId={membership.team_id}
        teamName={membership.name}
        shareAll={membership.share_all}
      />
      <AlertsRow
        teamId={membership.team_id}
        teamName={membership.name}
        alerts={membership.alerts}
      />
      {confirm.dialog}
    </Card>
  );
}
