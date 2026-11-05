import type { Account } from "@/api/types";

/** "jdoe@LUMI", or "alice · jdoe@LUMI" for an account a teammate shares with you. */
export function accountLabel(account: Pick<Account, "username" | "cluster" | "owner">): string {
  const label = `${account.username}@${account.cluster}`;
  return account.owner ? `${account.owner} · ${label}` : label;
}
