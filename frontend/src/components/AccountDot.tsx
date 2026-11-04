import { ACCOUNT_COLOR_CLASSES as palette } from "@/config/constants";
import { cn } from "@/lib/utils";

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
