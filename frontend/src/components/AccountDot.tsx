import { cn } from "@/lib/utils";

// Literal class names so Tailwind can see them; length matches PALETTE_SIZE in the backend.
const palette = ["bg-acc-0", "bg-acc-1", "bg-acc-2", "bg-acc-3", "bg-acc-4", "bg-acc-5"];

export function AccountDot({ color, className }: { color: number; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-2 shrink-0 rounded-sm",
        palette[color % palette.length],
        className,
      )}
    />
  );
}
