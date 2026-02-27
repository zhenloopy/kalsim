import argparse
import atexit
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PID_FILE = Path("data/collector.pid")
LOG_FILE = Path("data/collector.log")
DEFAULT_INTERVAL = 60

logger = logging.getLogger(__name__)


def _is_pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.c_ulong(260)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(handle)
        if ok:
            name = buf.value.lower()
            return "python" in name
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def collector_status() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return False
    return _is_pid_alive(pid)


def start_collector(interval: int = DEFAULT_INTERVAL):
    if collector_status():
        print("Collector is already running.")
        return

    if PID_FILE.exists():
        PID_FILE.unlink()

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "src.collector", "_run", "--interval", str(interval)]
    log_fh = open(LOG_FILE, "a")

    if sys.platform == "win32":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=log_fh,
            creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=log_fh,
            start_new_session=True,
        )

    log_fh.close()
    PID_FILE.write_text(str(proc.pid))
    print(f"Collector started (PID {proc.pid})")


def stop_collector():
    if not PID_FILE.exists():
        print("Collector is not running.")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        print("Collector is not running (stale PID file removed).")
        return

    if not _is_pid_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        print("Collector is not running (stale PID file removed).")
        return

    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_TERMINATE = 0x0001
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGTERM)

    PID_FILE.unlink(missing_ok=True)
    print(f"Collector stopped (PID {pid})")


def _run_collector(interval: int):
    load_dotenv()

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    from src.position_feed import PositionFeed
    from src.nav_store import NavStore, NavSnapshot

    nav_store = NavStore()
    my_pid = os.getpid()

    def cleanup():
        nav_store.close()
        try:
            if PID_FILE.exists() and int(PID_FILE.read_text().strip()) == my_pid:
                PID_FILE.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    atexit.register(cleanup)

    if sys.platform != "win32":
        def handle_signal(signum, frame):
            sys.exit(0)
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

    logger.info(f"Collector started, interval={interval}s, PID={my_pid}")

    feed = PositionFeed()

    while True:
        try:
            positions = feed.get_positions()
            cash, portfolio_value = feed.client.get_balance()

            nav = cash
            for pos in positions:
                nav += pos.quantity * pos.current_mid

            pnl = sum(
                pos.quantity * (pos.current_mid - pos.entry_price)
                for pos in positions
            )

            snap = NavSnapshot(
                timestamp_utc=time.time(),
                nav=nav,
                cash=cash,
                portfolio_value=portfolio_value,
                unrealized_pnl=pnl,
                position_count=len(positions),
            )
            nav_store.record(snap)
            logger.info(
                f"NAV=${nav:,.2f} cash=${cash:,.2f} "
                f"positions={len(positions)} pnl=${pnl:+,.2f}"
            )
        except Exception as e:
            logger.error(f"Collection failed: {e}")

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="collector",
        description="Background NAV collector for kalsim",
    )
    parser.add_argument("command", choices=["start", "stop", "status", "_run"])
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    args = parser.parse_args()

    if args.command == "start":
        start_collector(args.interval)
    elif args.command == "stop":
        stop_collector()
    elif args.command == "status":
        if collector_status():
            pid = int(PID_FILE.read_text().strip())
            print(f"Collector is running (PID {pid})")
        else:
            print("Collector is not running")
    elif args.command == "_run":
        _run_collector(args.interval)
