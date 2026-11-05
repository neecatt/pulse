import { useEffect, useRef } from "react";

import { Button } from "./Button";

export interface ConfirmOptions {
  title: string;
  description: string;
  /** The confirm button's label: say what happens, e.g. "Delete team". */
  action: string;
  /** Destructive actions get a red confirm button. */
  danger?: boolean;
  onConfirm: () => void;
}

/** The dialog behind `useConfirm`; it opens as soon as it mounts. */
export function ConfirmDialog({
  options,
  onClose,
}: {
  options: ConfirmOptions;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => ref.current?.showModal(), []);

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-title"
      onClose={onClose}
      // The dialog has no padding, so a click on the element itself is the backdrop.
      onClick={(e) => e.target === ref.current && ref.current.close()}
      className="m-auto w-[calc(100%-2rem)] max-w-sm rounded-lg border bg-surface p-0 text-foreground shadow-lg backdrop:bg-black/40"
    >
      <div className="space-y-1.5 p-5">
        <h2 id="confirm-title" className="text-sm font-medium">
          {options.title}
        </h2>
        <p className="text-sm text-muted-foreground">{options.description}</p>
      </div>
      <div className="flex justify-end gap-2 border-t px-5 py-3">
        <Button variant="ghost" autoFocus onClick={() => ref.current?.close()}>
          Cancel
        </Button>
        <Button
          variant={options.danger ? "destructive" : "primary"}
          onClick={() => {
            options.onConfirm();
            ref.current?.close();
          }}
        >
          {options.action}
        </Button>
      </div>
    </dialog>
  );
}
