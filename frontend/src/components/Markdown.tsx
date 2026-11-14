import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { resolveDocLink } from "@/lib/docs";
import type { Block, Inline } from "@/lib/markdown";
import { cn } from "@/lib/utils";

import { CopyButton } from "./CopyButton";

/** Renders parsed docs (lib/markdown.ts) with the app's own type and tokens. */
export function Markdown({ blocks }: { blocks: Block[] }) {
  return <>{blocks.map((block, i) => renderBlock(block, i))}</>;
}

function renderBlock(block: Block, key: number): ReactNode {
  switch (block.kind) {
    case "heading": {
      const Tag = `h${Math.min(block.level, 4)}` as "h1" | "h2" | "h3" | "h4";
      return (
        <Tag
          key={key}
          id={block.id}
          className={cn(
            "group scroll-mt-20 font-medium tracking-tight",
            block.level === 1 && "text-3xl md:text-4xl",
            block.level === 2 && "mt-12 border-t pt-8 text-xl",
            block.level >= 3 && "mt-8 text-base",
          )}
        >
          {inline(block.text)}
          {block.level > 1 && (
            <a
              href={`#${block.id}`}
              aria-label="Link to this section"
              className="ml-2 text-muted-foreground opacity-0 group-hover:opacity-100 focus:opacity-100"
            >
              #
            </a>
          )}
        </Tag>
      );
    }
    case "paragraph":
      return (
        <p key={key} className="mt-4 leading-7 text-foreground/90">
          {inline(block.text)}
        </p>
      );
    case "list": {
      const List = block.ordered ? "ol" : "ul";
      return (
        <List
          key={key}
          className={cn(
            "mt-4 space-y-2 pl-5 leading-7 text-foreground/90 [&_p:first-child]:mt-0",
            block.ordered ? "list-decimal" : "list-disc",
          )}
        >
          {block.items.map((item, i) => (
            <li key={i} className="pl-1 marker:text-muted-foreground">
              <Markdown blocks={item} />
            </li>
          ))}
        </List>
      );
    }
    case "code":
      return (
        <div key={key} className="relative mt-4">
          <pre className="overflow-x-auto rounded-lg border bg-surface p-4 pr-20 font-mono text-[13px] leading-6">
            <code>{block.text}</code>
          </pre>
          <div className="absolute top-2 right-2">
            <CopyButton text={block.text} />
          </div>
        </div>
      );
    case "table":
      return (
        <div key={key} className="mt-4 overflow-x-auto rounded-lg border">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface text-xs text-muted-foreground">
              <tr>
                {block.header.map((cell, i) => (
                  <th key={i} className="min-w-44 px-3 py-2 font-medium">
                    {inline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {block.rows.map((row, r) => (
                <tr key={r} className="align-top">
                  {row.map((cell, i) => (
                    <td key={i} className="min-w-44 px-3 py-2">
                      {inline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

function inline(items: Inline[]): ReactNode {
  return items.map((item, i) => {
    switch (item.kind) {
      case "text":
        return item.text;
      case "code":
        return (
          <code key={i} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
            {item.text}
          </code>
        );
      case "strong":
        return (
          <strong key={i} className="font-medium text-foreground">
            {inline(item.children)}
          </strong>
        );
      case "em":
        return <em key={i}>{inline(item.children)}</em>;
      case "link":
        return (
          <DocLinkView key={i} href={item.href}>
            {inline(item.children)}
          </DocLinkView>
        );
    }
  });
}

const LINK = "underline decoration-border underline-offset-4 hover:decoration-foreground";

function DocLinkView({ href, children }: { href: string; children: ReactNode }) {
  const target = resolveDocLink(href);
  if (target.kind === "anchor")
    return (
      <a href={`#${target.hash}`} className={LINK}>
        {children}
      </a>
    );
  if (target.kind === "doc")
    return (
      <Link
        to="/docs/$slug"
        params={{ slug: target.slug }}
        {...(target.hash ? { hash: target.hash } : {})}
        className={LINK}
      >
        {children}
      </Link>
    );
  return (
    <a href={target.href} target="_blank" rel="noopener noreferrer" className={LINK}>
      {children}
    </a>
  );
}
