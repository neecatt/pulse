import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { useUpdateJob } from "@/api/queries";
import type { JobDetail } from "@/api/types";

/** A teammate's job: its note and tags, read-only. */
export function SharedJobNotes({ job }: { job: JobDetail }) {
  if (!job.tags.length && !job.note) return null;
  return (
    <div className="space-y-2">
      {job.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {job.tags.map((t) => (
            <span key={t} className="rounded-full border px-2 py-0.5 text-xs">
              {t}
            </span>
          ))}
        </div>
      )}
      {job.note && <p className="text-sm whitespace-pre-wrap text-muted-foreground">{job.note}</p>}
    </div>
  );
}

/** Inline note and tags for a job; changes save on their own. */
export function JobNotes({ job }: { job: JobDetail }) {
  const update = useUpdateJob(job.id);
  const [note, setNote] = useState(job.note ?? "");
  const [tag, setTag] = useState("");

  const saveNote = () => {
    if (note.trim() !== (job.note ?? "")) update.mutate({ note });
  };
  const addTag = (e: KeyboardEvent<HTMLInputElement>) => {
    const value = tag.trim().replace(/,$/, "");
    if ((e.key === "Enter" || e.key === ",") && value) {
      e.preventDefault();
      update.mutate({ tags: [...job.tags, value] });
      setTag("");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {job.tags.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
          >
            {t}
            <button
              type="button"
              aria-label={`Remove tag ${t}`}
              onClick={() => update.mutate({ tags: job.tags.filter((x) => x !== t) })}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <input
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          onKeyDown={addTag}
          placeholder={job.tags.length ? "+ tag" : "Add tags (press Enter)"}
          maxLength={32}
          className="h-7 min-w-24 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground/70"
        />
      </div>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={saveNote}
        placeholder="Notes about this run: what changed, what you learned…"
        maxLength={2000}
        rows={2}
        className="w-full resize-y rounded-md border bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring"
      />
      {update.error && <p className="text-xs text-fail">{update.error.message}</p>}
    </div>
  );
}
