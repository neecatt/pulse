import { describe, expect, it } from "vitest";

import { accountLabel } from "./accounts";

describe("accountLabel", () => {
  it("names your own account by its login", () => {
    expect(accountLabel({ username: "jdoe", cluster: "LUMI", owner: null })).toBe("jdoe@LUMI");
  });

  it("names a teammate's account by owner and cluster, never the cluster login", () => {
    expect(accountLabel({ username: "jdoe", cluster: "LUMI", owner: "alice" })).toBe(
      "alice · LUMI",
    );
  });
});
