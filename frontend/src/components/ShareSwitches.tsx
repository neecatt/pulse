import type { ShareTeam } from "@/api/queries";
import { Toggle } from "@/components/Toggle";

interface ShareSwitchesProps {
  teams: ShareTeam[];
  /** Ids of the teams it's shared with. */
  shared: number[];
  /** What's being shared, for screen readers: "jdoe@LUMI", "train-vit". */
  what: string;
  onChange: (teamId: number, shared: boolean) => void;
  disabled?: boolean;
}

/** One switch per team you're in: who sees this, read-only. Teams you share all
 * your jobs with show as on and locked; that's changed in Settings → Team. */
export function ShareSwitches({
  teams,
  shared,
  what,
  onChange,
  disabled = false,
}: ShareSwitchesProps) {
  return (
    <>
      {teams.map((team) => (
        <label
          key={team.id}
          className="flex items-center gap-2 text-xs text-muted-foreground"
          title={
            team.shareAll
              ? `All your jobs are shared with ${team.name} (Settings → Team)`
              : `Let ${team.name} see ${what}, read-only`
          }
        >
          <span className="max-w-32 truncate">{team.name}</span>
          <Toggle
            label={`Share ${what} with ${team.name}`}
            checked={team.shareAll || shared.includes(team.id)}
            onChange={(on) => onChange(team.id, on)}
            disabled={disabled || team.shareAll}
          />
        </label>
      ))}
    </>
  );
}
