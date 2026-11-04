import { useCopy } from "@/hooks/use-copy";

import { Button } from "./Button";

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const { copied, copy } = useCopy();
  return (
    <Button variant="ghost" onClick={() => copy(text)} className="shrink-0">
      {copied ? "Copied" : label}
    </Button>
  );
}
