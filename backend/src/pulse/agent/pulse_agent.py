#!/usr/bin/env python3
"""Pulse agent: reports your Slurm jobs to Pulse from a cluster login node.

Use it on clusters where Pulse can't sign in by itself (2FA, SSH certificates).
It runs as you and needs only Python 3.6+ and the Slurm CLI: no root, no
packages, no daemon. Cron starts it every minute; each run reports for about a
minute at the pace the server asks for.

  python3 pulse-agent.py install <server-url> <token>   set up and verify
  python3 pulse-agent.py status                         send one report now
  python3 pulse-agent.py uninstall                      stop and remove
  python3 pulse-agent.py loop                           run in the foreground
                                                        (if cron isn't available)
"""

import base64
import contextlib
import fcntl
import json
import os
import pwd
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

VERSION = "1"
CONFIG_DIR = os.path.expanduser("~/.config/pulse-agent")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LOCK_PATH = os.path.join(CONFIG_DIR, "lock")
STATE_PATH = os.path.join(CONFIG_DIR, "state.json")  # file offsets the server has
CRON_TAG = "# pulse-agent"

RUN_SECONDS = 55  # cron starts the next run a minute later
GPU_SAMPLE_SECONDS = 60  # GPU queries start a job step; keep them rare
DEFAULT_INTERVAL = 30
MIN_INTERVAL = 5
COMMAND_TIMEOUT = 30
GPU_TIMEOUT = 15
LOG_TAIL_BYTES = 16384
LOG_TAIL_LINES = 40
LOOKBACK = "now-48hours"

# Must match pulse.slurm.parsing.SACCT_FIELDS; the backend tests check this.
SACCT_FIELDS = (
    "JobID",
    "JobName",
    "Partition",
    "State",
    "NNodes",
    "AllocTRES",
    "ReqTRES",
    "NodeList",
    "Submit",
    "Start",
    "End",
    "TimelimitRaw",
    "ElapsedRaw",
    "ExitCode",
)
# Metric file rules: must match pulse.metrics.discovery (the backend tests check this).
CHUNK_BYTES = 256 * 1024
CONFIG_MAX_BYTES = 64 * 1024
MAX_METRIC_FILES = 8
MAX_CONFIG_FILES = 4
SEARCH_DEPTH = 4
PRUNE_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", ".cache")
CONFIG_NAMES = (
    "hparams.yaml",
    "hparams.json",
    "config.yaml",
    "config.yml",
    "config.json",
    "params.json",
    "args.json",
)
DISCOVERY_SECONDS = 60  # walking shared filesystems is slow; don't repeat it often

NVIDIA_SMI = [
    "nvidia-smi",
    "--query-gpu=utilization.gpu,memory.used,memory.total",
    "--format=csv,noheader,nounits",
]


