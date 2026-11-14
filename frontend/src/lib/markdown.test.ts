import { describe, expect, it } from "vitest";

import { parseInline, parseMarkdown, slugify } from "./markdown";

describe("markdown for the docs pages", () => {
  it("parses headings with GitHub's anchors", () => {
    const [heading] = parseMarkdown("## 1. Public server (Docker + Caddy)");
    expect(heading).toMatchObject({
      kind: "heading",
      level: 2,
      id: "1-public-server-docker--caddy",
    });
    expect(slugify("Container platforms (Railway, Render, Fly.io)")).toBe(
      "container-platforms-railway-render-flyio",
    );
  });

  it("joins wrapped paragraph lines and keeps code blocks verbatim", () => {
    expect(parseMarkdown("One\nline.\n\n```sh\ndocker run \\\n  pulse\n```")).toEqual([
      { kind: "paragraph", text: [{ kind: "text", text: "One line." }] },
      { kind: "code", text: "docker run \\\n  pulse" },
    ]);
  });

  it("nests paragraphs and code inside list items", () => {
    const [list] = parseMarkdown("1. Set:\n\n   ```sh\n   A=1\n   ```\n\n   Done.\n2. Deploy.");
    expect(list).toMatchObject({ kind: "list", ordered: true });
    expect(list?.kind === "list" && list.items.map((item) => item.map((b) => b.kind))).toEqual([
      ["paragraph", "code", "paragraph"],
      ["paragraph"],
    ]);
  });

  it("continues list items over wrapped lines", () => {
    const [list] = parseMarkdown("- **Agent:** for 2FA\n  clusters.\n- Direct.\n\nAfter.");
    expect(list?.kind === "list" && list.items.length).toBe(2);
  });

  it("parses pipe tables", () => {
    const [table] = parseMarkdown("| A | B |\n| - | --- |\n| `x` | y |");
    expect(table).toMatchObject({
      kind: "table",
      rows: [[[{ kind: "code", text: "x" }], [{ text: "y" }]]],
    });
  });

  it("parses inline code, bold, italics and links, but not snake_case", () => {
    expect(
      parseInline("**Go** to [the guide](a.md#b), `PULSE_X`, _(unset)_ or snake_case_name"),
    ).toEqual([
      { kind: "strong", children: [{ kind: "text", text: "Go" }] },
      { kind: "text", text: " to " },
      { kind: "link", href: "a.md#b", children: [{ kind: "text", text: "the guide" }] },
      { kind: "text", text: ", " },
      { kind: "code", text: "PULSE_X" },
      { kind: "text", text: ", " },
      { kind: "em", children: [{ kind: "text", text: "(unset)" }] },
      { kind: "text", text: " or snake_case_name" },
    ]);
  });
});
