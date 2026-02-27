import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NavSnapshot:
    timestamp_utc: float
    nav: float
    cash: float
    portfolio_value: float
    unrealized_pnl: float
    position_count: int


class NavStore:
    def __init__(self, db_path: str = "data/nav.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS nav_snapshots (
                timestamp_utc REAL PRIMARY KEY,
                nav REAL NOT NULL,
                cash REAL NOT NULL,
                portfolio_value REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                position_count INTEGER NOT NULL
            )
        """)
        self._conn.commit()

    def record(self, snap: NavSnapshot):
        self._conn.execute(
            "INSERT OR REPLACE INTO nav_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            (snap.timestamp_utc, snap.nav, snap.cash, snap.portfolio_value,
             snap.unrealized_pnl, snap.position_count),
        )
        self._conn.commit()

    def query(self, start: float, end: float, max_points: int = 500) -> list[NavSnapshot]:
        rows = self._conn.execute(
            "SELECT timestamp_utc, nav, cash, portfolio_value, unrealized_pnl, position_count "
            "FROM nav_snapshots WHERE timestamp_utc >= ? AND timestamp_utc <= ? "
            "ORDER BY timestamp_utc",
            (start, end),
        ).fetchall()

        if len(rows) <= max_points:
            return [NavSnapshot(*r) for r in rows]

        return self._downsample(rows, max_points)

    def _downsample(self, rows: list[tuple], max_points: int) -> list[NavSnapshot]:
        n = len(rows)
        bucket_size = n / max_points
        result = []
        for i in range(max_points):
            lo = int(i * bucket_size)
            hi = int((i + 1) * bucket_size)
            hi = min(hi, n)
            if lo >= hi:
                continue
            bucket = rows[lo:hi]
            avg_ts = sum(r[0] for r in bucket) / len(bucket)
            avg_nav = sum(r[1] for r in bucket) / len(bucket)
            avg_cash = sum(r[2] for r in bucket) / len(bucket)
            avg_pv = sum(r[3] for r in bucket) / len(bucket)
            avg_pnl = sum(r[4] for r in bucket) / len(bucket)
            avg_count = round(sum(r[5] for r in bucket) / len(bucket))
            result.append(NavSnapshot(avg_ts, avg_nav, avg_cash, avg_pv, avg_pnl, avg_count))
        return result

    def latest(self) -> NavSnapshot | None:
        row = self._conn.execute(
            "SELECT timestamp_utc, nav, cash, portfolio_value, unrealized_pnl, position_count "
            "FROM nav_snapshots ORDER BY timestamp_utc DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return NavSnapshot(*row)

    def close(self):
        self._conn.close()
