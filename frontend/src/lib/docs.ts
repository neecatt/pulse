import assistants from "../../../docs/assistants.md?raw";
import deployment from "../../../docs/deployment.md?raw";

import { REPO_URL } from "@/config/constants";

/** Guides from the repository's docs/ folder that the site publishes under /docs. */
export const DOCS = [
  { slug: "self-hosting", file: "deployment.md", title: "Self-hosting", source: deployment },
  { slug: "assistants", file: "assistants.md", title: "Claude Code and Codex", source: assistants },
] as const;

export type DocSlug = (typeof DOCS)[number]["slug"];

export type DocLink =
  | { kind: "anchor"; hash: string }
  | { kind: "doc"; slug: DocSlug; hash: string }
  | { kind: "external"; href: string };

/** Where a link in a doc goes: a section, another published doc, or the repository. */
export function resolveDocLink(href: string): DocLink {
  if (href.startsWith("#")) return { kind: "anchor", hash: href.slice(1) };
  if (/^[a-z]+:/i.test(href)) return { kind: "external", href };
  const [path, hash = ""] = href.split("#");
  const doc = DOCS.find((item) => item.file === path);
  if (doc) return { kind: "doc", slug: doc.slug, hash };
  return { kind: "external", href: new URL(href, `${REPO_URL}/blob/main/docs/`).href };
}
