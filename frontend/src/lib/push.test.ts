import { describe, expect, it } from "vitest";

import { base64UrlToBytes } from "./push";

describe("base64UrlToBytes", () => {
  it("decodes unpadded base64url", () => {
    // 0xfb 0xff 0xbf encodes to "+/+/" in base64 and "-_-_" in base64url.
    expect([...base64UrlToBytes("-_-_")]).toEqual([0xfb, 0xff, 0xbf]);
    expect([...base64UrlToBytes("AQ")]).toEqual([1]);
  });
});
