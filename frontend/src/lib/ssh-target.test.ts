import { describe, expect, it } from "vitest";

import { describeSshTarget, parseSshTarget } from "./ssh-target";

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
    [
      "ssh -J gateway.example.edu jdoe42@alex.example.edu",
      {
        username: "jdoe42",
        host: "alex.example.edu",
        port: 22,
        jump: { host: "gateway.example.edu", port: 22 },
      },
    ],
    [
      "ssh -J gate@bastion.org:2222 -p 2200 jdoe@node.org",
      {
        username: "jdoe",
        host: "node.org",
        port: 2200,
        jump: { host: "bastion.org", port: 2222, username: "gate" },
      },
    ],
    [
      "ssh -o ProxyJump=bastion.org jdoe@node.org",
      { username: "jdoe", host: "node.org", port: 22, jump: { host: "bastion.org", port: 22 } },
    ],
    [
      "ssh -J jdoe@bastion.org jdoe@node.org", // same user: not repeated
      { username: "jdoe", host: "node.org", port: 22, jump: { host: "bastion.org", port: 22 } },
    ],
  ])("%s", (input, expected) => {
    expect(parseSshTarget(input)).toEqual(expected);
  });

  it.each([
    "",
    "ssh",
    "lumi.csc.fi",
    "jdoe@",
    "j doe@host",
    "jdoe@host:99999",
    "x;rm@host",
    "ssh -J a.org,b.org jdoe@host.org", // chains of jump hosts aren't supported
    "ssh -J 'bad host' jdoe@host.org",
  ])("rejects %j", (input) => {
    expect(parseSshTarget(input)).toBeNull();
  });
});

describe("describeSshTarget", () => {
  it("shows the login, port and jump host", () => {
    const target = parseSshTarget("ssh -J gate@bastion.org:2222 -p 2200 jdoe@node.org");
    expect(target && describeSshTarget(target)).toBe(
      "jdoe on node.org:2200 via gate@bastion.org:2222",
    );
    const simple = parseSshTarget("jdoe@node.org");
    expect(simple && describeSshTarget(simple)).toBe("jdoe on node.org");
  });
});
