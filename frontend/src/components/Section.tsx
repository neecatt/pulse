import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface SectionProps {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Section({ title, action, children, className }: SectionProps) {
  return (
    <section className={className}>
      <div className="mb-3 flex min-h-8 items-center justify-between gap-4">
        <h2 className="text-xs tracking-wider text-muted-foreground uppercase">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-lg border bg-surface", className)}>{children}</div>;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card className="px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 text-sm text-muted-foreground">{children}</div>}
    </Card>
  );
}

export function LoadingRows({ rows = 3 }: { rows?: number }) {
  return (
    <Card className="divide-y">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="p-4">
          <div className="h-4 w-40 animate-pulse rounded bg-muted" />
          <div className="mt-2 h-3 w-64 max-w-full animate-pulse rounded bg-muted" />
        </div>
      ))}
    </Card>
  );
}

export function ErrorNotice({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Couldn't reach the Pulse API.";
  return (
    <Card className="border-fail/40 p-4 text-sm text-fail">
      {message} <span className="text-muted-foreground">Retrying automatically.</span>
    </Card>
  );
}
