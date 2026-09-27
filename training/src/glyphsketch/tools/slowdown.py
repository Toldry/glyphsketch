#!/usr/bin/env python3
"""Find what in this devcontainer slows the machine down, then pause, postpone or stop it.

Run it in a devcontainer terminal: ``make slowdown`` (or ``python3
training/src/glyphsketch/tools/slowdown.py``). It samples CPU use for a second, lists the
busy jobs, and offers, for each one:

- pause now and continue automatically at a later time (progress is kept),
- stop now and restart the same command at a later time (frees memory; a pipeline run
  skips the stages it already finished),
- stop for good.

A job is a process group: a command and everything it started (for example the pipeline
and its worker processes). VS Code, its extensions and Claude Code are shown but never
touched. Scheduled actions live in ``$DATA_DIR/slowdown/`` and are carried out by a small
background process, so the devcontainer must keep running until then. Standard library
only, so it works before ``make sync``.
"""

import argparse
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

PROC = Path("/proc")
CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
GIGABYTE = 1024**3
SAMPLE_SECONDS = 1.0
SHOWN_CORES = 0.25
SHOWN_BYTES = 512 * 1024**2
HEAVY_CORES = 1.0
HEAVY_BYTES = 2 * GIGABYTE
DEFAULT_WHEN = "01:00"
STOP_GRACE_SECONDS = 10.0
SCHEDULER_FLAG = "--run-scheduled"
INFRASTRUCTURE_PATTERN = re.compile(r"vscode-server|vscode-remote-containers|(^|/)claude( |$)")
MODULE_PATTERN = re.compile(r"-m (glyphsketch\.\S+)(.*)")


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int
    group_id: int
    state: str
    arguments: tuple[str, ...]
    cpu_ticks: int
    start_ticks: int
    memory_bytes: int
    threads: int


def parse_stat(pid: int, stat: str, arguments: Sequence[str]) -> ProcessInfo:
    """``/proc/<pid>/stat``: the command name is in parentheses and may contain spaces."""
    fields = stat[stat.rfind(")") + 2 :].split()
    return ProcessInfo(
        pid=pid,
        parent_pid=int(fields[1]),
        group_id=int(fields[2]),
        state=fields[0],
        arguments=tuple(arguments),
        cpu_ticks=int(fields[11]) + int(fields[12]),
        start_ticks=int(fields[19]),
        memory_bytes=int(fields[21]) * PAGE_SIZE,
        threads=int(fields[17]),
    )


