export type JobState = "RUNNING" | "PENDING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type Account = {
  id: string;
  user: string;
  cluster: string;
  host: string;
  color: string;
  notify: boolean;
};

export type Job = {
  id: string;
  name: string;
  accountId: string;
  partition: string;
  state: JobState;
  nodes: number;
  gpus: number;
  elapsed: string;
  limit: string;
  progress: number; // 0..1
  gpuUtil: number;
  memUtil: number;
  loss: number[];
  epoch?: string;
};

export const accounts: Account[] = [
  { id: "a1", user: "nabdulla", cluster: "JUWELS Booster", host: "juwels.fz-juelich.de", color: "var(--acc-1)", notify: true },
  { id: "a2", user: "nabdull2", cluster: "LUMI-G", host: "lumi.csc.fi", color: "var(--acc-2)", notify: true },
  { id: "a3", user: "na4521", cluster: "Leonardo", host: "login.leonardo.cineca.it", color: "var(--acc-3)", notify: false },
];

const curve = (start: number, n: number, seed: number) =>
  Array.from({ length: n }, (_, i) => +(start * Math.exp(-i / 14) + 0.25 + Math.sin(i * seed) * 0.04).toFixed(3));

export const jobs: Job[] = [
  { id: "8812041", name: "llama-7b-sft", accountId: "a1", partition: "booster", state: "RUNNING", nodes: 8, gpus: 32, elapsed: "14:22:07", limit: "24:00:00", progress: 0.6, gpuUtil: 94, memUtil: 81, loss: curve(2.6, 48, 1.3), epoch: "3 / 5" },
  { id: "8812102", name: "vit-l-pretrain", accountId: "a1", partition: "booster", state: "RUNNING", nodes: 4, gpus: 16, elapsed: "03:10:44", limit: "12:00:00", progress: 0.26, gpuUtil: 88, memUtil: 72, loss: curve(4.1, 22, 0.9), epoch: "12 / 90" },
  { id: "5530918", name: "diffusion-ft", accountId: "a2", partition: "standard-g", state: "PENDING", nodes: 2, gpus: 16, elapsed: "00:00:00", limit: "08:00:00", progress: 0, gpuUtil: 0, memUtil: 0, loss: [] },
  { id: "5530771", name: "mixtral-eval", accountId: "a2", partition: "small-g", state: "FAILED", nodes: 1, gpus: 8, elapsed: "00:41:12", limit: "02:00:00", progress: 0.34, gpuUtil: 0, memUtil: 0, loss: curve(1.9, 12, 2.1) },
  { id: "2209344", name: "gnn-sweep-17", accountId: "a3", partition: "boost_usr_prod", state: "COMPLETED", nodes: 1, gpus: 4, elapsed: "05:58:30", limit: "06:00:00", progress: 1, gpuUtil: 0, memUtil: 0, loss: curve(1.4, 40, 1.7) },
  { id: "2209360", name: "gnn-sweep-18", accountId: "a3", partition: "boost_usr_prod", state: "RUNNING", nodes: 1, gpus: 4, elapsed: "01:02:09", limit: "06:00:00", progress: 0.17, gpuUtil: 76, memUtil: 58, loss: curve(1.4, 10, 1.1) },
];

export const events = [
  { t: "2m", accountId: "a2", text: "mixtral-eval failed — exit code 137 (OOM)", kind: "FAILED" as JobState },
  { t: "18m", accountId: "a3", text: "gnn-sweep-18 started on lrdn1342", kind: "RUNNING" as JobState },
  { t: "21m", accountId: "a3", text: "gnn-sweep-17 completed", kind: "COMPLETED" as JobState },
  { t: "3h", accountId: "a1", text: "vit-l-pretrain started on 4 nodes", kind: "RUNNING" as JobState },
];

export const accountOf = (id: string) => accounts.find((a) => a.id === id)!;