class AgentError(Exception):
    def __init__(self, message: str, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal


def main(argv: List[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "install" and len(argv) == 4:
        return install(argv[2].rstrip("/"), argv[3])
    if command == "run":
        return run(RUN_SECONDS)
    if command == "loop":
        return run(float("inf"))
    if command == "status":
        return status()
    if command == "uninstall":
        return uninstall()
    print(__doc__)
    return 2


def install(server: str, token: str) -> int:
    config = {"server": server, "token": token}
    try:
        report(config, include_gpu=False)
    except AgentError as exc:
        print("✗ {}".format(exc))
        return 1
    save_config(config)
    if add_cron_entry():
        print("✓ Connected. Pulse now receives your jobs from this cluster.")
    else:
        print("✓ Connected, but cron isn't available on this node. Keep the agent running with:")
        print("  nohup {} {} loop >/dev/null 2>&1 &".format(sys.executable, script_path()))
    return 0


def status() -> int:
    try:
        interval = report(load_config(), include_gpu=False)
    except AgentError as exc:
        print("✗ {}".format(exc))
        return 1
    print("✓ Reported to Pulse. Next report in {}s.".format(interval))
    return 0


def uninstall() -> int:
    remove_cron_entry()
    for path in (CONFIG_PATH, LOCK_PATH, STATE_PATH):
        if os.path.exists(path):
            os.remove(path)
    print("✓ Pulse agent removed.")
    return 0


def run(duration: float) -> int:
    config = load_config()
    lock = acquire_lock()
    if lock is None:
        return 0  # another run is still going
    deadline = time.monotonic() + duration
    last_gpu_sample = -float("inf")
    discovered = {}  # type: Dict[str, Tuple[float, List[str]]]
    while True:
        include_gpu = time.monotonic() - last_gpu_sample >= GPU_SAMPLE_SECONDS
        if include_gpu:
            last_gpu_sample = time.monotonic()
        try:
            interval = report(config, include_gpu, discovered)
        except AgentError as exc:
            log(str(exc))
            if exc.fatal:
                return 1
            interval = DEFAULT_INTERVAL
        if time.monotonic() + interval > deadline:
            return 0
        time.sleep(interval)


# Reporting


def report(
    config: Dict[str, str],
    include_gpu: bool,
    discovered: Optional[Dict[str, Tuple[float, List[str]]]] = None,
) -> int:
    """Send one snapshot; returns the server's requested delay before the next."""
    payload = collect(include_gpu, load_cursors(), {} if discovered is None else discovered)
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        config["server"] + "/api/agent/report",
        data=body,
        headers={
            "Authorization": "Bearer " + config["token"],
            "Content-Type": "application/json",
            "User-Agent": "pulse-agent/" + VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=COMMAND_TIMEOUT) as response:
            reply = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise AgentError(
                "Pulse rejected this agent's token. Copy a fresh install command from the app.",
                fatal=True,
            ) from exc
        raise AgentError("Pulse answered HTTP {}.".format(exc.code)) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AgentError("Can't reach Pulse at {}: {}".format(config["server"], exc)) from exc
    if isinstance(reply.get("cursors"), dict):
        save_json(STATE_PATH, {"cursors": reply["cursors"]})
    return max(MIN_INTERVAL, int(reply.get("next_report_in", DEFAULT_INTERVAL)))


def collect(
    include_gpu: bool,
    cursors: Dict[str, Dict[str, int]],
    discovered: Dict[str, Tuple[float, List[str]]],
) -> Dict[str, object]:
    """Raw Slurm output for the server to parse; the agent stays deliberately dumb."""
    payload = {"agent_version": VERSION, "sacct": "", "jobs": {}, "error": None}  # type: Dict[str, object]
    try:
        sacct = run_command(
            [
                "sacct",
                "-X",
                "-P",
                "-n",
                "-u",
                current_user(),
                "-S",
                LOOKBACK,
                "-o",
                ",".join(SACCT_FIELDS),
            ],
            env={"SLURM_TIME_FORMAT": "%s"},
        )
    except AgentError as exc:
        payload["error"] = str(exc)
        return payload
    payload["sacct"] = sacct
    payload["jobs"] = {
        job_id: job_telemetry(job_id, has_gpus and include_gpu, cursors.get(job_id, {}), discovered)
        for job_id, has_gpus in running_jobs(sacct)
    }
    return payload


def running_jobs(sacct: str) -> List[Tuple[str, bool]]:
    jobs = []
    state_col = SACCT_FIELDS.index("State")
    tres_col = SACCT_FIELDS.index("AllocTRES")
    for line in sacct.splitlines():
        cols = line.split("|")
        if len(cols) != len(SACCT_FIELDS):
            continue
        state = (cols[state_col].split() or [""])[0]
        if state in ("RUNNING", "COMPLETING"):
            jobs.append((cols[0], "gres/gpu" in cols[tres_col]))
    return jobs


def job_telemetry(
    job_id: str,
    include_gpu: bool,
    cursors: Dict[str, int],
    discovered: Dict[str, Tuple[float, List[str]]],
) -> Dict[str, object]:
    telemetry = {}  # type: Dict[str, object]
    try:
        info = run_command(["scontrol", "show", "job", "-o", job_id])
    except AgentError:
        return telemetry
    stdout_path = scontrol_field(info, "StdOut")
    if stdout_path:
        lines, mtime = read_tail(stdout_path)
        telemetry["log_tail"] = lines
        telemetry["log_mtime"] = mtime
    work_dir = scontrol_field(info, "WorkDir")
    if work_dir:
        cached = discovered.get(job_id)
        if cached is None or time.monotonic() - cached[0] >= DISCOVERY_SECONDS:
            cached = (time.monotonic(), find_metric_files(work_dir))
            discovered[job_id] = cached
        telemetry["files"] = read_chunks(cached[1], cursors)
    if include_gpu:
        with contextlib.suppress(AgentError):
            telemetry["nvidia_smi"] = run_command(
                ["srun", "--jobid=" + job_id, "--overlap", "-N1", "-n1", *NVIDIA_SMI],
                timeout=GPU_TIMEOUT,
            )
    return telemetry


def read_tail(path: str) -> Tuple[List[str], Optional[int]]:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - LOG_TAIL_BYTES))
            text = handle.read().decode("utf-8", "replace")
        return text.splitlines()[-LOG_TAIL_LINES:], int(os.stat(path).st_mtime)
    except OSError:
        return [], None


def classify(path: str) -> Optional[str]:
    name = os.path.basename(path).lower()
    if name.startswith("events.out.tfevents."):
        return "tfevents"
    if name.endswith(".jsonl") and "metric" in name:
        return "jsonl"
    if name.endswith(".csv") and ("metric" in name or name == "progress.csv"):
        return "csv"
    if name in CONFIG_NAMES:
        return "config"
    return None


def find_metric_files(work_dir: str) -> List[str]:
    """Newest metric files and config files under the job's working directory."""
    found = []  # type: List[Tuple[float, str]]
    base_depth = work_dir.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(work_dir):
        if root.count(os.sep) - base_depth >= SEARCH_DEPTH - 1:
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs if d not in PRUNE_DIRS]
        for name in files:
            path = os.path.join(root, name)
            if classify(path):
                with contextlib.suppress(OSError):
                    found.append((os.path.getmtime(path), path))
    found.sort(reverse=True)
    metrics = [p for _, p in found if classify(p) != "config"][:MAX_METRIC_FILES]
    configs = [p for _, p in found if classify(p) == "config"][:MAX_CONFIG_FILES]
    return metrics + configs


