import { describe, expect, it } from "vitest";

import { parseSshTarget } from "./ssh-target";

describe("parseSshTarget", () => {
  it.each([
    ["jdoe@lumi.csc.fi", { username: "jdoe", host: "lumi.csc.fi", port: 22 }],
    ["  ssh jdoe@LUMI.csc.fi ", { username: "jdoe", host: "lumi.csc.fi", port: 22 }],
    ["ssh -p 2222 jdoe@host.org", { username: "jdoe", host: "host.org", port: 2222 }],
    ["jdoe@host.org:2200", { username: "jdoe", host: "host.org", port: 2200 }],
    ["ssh -l jdoe host.org", { username: "jdoe", host: "host.org", port: 22 }],
    ["ssh -i ~/.ssh/id jdoe@host.org", { username: "jdoe", host: "host.org", port: 22 }],
    ["ssh://jdoe@host.org:2222", { username: "jdoe", host: "host.org", port: 2222 }],
    ["ssh jdoe@host.org squeue", { username: "jdoe", host: "host.org", port: 22 }],
  ])("%s", (input, expected) => {
    expect(parseSshTarget(input)).toEqual(expected);
  });

  it.each(["", "ssh", "lumi.csc.fi", "jdoe@", "j doe@host", "jdoe@host:99999", "x;rm@host"])(
    "rejects %j",
    (input) => {
      expect(parseSshTarget(input)).toBeNull();
    },
  );
});
