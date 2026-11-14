import { Link, createFileRoute, notFound, useLocation } from "@tanstack/react-router";
import { List, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAuthStatus } from "@/api/queries";
import { Markdown } from "@/components/Markdown";
import { GitHubLink, SiteHeader } from "@/components/SiteHeader";
import { REPO_URL } from "@/config/constants";
import { useActiveSection } from "@/hooks/use-active-section";
import { DOCS } from "@/lib/docs";
import { parseMarkdown, plainText } from "@/lib/markdown";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/docs/$slug")({
  loader: ({ params }) => {
    const doc = DOCS.find((item) => item.slug === params.slug);
    if (!doc) throw notFound();
    return doc;
  },
  component: DocPage,
});

const ACTION = "inline-flex h-8 items-center rounded-md border px-3 font-medium hover:bg-muted";

/** A public guide from the repository's docs/, readable signed in or out. */
function DocPage() {
  const doc = Route.useLoaderData();
  const { data: status } = useAuthStatus();
  const hash = useLocation({ select: (location) => location.hash });
  const blocks = useMemo(() => parseMarkdown(doc.source), [doc]);
  const title = blocks[0]?.kind === "heading" ? plainText(blocks[0].text) : doc.title;
  const sections = useMemo(
    () =>
      blocks.flatMap((block) =>
        block.kind === "heading" && block.level === 2
          ? [{ id: block.id, title: plainText(block.text) }]
          : [],
      ),
    [blocks],
  );
  const ids = useMemo(() => sections.map((section) => section.id), [sections]);
  const active = useActiveSection(ids);
  const [contentsOpen, setContentsOpen] = useState(false);
  const [heading, body] =
    blocks[0]?.kind === "heading" ? [blocks.slice(0, 1), blocks.slice(1)] : [[], blocks];

  useEffect(() => {
    document.title = `${title} · Pulse`;
  }, [title]);

  // Content renders after the first paint, so jump to a linked section ourselves.
  useEffect(() => {
    if (hash) document.getElementById(hash)?.scrollIntoView();
    else window.scrollTo(0, 0);
  }, [doc, hash]);

  return (
    <div className="min-h-dvh">
      <div className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
        <SiteHeader>
          {status?.user ? (
            <Link to="/" className={ACTION}>
              Open Pulse
            </Link>
          ) : (
            <a href="/?start=login" className={ACTION}>
              Sign in
            </a>
          )}
        </SiteHeader>
      </div>

      <div className="mx-auto grid max-w-6xl gap-10 px-4 pb-24 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <aside className="pt-8 lg:sticky lg:top-14 lg:max-h-[calc(100dvh-3.5rem)] lg:self-start lg:overflow-y-auto lg:pb-8">
          <p className="font-mono text-xs tracking-wider text-muted-foreground uppercase">Guides</p>
          <nav className="mt-3 flex flex-wrap gap-1 lg:flex-col">
            {DOCS.map((item) => (
              <Link
                key={item.slug}
                to="/docs/$slug"
                params={{ slug: item.slug }}
                className={cn(
                  "rounded-md px-2 py-1.5 text-sm hover:bg-muted",
                  item.slug === doc.slug ? "bg-muted font-medium" : "text-muted-foreground",
                )}
              >
                {item.title}
              </Link>
            ))}
          </nav>
          {sections.length > 0 && (
            <>
              <p className="mt-8 hidden font-mono text-xs tracking-wider text-muted-foreground uppercase lg:block">
                On this page
              </p>
              <nav className="mt-3 hidden border-l lg:flex lg:flex-col">
                <SectionLinks sections={sections} active={active} />
              </nav>
            </>
          )}
        </aside>

        <article className="max-w-3xl min-w-0 pt-8">
          <Markdown blocks={heading} />
          <p className="mt-3 text-sm text-muted-foreground">
            The same guide lives{" "}
            <a
              href={`${REPO_URL}/blob/main/docs/${doc.file}`}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 hover:text-foreground"
            >
              in the repository
            </a>
            , next to the code it describes.
          </p>
          <Markdown blocks={body} />
          <footer className="mt-16 flex flex-wrap items-center justify-between gap-3 border-t pt-6 text-xs text-muted-foreground">
            <a
              href={`${REPO_URL}/edit/main/docs/${doc.file}`}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground"
            >
              Improve this page on GitHub
            </a>
            <GitHubLink label="View the source" />
          </footer>
        </article>
      </div>

      {sections.length > 0 && (
        <div className="fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] left-4 z-30 lg:hidden">
          {contentsOpen && (
            <nav className="mb-2 flex max-h-[60dvh] w-[min(20rem,calc(100vw-2rem))] flex-col overflow-y-auto rounded-lg border bg-surface py-2 shadow-lg">
              <SectionLinks
                sections={sections}
                active={active}
                onPick={() => setContentsOpen(false)}
              />
            </nav>
          )}
          <button
            type="button"
            aria-expanded={contentsOpen}
            onClick={() => setContentsOpen((open) => !open)}
            className="inline-flex h-10 items-center gap-2 rounded-full border bg-surface px-4 text-sm font-medium shadow-lg"
          >
            {contentsOpen ? <X className="size-4" /> : <List className="size-4" />}
            Contents
          </button>
        </div>
      )}
    </div>
  );
}

function SectionLinks({
  sections,
  active,
  onPick,
}: {
  sections: { id: string; title: string }[];
  active: string | undefined;
  onPick?: () => void;
}) {
  return sections.map((section) => (
    <a
      key={section.id}
      href={`#${section.id}`}
      onClick={onPick}
      aria-current={section.id === active ? "location" : undefined}
      className={cn(
        "-ml-px border-l-2 px-3 py-1.5 text-[13px] hover:text-foreground",
        section.id === active
          ? "border-foreground font-medium text-foreground"
          : "border-transparent text-muted-foreground",
      )}
    >
      {section.title}
    </a>
  ));
}