def read_chunks(paths: List[str], cursors: Dict[str, int]) -> List[Dict[str, object]]:
    """Bytes the server hasn't seen yet, base64-encoded, one entry per file."""
    chunks = []
    for path in paths:
        try:
            size = os.path.getsize(path)
            offset = cursors.get(path, 0)
            if classify(path) == "config":
                if offset == size:
                    continue
                offset, limit = 0, CONFIG_MAX_BYTES
            else:
                if offset == size:
                    continue
                offset, limit = (0 if offset > size else offset), CHUNK_BYTES
            with open(path, "rb") as handle:
                handle.seek(offset)
                data = handle.read(limit)
        except OSError:
            continue
        chunks.append(
            {"path": path, "offset": offset, "size": size, "data": base64.b64encode(data).decode()}
        )
    return chunks


def scontrol_field(output: str, name: str) -> Optional[str]:
    for word in output.split():
        if word.startswith(name + "="):
            return word[len(name) + 1 :]
    return None


# System helpers


def run_command(
    args: List[str], env: Optional[Dict[str, str]] = None, timeout: int = COMMAND_TIMEOUT
) -> str:
    full_env = dict(os.environ, **(env or {}))
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=full_env,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgentError("{} failed: {}".format(args[0], exc)) from exc
    if result.returncode != 0:
        raise AgentError(
            "{} exited {}: {}".format(args[0], result.returncode, result.stderr.strip()[:200])
        )
    return result.stdout


def current_user() -> str:
    return os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name


def script_path() -> str:
    return os.path.abspath(__file__)


def load_config() -> Dict[str, str]:
    try:
        with open(CONFIG_PATH) as handle:
            config = json.load(handle)  # type: Dict[str, str]
            return config
    except (OSError, ValueError):
        raise AgentError(
            "Not installed. Run the install command from the Pulse app.", fatal=True
        ) from None


def save_config(config: Dict[str, str]) -> None:
    save_json(CONFIG_PATH, config)


def load_cursors() -> Dict[str, Dict[str, int]]:
    try:
        with open(STATE_PATH) as handle:
            cursors = json.load(handle).get("cursors", {})  # type: Dict[str, Dict[str, int]]
            return cursors
    except (OSError, ValueError, AttributeError):
        return {}


def save_json(path: str, data: object) -> None:
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle)


def acquire_lock() -> Optional[object]:
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    handle = open(LOCK_PATH, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle  # keep the handle alive to hold the lock


def read_crontab() -> Optional[List[str]]:
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except OSError:
        return None  # no cron on this node
    return result.stdout.splitlines() if result.returncode == 0 else []


def write_crontab(lines: List[str]) -> bool:
    try:
        result = subprocess.run(
            ["crontab", "-"],
            input="\n".join(lines) + "\n",
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return False
    return result.returncode == 0


def add_cron_entry() -> bool:
    lines = read_crontab()
    if lines is None:
        return False
    entry = "* * * * * {} {} run >/dev/null 2>&1 {}".format(sys.executable, script_path(), CRON_TAG)
    return write_crontab([line for line in lines if CRON_TAG not in line] + [entry])


def remove_cron_entry() -> None:
    lines = read_crontab()
    if lines:
        write_crontab([line for line in lines if CRON_TAG not in line])


def log(message: str) -> None:
    sys.stderr.write("pulse-agent: {}\n".format(message))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
