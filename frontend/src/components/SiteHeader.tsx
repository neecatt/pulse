import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { REPO_URL } from "@/config/constants";
import { cn } from "@/lib/utils";

/** The public site's top bar: name, docs, source, and a slot for sign-in. */
export function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="pt-safe mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4">
      <Link to="/" className="flex items-center gap-2 font-mono text-sm font-medium">
        <span className="size-2 animate-pulse rounded-full bg-run" /> pulse
      </Link>
      <nav className="flex items-center gap-1 text-xs">
        <Link
          to="/docs/$slug"
          params={{ slug: "self-hosting" }}
          className="inline-flex h-8 items-center rounded-md px-2 text-muted-foreground hover:text-foreground sm:px-3"
          activeProps={{ className: "text-foreground" }}
        >
          Docs
        </Link>
        <GitHubLink className="h-8 px-2 sm:px-3" />
        {children}
      </nav>
    </header>
  );
}

export function GitHubLink({
  className,
  label = "GitHub",
}: {
  className?: string;
  label?: string;
}) {
  return (
    <a
      href={REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md text-muted-foreground hover:text-foreground",
        className,
      )}
    >
      <GitHubMark className="size-4" />
      <span>{label}</span>
    </a>
  );
}

/** GitHub's mark (Octicons, MIT). */
function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden className={className}>
      <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
    </svg>
  );
}
