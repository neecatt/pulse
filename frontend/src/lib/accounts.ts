import type { Account } from "@/api/types";

/** "jdoe@LUMI", or "alice · LUMI" for a teammate's account (their cluster login stays private). */
export function accountLabel(account: Pick<Account, "username" | "cluster" | "owner">): string {
  return account.owner
    ? `${account.owner} · ${account.cluster}`
    : `${account.username}@${account.cluster}`;
}
