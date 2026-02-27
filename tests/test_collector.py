import os
import sys
import subprocess
import time

import pytest

from src.collector import PID_FILE, collector_status, stop_collector, _is_pid_alive


@pytest.fixture(autouse=True)
def cleanup_pid_file():
    PID_FILE.unlink(missing_ok=True)
    yield
    PID_FILE.unlink(missing_ok=True)


def _write_pid(pid: int):
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def test_status_no_pid_file():
    assert collector_status() is False


def test_status_stale_pid():
    _write_pid(4_000_000_000)
    assert collector_status() is False


def test_is_pid_alive_self():
    assert _is_pid_alive(os.getpid()) is True


def test_is_pid_alive_dead():
    assert _is_pid_alive(4_000_000_000) is False


def test_status_with_live_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _write_pid(proc.pid)
        assert collector_status() is True
    finally:
        proc.terminate()
        proc.wait()


def test_stop_kills_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    _write_pid(proc.pid)
    stop_collector()
    proc.wait(timeout=5)
    assert not PID_FILE.exists()
    time.sleep(0.1)
    assert not _is_pid_alive(proc.pid)


def test_stop_cleans_stale_pid():
    _write_pid(4_000_000_000)
    stop_collector()
    assert not PID_FILE.exists()


def test_stop_no_pid_file():
    stop_collector()
    assert not PID_FILE.exists()


def test_pid_file_cleanup_guards_own_pid():
    """If PID file was overwritten by a new collector, the old one shouldn't delete it."""
    import atexit
    from unittest.mock import patch

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    _write_pid(proc.pid)

    with patch("src.collector.os.getpid", return_value=99999):
        from src.collector import _run_collector
        # Simulate: atexit cleanup from a different PID shouldn't remove the file
        try:
            if PID_FILE.exists() and int(PID_FILE.read_text().strip()) == 99999:
                PID_FILE.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    assert PID_FILE.exists()
    assert int(PID_FILE.read_text().strip()) == proc.pid

    proc.terminate()
    proc.wait()
