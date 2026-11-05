import { useState, type ReactNode } from "react";

import { ConfirmDialog, type ConfirmOptions } from "@/components/ConfirmDialog";

/**
 * Ask before doing something that can't be undone, in an in-app dialog.
 * Render `dialog` once, then call `ask(...)` from any button or link.
 * Escape, Cancel or a click outside closes it without doing anything.
 */
export function useConfirm(): { ask: (options: ConfirmOptions) => void; dialog: ReactNode } {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  return {
    ask: setOptions,
    dialog: options && <ConfirmDialog options={options} onClose={() => setOptions(null)} />,
  };
}
