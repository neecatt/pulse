# Pulse backend

FastAPI service that polls Slurm for every linked HPC account, stores job
snapshots and training telemetry, records state-change events, and delivers
them as Web Push notifications.

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/pulse serve --reload          # http://127.0.0.1:8000/docs
```

## How it works

```
poller ──snapshot()──▶ SlurmClient ──(mock | ssh: sacct, scontrol, tail, nvidia-smi)
   │
   ├─ upsert jobs + job_metrics
   ├─ diff states ─▶ events  (services/events.py, pure)
   └─ notifier ─▶ Web Push to every subscribed device of the user
```

- **Mock mode** (default) simulates a cluster whose jobs start, finish, fail,
  stall and approach their time limit within minutes of startup.
- **SSH mode** connects to `host:port` as the account's username with the
  server's SSH key or agent. The login node needs `sacct` and `scontrol`;
  GPU utilisation uses `srun --overlap … nvidia-smi` and is skipped if that
  fails. Training loss and epoch are parsed from the tail of the job's StdOut.

## Web Push

```sh
.venv/bin/pulse gen-vapid >> .env
```

Without VAPID keys the app works normally but sends no notifications.