def read_process(pid: int) -> ProcessInfo | None:
    try:
        stat = (PROC / str(pid) / "stat").read_text()
        raw_arguments = (PROC / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    arguments = [part.decode(errors="replace") for part in raw_arguments.split(b"\0") if part]
    info = parse_stat(pid, stat, arguments)
    return None if info.state in ("Z", "X") else info


def read_processes() -> dict[int, ProcessInfo]:
    processes = {}
    for entry in PROC.iterdir():
        if entry.name.isdigit() and (info := read_process(int(entry.name))):
            processes[info.pid] = info
    return processes


@dataclass
class Job:
    group_id: int
    processes: list[ProcessInfo]
    cores: float
    protected: bool

    @property
    def memory_bytes(self) -> int:
        return sum(process.memory_bytes for process in self.processes)

    @property
    def paused(self) -> bool:
        return all(process.state == "T" for process in self.processes)

    @property
    def root(self) -> ProcessInfo:
        pids = {process.pid for process in self.processes}
        roots = [process for process in self.processes if process.parent_pid not in pids]
        return min(roots or self.processes, key=lambda process: process.pid)

    @property
    def label(self) -> str:
        if self.protected:
            return "VS Code server and extensions (including Claude Code)"
        for process in sorted(self.processes, key=lambda process: process.pid):
            if match := MODULE_PATTERN.search(" ".join(process.arguments)):
                return shorten((match.group(1) + match.group(2)).strip())
        return shorten(" ".join(self.root.arguments) or "(unknown command)")

    @property
    def restart_note(self) -> str:
        if "glyphsketch.pipeline" in self.label:
            return "Finished pipeline stages are cached; a restart redoes only the current stage."
        if "glyphsketch.model" in self.label:
            return "A restart starts this training run over from the beginning."
        return "A restart runs the command again from the beginning."


def shorten(text: str, width: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def is_infrastructure(process: ProcessInfo) -> bool:
    return process.pid == 1 or bool(INFRASTRUCTURE_PATTERN.search(" ".join(process.arguments)))


def group_jobs(
    before: dict[int, ProcessInfo],
    after: dict[int, ProcessInfo],
    seconds: float,
    own_group: int,
) -> list[Job]:
    """Jobs by process group, busiest first; CPU use is measured between the two snapshots."""
    groups: dict[int, list[ProcessInfo]] = {}
    for process in after.values():
        if process.group_id != own_group and SCHEDULER_FLAG not in process.arguments:
            groups.setdefault(process.group_id, []).append(process)
    jobs = []
    for group_id, members in groups.items():
        ticks = 0
        for process in members:
            earlier = before.get(process.pid)
            same = earlier is not None and earlier.start_ticks == process.start_ticks
            ticks += process.cpu_ticks - (earlier.cpu_ticks if earlier and same else 0)
        cores = ticks / CLOCK_TICKS / seconds
        protected = any(is_infrastructure(process) for process in members)
        jobs.append(Job(group_id, members, cores, protected))
    return sorted(jobs, key=lambda job: (job.cores, job.memory_bytes), reverse=True)


def sample_jobs(seconds: float = SAMPLE_SECONDS) -> list[Job]:
    before = read_processes()
    time.sleep(seconds)
    return group_jobs(before, read_processes(), seconds, os.getpgrp())


def is_notable(job: Job) -> bool:
    return job.cores >= SHOWN_CORES or job.memory_bytes >= SHOWN_BYTES or job.paused


def is_heavy(job: Job) -> bool:
    return job.cores >= HEAVY_CORES or job.memory_bytes >= HEAVY_BYTES


# System summary.


def read_meminfo() -> dict[str, int]:
    values = {}
    for line in (PROC / "meminfo").read_text().splitlines():
        name, _, rest = line.partition(":")
        values[name] = int(rest.split()[0]) * 1024
    return values


def uptime_seconds() -> float:
    return float((PROC / "uptime").read_text().split()[0])


def system_lines() -> list[str]:
    cores = os.cpu_count() or 1
    one, five, _ = os.getloadavg()
    memory = read_meminfo()
    total = memory["MemTotal"]
    used = total - memory.get("MemAvailable", memory["MemFree"])
    swap_used = memory.get("SwapTotal", 0) - memory.get("SwapFree", 0)
    return [
        f"CPU:    {cores} cores; load {one:.1f} over the last minute, {five:.1f} over 5 minutes",
        f"Memory: {used / GIGABYTE:.1f} of {total / GIGABYTE:.1f} GB in use; "
        f"swap {swap_used / GIGABYTE:.1f} GB in use",
    ]


def memory_is_tight() -> bool:
    memory = read_meminfo()
    swap_used = memory.get("SwapTotal", 0) - memory.get("SwapFree", 0)
    available = memory.get("MemAvailable", memory["MemFree"])
    return available < 0.1 * memory["MemTotal"] or swap_used > GIGABYTE


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return f"{int(seconds)} s"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def job_age(job: Job) -> str:
    return format_duration(uptime_seconds() - job.root.start_ticks / CLOCK_TICKS)


# Pausing, continuing and stopping.


def process_identities(job: Job) -> list[tuple[int, int]]:
    """(pid, start time) pairs: the start time guards against a reused pid."""
    return [(process.pid, process.start_ticks) for process in job.processes]


def still_running(pid: int, start_ticks: int) -> bool:
    process = read_process(pid)
    return process is not None and process.start_ticks == start_ticks


def signal_processes(identities: Sequence[Sequence[int]], signal_number: int) -> int:
    signalled = 0
    for pid, start_ticks in identities:
        if still_running(pid, start_ticks):
            try:
                os.kill(pid, signal_number)
                signalled += 1
            except ProcessLookupError:
                pass
    return signalled


def pause_job(job: Job) -> None:
    os.killpg(job.group_id, signal.SIGSTOP)


def continue_processes(identities: Sequence[Sequence[int]]) -> int:
    return signal_processes(identities, signal.SIGCONT)


def stop_job(job: Job, grace_seconds: float = STOP_GRACE_SECONDS) -> bool:
    """SIGTERM (and SIGCONT, so a paused job receives it), then SIGKILL; True once all exit."""
    identities = process_identities(job)
    for signal_number in (signal.SIGTERM, signal.SIGCONT):
        try:
            os.killpg(job.group_id, signal_number)
        except ProcessLookupError:
            return True
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not any(still_running(pid, start) for pid, start in identities):
            return True
        time.sleep(0.2)
    signal_processes(identities, signal.SIGKILL)
    time.sleep(0.5)
    return not any(still_running(pid, start) for pid, start in identities)


# Scheduled actions.


def schedule_dir() -> Path:
    base = Path(os.environ.get("DATA_DIR") or Path.home() / ".cache" / "glyphsketch")
    return base / "slowdown"


@dataclass
class ScheduledAction:
    """``continue`` a paused job, or ``restart`` a stopped job's command, at ``at`` (epoch)."""

    action: str
    at: float
    label: str
    group_id: int = 0
    processes: list[list[int]] = field(default_factory=list)
    arguments: list[str] = field(default_factory=list)
    working_dir: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    output_file: str = ""
    identifier: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    scheduler_pid: int = 0

    @property
    def path(self) -> Path:
        return schedule_dir() / f"{self.identifier}.json"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The saved environment may hold tokens, so only the owner may read the file.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, indent=1)

    @classmethod
    def load(cls, path: Path) -> "ScheduledAction":
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def scheduler_alive(self) -> bool:
        return self.scheduler_pid > 0 and (PROC / str(self.scheduler_pid)).exists()

    def describe(self) -> str:
        when = datetime.fromtimestamp(self.at).strftime("%H:%M")
        remaining = format_duration(max(0.0, self.at - time.time()))
        verb = "continue" if self.action == "continue" else "restart"
        return f"{verb} {self.label} at {when} (in {remaining})"


def load_schedules() -> list[ScheduledAction]:
    directory = schedule_dir()
    if not directory.is_dir():
        return []
    schedules = []
    for path in sorted(directory.glob("*.json")):
        try:
            schedules.append(ScheduledAction.load(path))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(schedules, key=lambda schedule: schedule.at)


def log_line(message: str) -> None:
    directory = schedule_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with (directory / "slowdown.log").open("a", encoding="utf-8") as log:
        log.write(f"{stamp}  {message}\n")


def restart_command(schedule: ScheduledAction) -> subprocess.Popen[bytes]:
    output = Path(schedule.output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("ab") as handle:
        return subprocess.Popen(
            schedule.arguments,
            cwd=schedule.working_dir or None,
            env=schedule.environment or None,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def carry_out(schedule: ScheduledAction) -> str:
    if schedule.action == "continue":
        count = continue_processes(schedule.processes)
        return f"continued {schedule.label} ({count} processes)"
    process = restart_command(schedule)
    return f"restarted {schedule.label} as pid {process.pid}; output: {schedule.output_file}"


def run_scheduled(path: Path, sleep: Callable[[float], None] = time.sleep) -> None:
    """Body of the background scheduler: wait for the time (by wall clock), then act."""
    schedule = ScheduledAction.load(path)
    while (remaining := schedule.at - time.time()) > 0:
        sleep(min(remaining, 30.0))
        if not path.exists():
            return  # cancelled
    try:
        log_line(carry_out(schedule))
    except OSError as error:
        log_line(f"could not {schedule.action} {schedule.label}: {error}")
    path.unlink(missing_ok=True)


def start_scheduler(schedule: ScheduledAction) -> None:
    schedule.save()
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), SCHEDULER_FLAG, str(schedule.path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    schedule.scheduler_pid = process.pid
    schedule.save()


def cancel_schedule(schedule: ScheduledAction) -> None:
    schedule.path.unlink(missing_ok=True)
    if schedule.scheduler_alive():
        with contextlib.suppress(ProcessLookupError):
            os.kill(schedule.scheduler_pid, signal.SIGTERM)


def restart_schedule(job: Job, at: float) -> ScheduledAction:
    """Capture what is needed to run the job's command again: arguments, directory, env."""
    root = PROC / str(job.root.pid)
    working_dir = os.readlink(root / "cwd")
    raw_environment = (root / "environ").read_bytes().split(b"\0")
    environment = dict(
        entry.decode(errors="replace").split("=", 1) for entry in raw_environment if b"=" in entry
    )
    try:
        output_file = os.readlink(root / "fd" / "1")
    except OSError:
        output_file = ""
    if not os.path.isfile(output_file):
        stamp = datetime.fromtimestamp(at).strftime("%Y%m%d-%H%M")
        output_file = str(schedule_dir() / f"restart-{stamp}.log")
    return ScheduledAction(
        action="restart",
        at=at,
        label=job.label,
        arguments=list(job.root.arguments),
        working_dir=working_dir,
        environment=environment,
        output_file=output_file,
    )


def parse_when(text: str, now: datetime) -> datetime:
    """``HH:MM`` or ``H`` (next time the clock shows it), or ``+2h``, ``+45m``, ``+1h30m``."""
    text = text.strip().lower()
    relative = re.fullmatch(r"\+\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?", text)
    if relative and any(relative.groups()):
        hours, minutes = (int(value or 0) for value in relative.groups())
        return now + timedelta(hours=hours, minutes=minutes)
    clock = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", text)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
        if hour < 24 and minute < 60:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return target if target > now else target + timedelta(days=1)
    raise ValueError(f"Not a time: {text!r}. Use HH:MM (e.g. 01:00) or +2h / +45m.")


# Interaction.


def ask(prompt: str) -> str:
    return input(prompt).strip().lower()


def ask_time(question: str) -> float | None:
    while True:
        answer = ask(f"{question} [HH:MM, +2h or +45m; Enter for {DEFAULT_WHEN}; b to go back] ")
        if answer == "b":
            return None
        try:
            target = parse_when(answer or DEFAULT_WHEN, datetime.now())
        except ValueError as error:
            print(f"  {error}")
            continue
        return target.timestamp()


@dataclass
class Item:
    job: Job | None = None
    schedule: ScheduledAction | None = None


def print_report(jobs: list[Job], schedules: list[ScheduledAction]) -> list[Item]:
    print()
    for line in system_lines():
        print(line)
    print()
    items: list[Item] = []
    notable = [job for job in jobs if is_notable(job)]
    if notable:
        print("   #  CPU (cores)  Memory    Running for  What")
        for job in notable:
            marker = "  -"
            if not job.protected:
                items.append(Item(job=job))
                marker = f"{len(items):3d}"
            state = "  [paused]" if job.paused else ""
            pending = [item for item in schedules if item.group_id == job.group_id]
            if pending:
                state += f"  [{pending[0].describe()}]"
            count = f"  ({len(job.processes)} processes)" if len(job.processes) > 1 else ""
            print(
                f"{marker}  {job.cores:11.1f}  {job.memory_bytes / GIGABYTE:5.1f} GB  "
                f"{job_age(job):>11}  {job.label}{count}{state}"
            )
    else:
        print("Nothing in this container is busy right now.")
    restarts = [schedule for schedule in schedules if schedule.action == "restart"]
    if restarts:
        print("\nScheduled restarts:")
        for schedule in restarts:
            items.append(Item(schedule=schedule))
            lost = "" if schedule.scheduler_alive() else "  [scheduler gone: will not happen]"
            print(f"{len(items):3d}  {schedule.describe()}{lost}")
    print()
    print_verdict(jobs)
    return items


def print_verdict(jobs: list[Job]) -> None:
    cores = os.cpu_count() or 1
    heavy = [job for job in jobs if not job.protected and not job.paused and is_heavy(job)]
    if heavy:
        job = heavy[0]
        print(
            f"Most likely cause: {job.label} — {job.cores:.1f} of {cores} cores and "
            f"{job.memory_bytes / GIGABYTE:.1f} GB of memory."
        )
    elif memory_is_tight():
        print("Nothing is busy, but memory is tight: a paused job still holds its memory.")
    else:
        print(
            "Nothing in this container is heavy, so the slowness probably comes from outside it\n"
            "(Windows or another program). WSL 2 can also keep memory it used earlier for file\n"
            "caching; `wsl --shutdown` in Windows gives it back, but it also stops this container."
        )


def act_on_job(job: Job, schedules: list[ScheduledAction]) -> None:
    pending = [schedule for schedule in schedules if schedule.group_id == job.group_id]
    print(f"\n{job.label}\n  command: {shorten(' '.join(job.root.arguments), 90)}")
    if job.paused:
        options = {
            "c": "Continue it now",
            "l": "Continue it later (change the time)",
            "s": "Stop it for good",
        }
    else:
        options = {
            "p": "Pause now, continue automatically later (keeps its progress and its memory)",
            "r": "Stop now, restart automatically later (frees its memory)\n      "
            + job.restart_note,
            "s": "Stop it for good",
        }
    for key, text in options.items():
        print(f"  [{key}] {text}")
    print("  [b] Back")
    choice = ask("> ")
    if choice in ("c", "l", "s"):
        for schedule in pending:
            cancel_schedule(schedule)
    if choice == "c" and job.paused:
        continue_processes(process_identities(job))
        print("Continued.")
    elif choice == "l" and job.paused:
        schedule_continue(job)
    elif choice == "p" and not job.paused:
        pause_job(job)
        print("Paused.")
        schedule_continue(job)
    elif choice == "r" and not job.paused:
        at = ask_time("Restart when?")
        if at is None:
            return
        schedule = restart_schedule(job, at)
        if stop_job(job):
            start_scheduler(schedule)
            print(f"Stopped. Will {schedule.describe()}; output goes to {schedule.output_file}")
        else:
            print("Some processes did not exit; nothing was scheduled.")
    elif choice == "s":
        confirm = ask("Stop it for good? Work not yet saved is lost. [y/N] ")
        if confirm == "y":
            print("Stopped." if stop_job(job) else "Some processes did not exit.")


def schedule_continue(job: Job) -> None:
    at = ask_time("Continue when?")
    if at is None:
        print("It stays paused until you continue it from this script.")
        return
    schedule = ScheduledAction(
        action="continue",
        at=at,
        label=job.label,
        group_id=job.group_id,
        processes=[list(identity) for identity in process_identities(job)],
    )
    start_scheduler(schedule)
    print(f"Will {schedule.describe()}. Paused jobs still hold their memory.")


def act_on_schedule(schedule: ScheduledAction) -> None:
    print(f"\n{schedule.describe()}\n  [n] Run it now\n  [x] Cancel it\n  [b] Back")
    choice = ask("> ")
    if choice == "n":
        cancel_schedule(schedule)
        print(carry_out(schedule))
    elif choice == "x":
        cancel_schedule(schedule)
        print("Cancelled.")


def interactive() -> None:
    while True:
        print(f"Measuring CPU use for {SAMPLE_SECONDS:.0f} s…")
        schedules = load_schedules()
        items = print_report(sample_jobs(), schedules)
        numbers = f"1–{len(items)} to act on an item, " if items else ""
        choice = ask(f"\nEnter {numbers}r to refresh, or q to quit: ")
        if choice == "q":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            item = items[int(choice) - 1]
            try:
                if item.job:
                    act_on_job(item.job, schedules)
                elif item.schedule:
                    act_on_schedule(item.schedule)
            except PermissionError:
                print("Not allowed to signal that job (it belongs to another user).")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--list", action="store_true", help="print the report and exit")
    parser.add_argument(SCHEDULER_FLAG, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.run_scheduled:
        run_scheduled(args.run_scheduled)
        return 0
    if args.list:
        print_report(sample_jobs(), load_schedules())
        return 0
    try:
        interactive()
    except (KeyboardInterrupt, EOFError):
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
