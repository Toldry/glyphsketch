import os
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from glyphsketch.tools.slowdown import (
    CLOCK_TICKS,
    Job,
    ProcessInfo,
    ScheduledAction,
    continue_processes,
    group_jobs,
    load_schedules,
    parse_stat,
    parse_when,
    pause_job,
    process_identities,
    read_process,
    run_scheduled,
    sample_jobs,
    stop_job,
)


def _process(
    pid: int, group_id: int, ticks: int, arguments: tuple[str, ...] = ("x",)
) -> ProcessInfo:
    return ProcessInfo(pid, 1, group_id, "R", arguments, ticks, 100, 1024, 1)


def test_parse_stat_handles_spaces_and_parentheses_in_the_command_name() -> None:
    rest = " ".join(["S", "7", "42", "42"] + ["0"] * 7 + ["30", "12"] + ["0"] * 4 + ["3"])
    rest += " 0 5000 0 10"
    info = parse_stat(99, f"99 (weird (name) x) {rest}", ["python", "-c", "pass"])
    assert (info.parent_pid, info.group_id, info.state) == (7, 42, "S")
    assert info.cpu_ticks == 42 and info.threads == 3 and info.start_ticks == 5000
    assert info.memory_bytes == 10 * os.sysconf("SC_PAGE_SIZE")


def test_parse_when_accepts_clock_times_and_offsets() -> None:
    now = datetime(2026, 9, 27, 14, 30)
    assert parse_when("01:00", now) == datetime(2026, 9, 28, 1, 0)
    assert parse_when("22", now) == datetime(2026, 9, 27, 22, 0)
    assert parse_when("+2h", now) == datetime(2026, 9, 27, 16, 30)
    assert parse_when("+1h30m", now) == datetime(2026, 9, 27, 16, 0)
    assert parse_when("+45m", now) == datetime(2026, 9, 27, 15, 15)
    for text in ("tonight", "25:00", "+"):
        with pytest.raises(ValueError):
            parse_when(text, now)


def test_jobs_group_by_process_group_and_protect_the_editor() -> None:
    before = {10: _process(10, 5, 0), 11: _process(11, 5, 0)}
    after = {
        10: _process(10, 5, int(CLOCK_TICKS)),
        11: _process(11, 5, int(CLOCK_TICKS)),
        20: _process(20, 6, 0, ("/vscode/vscode-server/bin/node", "server.js")),
        30: _process(30, 7, 5 * int(CLOCK_TICKS)),
    }
    jobs = group_jobs(before, after, 1.0, own_group=7)
    assert [job.group_id for job in jobs] == [5, 6]
    assert jobs[0].cores == pytest.approx(2.0) and not jobs[0].protected
    assert jobs[1].protected


def test_job_label_names_the_glyphsketch_module() -> None:
    job = Job(
        5,
        [
            _process(10, 5, 0, ("uv", "run", "python", "-m", "glyphsketch.pipeline", "all")),
            _process(11, 5, 0, ("python", "-c", "from multiprocessing.spawn import spawn_main")),
        ],
        1.0,
        False,
    )
    assert job.label == "glyphsketch.pipeline all"
    assert "cached" in job.restart_note


@pytest.fixture
def busy_process() -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen([sys.executable, "-c", "while True: pass"], start_new_session=True)
    yield process
    process.kill()
    process.wait()


def _job_for(process: subprocess.Popen[bytes]) -> Job:
    return next(job for job in sample_jobs(0.5) if job.group_id == process.pid)


def _state(pid: int) -> str:
    info = read_process(pid)
    return info.state if info else "gone"


def test_pause_continue_and_stop_a_real_job(busy_process: subprocess.Popen[bytes]) -> None:
    job = _job_for(busy_process)
    assert job.cores > 0.5 and not job.protected
    pause_job(job)
    time.sleep(0.2)
    assert _state(busy_process.pid) == "T"
    assert continue_processes(process_identities(job)) == 1
    time.sleep(0.2)
    assert _state(busy_process.pid) in ("R", "S")
    assert stop_job(job, grace_seconds=5)
    assert busy_process.wait(timeout=5) != 0


def test_a_scheduled_continue_resumes_the_paused_job(
    busy_process: subprocess.Popen[bytes], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = _job_for(busy_process)
    pause_job(job)
    schedule = ScheduledAction(
        action="continue",
        at=time.time() + 60,
        label=job.label,
        group_id=job.group_id,
        processes=[list(identity) for identity in process_identities(job)],
    )
    schedule.save()
    assert [item.identifier for item in load_schedules()] == [schedule.identifier]
    clock = [time.time()]
    monkeypatch.setattr("glyphsketch.tools.slowdown.time.time", lambda: clock[0])
    run_scheduled(schedule.path, sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    time.sleep(0.2)
    assert _state(busy_process.pid) in ("R", "S")
    assert not schedule.path.exists()
    assert "continued" in (tmp_path / "slowdown" / "slowdown.log").read_text()


def test_a_cancelled_schedule_does_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    output = tmp_path / "out.log"
    schedule = ScheduledAction(
        action="restart",
        at=time.time() + 3600,
        label="test",
        arguments=[sys.executable, "-c", "print('ran')"],
        output_file=str(output),
    )
    schedule.save()
    run_scheduled(schedule.path, sleep=lambda _: schedule.path.unlink())
    assert not output.exists()


def test_a_scheduled_restart_runs_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    output = tmp_path / "out.log"
    output.write_text("before\n")
    schedule = ScheduledAction(
        action="restart",
        at=time.time() - 1,
        label="test",
        arguments=[sys.executable, "-c", "import os; print(os.getcwd())"],
        working_dir=str(tmp_path),
        output_file=str(output),
    )
    schedule.save()
    run_scheduled(schedule.path)
    deadline = time.time() + 10
    while time.time() < deadline and output.read_text().count("\n") < 2:
        time.sleep(0.1)
    assert output.read_text() == f"before\n{tmp_path}\n"
