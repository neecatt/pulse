// Dotted (Hydra, Lightning) or slashed keys: "model.params.lr", "optim/lr".
const SEPARATOR = /[./]/;

export interface HparamGroup {
  /** First key segment ("trainer"), or null for keys that stand alone. */
  name: string | null;
  /** Full keys, in config order, with their label inside the group. */
  rows: { key: string; label: string }[];
}

/**
 * Hyperparameters grouped by their first key segment, the way config files
 * nest them: "trainer.precision" is "precision" in the "trainer" group. Keys
 * without a segment, and groups of a single key, go together first.
 */
export function groupHparams(keys: string[]): HparamGroup[] {
  // A config wrapped in one top-level key ({"config": {...}}) groups by the
  // level below it, or every key would land in one group.
  const wrapper = sharedFirstSegment(keys);
  if (wrapper !== null) {
    return groupHparams(keys.map((key) => key.slice(wrapper.length))).map((group) => ({
      ...group,
      rows: group.rows.map((row) => ({ ...row, key: wrapper + row.key })),
    }));
  }
  const groups = new Map<string, string[]>();
  for (const key of keys) {
    const match = SEPARATOR.exec(key);
    const name = match && match.index > 0 ? key.slice(0, match.index) : "";
    groups.set(name, [...(groups.get(name) ?? []), key]);
  }
  const loose = [...groups].filter(([name, group]) => name === "" || group.length === 1);
  const result: HparamGroup[] = [...groups]
    .filter(([name, group]) => name !== "" && group.length > 1)
    .map(([name, group]) => ({
      name,
      rows: group.map((key) => ({ key, label: key.slice(name.length + 1) })),
    }));
  const standalone = loose.flatMap(([, group]) => group);
  if (standalone.length) {
    result.unshift({ name: null, rows: standalone.map((key) => ({ key, label: key })) });
  }
  return result;
}

/** "config." when every key (two or more) starts with that same segment. */
function sharedFirstSegment(keys: string[]): string | null {
  const first = keys[0];
  const match = first === undefined ? null : SEPARATOR.exec(first);
  if (!first || !match || match.index === 0 || keys.length < 2) return null;
  const prefix = first.slice(0, match.index + 1);
  return keys.every((key) => key.startsWith(prefix) && key.length > prefix.length) ? prefix : null;
}
