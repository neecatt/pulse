import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { resolveDocLink } from "@/lib/docs";
import type { Block, Inline } from "@/lib/markdown";
import { cn } from "@/lib/utils";

import { CopyButton } from "./CopyButton";

/**
 * Renders parsed Markdown (lib/markdown.ts) with the app's own type and tokens:
 * a public guide (``docs``), or an assistant's reply (``chat``: compact, no
 * section anchors, and only web and mail links, since the text isn't ours).
 */
export function Markdown({ blocks, variant = "docs" }: { blocks: Block[]; variant?: Variant }) {
  return <>{blocks.map((block, i) => renderBlock(block, i, variant))}</>;
}

type Variant = "docs" | "chat";

const GAP: Record<Variant, string> = { docs: "mt-4", chat: "mt-3 first:mt-0" };

function renderBlock(block: Block, key: number, variant: Variant): ReactNode {
  const chat = variant === "chat";
  const gap = GAP[variant];
  switch (block.kind) {
    case "heading": {
      const Tag = `h${Math.min(block.level, 4)}` as "h1" | "h2" | "h3" | "h4";
      if (chat)
        return (
          <Tag
            key={key}
            className={cn(
              "mt-4 font-semibold first:mt-0",
              block.level <= 2 ? "text-base" : "text-sm",
            )}
          >
            {inline(block.text, variant)}
          </Tag>
        );
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
          {inline(block.text, variant)}
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
        <p key={key} className={cn(gap, chat ? "leading-6" : "leading-7 text-foreground/90")}>
          {inline(block.text, variant)}
        </p>
      );
    case "quote":
      return (
        <blockquote key={key} className={cn(gap, "border-l-2 pl-3 text-muted-foreground")}>
          <Markdown blocks={block.blocks} variant={variant} />
        </blockquote>
      );
    case "rule":
      return <hr key={key} className={cn(chat ? "my-4" : "my-8", "border-border")} />;
    case "list": {
      const List = block.ordered ? "ol" : "ul";
      return (
        <List
          key={key}
          className={cn(
            gap,
            "pl-5 [&_p:first-child]:mt-0",
            chat ? "space-y-1 leading-6" : "space-y-2 leading-7 text-foreground/90",
            block.ordered ? "list-decimal" : "list-disc",
          )}
        >
          {block.items.map((item, i) => (
            <li key={i} className="pl-1 marker:text-muted-foreground">
              <Markdown blocks={item} variant={variant} />
            </li>
          ))}
        </List>
      );
    }
    case "code":
      return (
        <div key={key} className={cn(gap, "relative")}>
          <pre
            className={cn(
              "overflow-x-auto rounded-lg border bg-surface pr-20 font-mono leading-6",
              chat ? "p-3 text-xs" : "p-4 text-[13px]",
            )}
          >
            <code>{block.text}</code>
          </pre>
          <div className="absolute top-2 right-2">
            <CopyButton text={block.text} />
          </div>
        </div>
      );
    case "table":
      return (
        <div key={key} className={cn(gap, "overflow-x-auto rounded-lg border")}>
          <table className="w-full text-left text-sm">
            <thead className="bg-surface text-xs text-muted-foreground">
              <tr>
                {block.header.map((cell, i) => (
                  <th key={i} className={cn("px-3 py-2 font-medium", !chat && "min-w-44")}>
                    {inline(cell, variant)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {block.rows.map((row, r) => (
                <tr key={r} className="align-top">
                  {row.map((cell, i) => (
                    <td key={i} className={cn("px-3 py-2", !chat && "min-w-44")}>
                      {inline(cell, variant)}
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

function inline(items: Inline[], variant: Variant): ReactNode {
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
            {inline(item.children, variant)}
          </strong>
        );
      case "em":
        return <em key={i}>{inline(item.children, variant)}</em>;
      case "del":
        return <del key={i}>{inline(item.children, variant)}</del>;
      case "link":
        return variant === "chat" ? (
          <ChatLink key={i} href={item.href}>
            {inline(item.children, variant)}
          </ChatLink>
        ) : (
          <DocLinkView key={i} href={item.href}>
            {inline(item.children, variant)}
          </DocLinkView>
        );
    }
  });
}

const LINK = "underline decoration-border underline-offset-4 hover:decoration-foreground";

/** A link in an assistant's reply: web and mail only, never javascript: or data:. */
function ChatLink({ href, children }: { href: string; children: ReactNode }) {
  if (!/^(https?:\/\/|mailto:)/i.test(href)) return <>{children}</>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={LINK}>
      {children}
    </a>
  );
}

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
