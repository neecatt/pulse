import { describe, expect, it } from "vitest";

import { accountLabel } from "./accounts";

describe("accountLabel", () => {
  it("names the owner of a teammate's account", () => {
    expect(accountLabel({ username: "jdoe", cluster: "LUMI", owner: null })).toBe("jdoe@LUMI");
    expect(accountLabel({ username: "jdoe", cluster: "LUMI", owner: "alice" })).toBe(
      "alice · jdoe@LUMI",
    );
  });
});
