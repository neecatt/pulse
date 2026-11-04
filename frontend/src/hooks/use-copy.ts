import { useState } from "react";

import { COPIED_FEEDBACK_MS } from "@/config/constants";

/** Copy text to the clipboard; `copied` is true briefly afterwards for feedback. */
export function useCopy(): { copied: boolean; copy: (text: string) => Promise<void> } {
  const [copied, setCopied] = useState(false);
  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), COPIED_FEEDBACK_MS);
  };
  return { copied, copy };
}
