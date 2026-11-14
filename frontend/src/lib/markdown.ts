/**
 * The part of Markdown the docs in /docs and assistant replies use: headings,
 * paragraphs, lists, quotes, rules, fenced code, pipe tables and inline code, bold,
 * italics, strikethrough and links. It parses to plain data that
 * components/Markdown.tsx renders, so no HTML is ever injected.
 */

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "strong" | "em" | "del"; children: Inline[] }
  | { kind: "link"; href: string; children: Inline[] };

export type Block =
  | { kind: "heading"; level: number; id: string; text: Inline[] }
  | { kind: "paragraph"; text: Inline[] }
  | { kind: "list"; ordered: boolean; items: Block[][] }
  | { kind: "code"; text: string }
  | { kind: "quote"; blocks: Block[] }
  | { kind: "rule" }
  | { kind: "table"; header: Inline[][]; rows: Inline[][][] };

const HEADING = /^(#{1,6})\s+(.*)$/;
const FENCE = /^```/;
const LIST_ITEM = /^([-*]|\d+\.)\s+/;
const TABLE_RULE = /^\|?\s*:?-+/;
const QUOTE = /^ {0,3}> ?/;
const RULE = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/;

export function parseMarkdown(source: string): Block[] {
  const slugs = new Map<string, number>();
  return parseBlocks(source.replace(/\r\n?/g, "\n").split("\n"), slugs);
}

function parseBlocks(lines: string[], slugs: Map<string, number>): Block[] {
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = at(lines, i);
    if (!line.trim()) {
      i++;
    } else if (FENCE.test(line)) {
      const end = findIndex(lines, i + 1, (l) => FENCE.test(l));
      blocks.push({ kind: "code", text: lines.slice(i + 1, end).join("\n") });
      i = end + 1;
    } else if (RULE.test(line)) {
      blocks.push({ kind: "rule" });
      i++;
    } else if (QUOTE.test(line)) {
      const end = findIndex(lines, i + 1, (l) => !QUOTE.test(l));
      const inner = lines.slice(i, end).map((l) => l.replace(QUOTE, ""));
      blocks.push({ kind: "quote", blocks: parseBlocks(inner, slugs) });
      i = end;
    } else if (HEADING.test(line)) {
      const [, hashes = "", title = ""] = HEADING.exec(line) ?? [];
      const text = parseInline(title.trim());
      blocks.push({ kind: "heading", level: hashes.length, id: uniqueSlug(text, slugs), text });
      i++;
    } else if (line.startsWith("|") && TABLE_RULE.test(at(lines, i + 1))) {
      const end = findIndex(lines, i + 2, (l) => !l.startsWith("|"));
      blocks.push({
        kind: "table",
        header: cells(line).map(parseInline),
        rows: lines.slice(i + 2, end).map((row) => cells(row).map(parseInline)),
      });
      i = end;
    } else if (LIST_ITEM.test(line)) {
      i = parseList(lines, i, blocks, slugs);
    } else {
      const end = findIndex(lines, i + 1, (l) => !l.trim() || startsBlock(l));
      blocks.push({ kind: "paragraph", text: parseInline(joinLines(lines.slice(i, end))) });
      i = end;
    }
  }
  return blocks;
}

/** One list from line ``start``; items continue on lines indented past the marker. */
function parseList(
  lines: string[],
  start: number,
  blocks: Block[],
  slugs: Map<string, number>,
): number {
  const ordered = /^\d/.test(at(lines, start));
  const items: Block[][] = [];
  let i = start;
  while (i < lines.length) {
    const marker = LIST_ITEM.exec(at(lines, i));
    if (!marker || /^\d/.test(marker[0]) !== ordered) break;
    const indent = marker[0].length;
    const body = [at(lines, i).slice(indent)];
    i++;
    while (i < lines.length) {
      const next = at(lines, i);
      if (next.trim() && !next.startsWith(" ".repeat(indent))) break;
      // A blank line ends the item unless the item continues, indented, after it.
      if (!next.trim()) {
        const following = at(
          lines,
          findIndex(lines, i, (l) => !!l.trim()),
        );
        if (!following.startsWith(" ".repeat(indent))) break;
      }
      body.push(next.slice(indent));
      i++;
    }
    items.push(parseBlocks(body, slugs));
    // Items separated by a single blank line still belong to the same list.
    const next = findIndex(lines, i, (l) => !!l.trim());
    if (next < lines.length && LIST_ITEM.test(at(lines, next))) i = next;
  }
  blocks.push({ kind: "list", ordered, items });
  return i;
}

function startsBlock(line: string): boolean {
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    LIST_ITEM.test(line) ||
    QUOTE.test(line) ||
    RULE.test(line) ||
    line.startsWith("|")
  );
}

function findIndex(lines: string[], from: number, test: (line: string) => boolean): number {
  for (let i = from; i < lines.length; i++) if (test(at(lines, i))) return i;
  return lines.length;
}

function at(lines: string[], i: number): string {
  return lines[i] ?? "";
}

function joinLines(lines: string[]): string {
  return lines.map((line) => line.trim()).join(" ");
}

function cells(row: string): string[] {
  return row
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let plain = "";
  const flush = () => {
    if (plain) out.push({ kind: "text", text: plain });
    plain = "";
  };
  let i = 0;
  while (i < text.length) {
    const rest = text.slice(i);
    const code = /^`([^`]+)`/.exec(rest);
    const strong = /^(\*\*|__)(\S(?:.*?\S)?)\1/.exec(rest);
    const em = /^([_*])(\S(?:.*?\S)?)\1(?![\p{L}\p{N}])/u.exec(rest);
    const del = /^~~(\S(?:.*?\S)?)~~/.exec(rest);
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(rest);
    const wordStart = !/[\p{L}\p{N}]/u.test(text.charAt(i - 1));
    if (code) {
      flush();
      out.push({ kind: "code", text: code[1] ?? "" });
      i += code[0].length;
    } else if (strong && wordStart) {
      flush();
      out.push({ kind: "strong", children: parseInline(strong[2] ?? "") });
      i += strong[0].length;
    } else if (em && wordStart) {
      flush();
      out.push({ kind: "em", children: parseInline(em[2] ?? "") });
      i += em[0].length;
    } else if (del) {
      flush();
      out.push({ kind: "del", children: parseInline(del[1] ?? "") });
      i += del[0].length;
    } else if (link) {
      flush();
      out.push({ kind: "link", href: link[2] ?? "", children: parseInline(link[1] ?? "") });
      i += link[0].length;
    } else {
      plain += text.charAt(i);
      i++;
    }
  }
  flush();
  return out;
}

export function plainText(inlines: Inline[]): string {
  return inlines
    .map((item) => ("children" in item ? plainText(item.children) : item.text))
    .join("");
}

/** GitHub's heading anchors, so the same links work on GitHub and on the site. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s_-]/gu, "")
    .replace(/\s/g, "-");
}

function uniqueSlug(text: Inline[], slugs: Map<string, number>): string {
  const base = slugify(plainText(text));
  const seen = slugs.get(base) ?? 0;
  slugs.set(base, seen + 1);
  return seen ? `${base}-${seen}` : base;
}
