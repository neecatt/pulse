import { describe, expect, it } from "vitest";

import { DOCS, resolveDocLink } from "./docs";
import { type Block, type Inline, parseMarkdown } from "./markdown";

function links(blocks: Block[]): string[] {
  const inlines = (items: Inline[]): string[] =>
    items.flatMap((item) =>
      item.kind === "link"
        ? [item.href, ...inlines(item.children)]
        : "children" in item
          ? inlines(item.children)
          : [],
    );
  return blocks.flatMap((block) => {
    if (block.kind === "list") return block.items.flatMap(links);
    if (block.kind === "table") return [...block.header, ...block.rows.flat()].flatMap(inlines);
    return "text" in block && typeof block.text !== "string" ? inlines(block.text) : [];
  });
}

function anchors(blocks: Block[]): string[] {
  return blocks.flatMap((block) =>
    block.kind === "heading"
      ? [block.id]
      : block.kind === "list"
        ? block.items.flatMap(anchors)
        : [],
  );
}

describe("published guides", () => {
  it.each(DOCS.map((doc) => [doc.slug, doc] as const))("%s has no broken links", (_, doc) => {
    for (const href of links(parseMarkdown(doc.source))) {
      const target = resolveDocLink(href);
      if (target.kind === "external") continue;
      const page = target.kind === "doc" ? DOCS.find((d) => d.slug === target.slug)! : doc;
      if (target.hash) expect(anchors(parseMarkdown(page.source)), href).toContain(target.hash);
    }
  });

  it("links between guides stay on the site and other files go to GitHub", () => {
    expect(resolveDocLink("assistants.md")).toEqual({ kind: "doc", slug: "assistants", hash: "" });
    expect(resolveDocLink("#users")).toEqual({ kind: "anchor", hash: "users" });
    expect(resolveDocLink("../SECURITY.md")).toEqual({
      kind: "external",
      href: "https://github.com/neecatt/pulse/blob/main/SECURITY.md",
    });
  });
});
