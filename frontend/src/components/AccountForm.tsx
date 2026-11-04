import { useState, type FormEvent } from "react";

import { useCreateAccount } from "@/api/queries";

import { Button } from "./Button";

const inputClass =
  "h-9 w-full rounded-md border bg-background px-3 font-mono text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

export function AccountForm({ onDone }: { onDone: () => void }) {
  const create = useCreateAccount();
  const [form, setForm] = useState({ cluster: "", username: "", host: "", port: "22" });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      { cluster: form.cluster, username: form.username, host: form.host, port: Number(form.port) },
      { onSuccess: onDone },
    );
  };

  return (
    <form onSubmit={submit} className="grid gap-3 p-4 sm:grid-cols-2">
      <Field label="Cluster name">
        <input
          required
          value={form.cluster}
          onChange={set("cluster")}
          placeholder="LUMI-G"
          className={inputClass}
        />
      </Field>
      <Field label="Username">
        <input
          required
          value={form.username}
          onChange={set("username")}
          placeholder="jdoe"
          autoCapitalize="none"
          autoCorrect="off"
          className={inputClass}
        />
      </Field>
      <Field label="Login host">
        <input
          required
          value={form.host}
          onChange={set("host")}
          placeholder="lumi.csc.fi"
          autoCapitalize="none"
          inputMode="url"
          className={inputClass}
        />
      </Field>
      <Field label="SSH port">
        <input
          required
          type="number"
          min={1}
          max={65535}
          value={form.port}
          onChange={set("port")}
          className={inputClass}
        />
      </Field>
      {create.error && <p className="text-xs text-fail sm:col-span-2">{create.error.message}</p>}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add account"}
        </Button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5 text-xs text-muted-foreground">
      {label}
      {children}
    </label>
  );
}
