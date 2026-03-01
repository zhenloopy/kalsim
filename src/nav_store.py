import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NavOHLC:
    timestamp_utc: float
    open: float
    high: float
    low: float
    close: float


@dataclass
class NavSnapshot:
    timestamp_utc: float
    nav: float
    cash: float
    portfolio_value: float
    unrealized_pnl: float
    position_count: int


@dataclass
class PositionSnapshot:
    timestamp_utc: float
    contract_id: str
    platform: str
    canonical_event_id: str
    quantity: int
    entry_price: float
    current_mid: float
    market_prob: float
    model_prob: float
    edge: float
    resolves_at: float
    tte_days: float
    fee_adjusted_breakeven: float


class NavStore:
    def __init__(self, db_path: str = "data/nav.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
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
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS position_snapshots (
                timestamp_utc REAL NOT NULL,
                contract_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                canonical_event_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                current_mid REAL NOT NULL,
                market_prob REAL NOT NULL,
                model_prob REAL NOT NULL,
                edge REAL NOT NULL,
                resolves_at REAL NOT NULL,
                tte_days REAL NOT NULL,
                fee_adjusted_breakeven REAL NOT NULL,
                PRIMARY KEY (timestamp_utc, contract_id)
            )
        """)
        self._conn.commit()

    def record(self, snap: NavSnapshot, positions: list[PositionSnapshot] | None = None):
        self._conn.execute(
            "INSERT OR REPLACE INTO nav_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            (snap.timestamp_utc, snap.nav, snap.cash, snap.portfolio_value,
             snap.unrealized_pnl, snap.position_count),
        )
        if positions:
            self._conn.executemany(
                "INSERT OR REPLACE INTO position_snapshots VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (p.timestamp_utc, p.contract_id, p.platform,
                     p.canonical_event_id, p.quantity, p.entry_price,
                     p.current_mid, p.market_prob, p.model_prob, p.edge,
                     p.resolves_at, p.tte_days, p.fee_adjusted_breakeven)
                    for p in positions
                ],
            )
        self._conn.commit()

    def query(self, start: float, end: float, max_points: int = 500) -> list[NavSnapshot]:
        rows = self._conn.execute(
            "SELECT timestamp_utc, nav, cash, portfolio_value, unrealized_pnl, position_count "
            "FROM nav_snapshots WHERE timestamp_utc >= ? AND timestamp_utc <= ? "
            "ORDER BY timestamp_utc",
            (start, end),
        ).fetchall()

        if max_points == 0 or len(rows) <= max_points:
            return [NavSnapshot(*r) for r in rows]

        return self._downsample(rows, max_points)

    def _downsample(self, rows: list[tuple], max_points: int) -> list[NavSnapshot]:
        n = len(rows)
        if max_points >= n:
            return [NavSnapshot(*r) for r in rows]

        result = [rows[0]]
        bucket_size = (n - 2) / (max_points - 2)

        prev_idx = 0
        for i in range(max_points - 2):
            b_start = int(1 + i * bucket_size)
            b_end = int(1 + (i + 1) * bucket_size)
            b_end = min(b_end, n - 1)

            n_start = int(1 + (i + 1) * bucket_size)
            n_end = int(1 + (i + 2) * bucket_size)
            n_end = min(n_end, n)
            if n_start >= n:
                n_start = n - 1
            next_bucket = rows[n_start:n_end] or [rows[-1]]
            avg_x = sum(r[0] for r in next_bucket) / len(next_bucket)
            avg_y = sum(r[1] for r in next_bucket) / len(next_bucket)

            px, py = rows[prev_idx][0], rows[prev_idx][1]
            max_area = -1.0
            best = b_start
            for j in range(b_start, b_end):
                area = abs(
                    px * (rows[j][1] - avg_y)
                    + rows[j][0] * (avg_y - py)
                    + avg_x * (py - rows[j][1])
                )
                if area > max_area:
                    max_area = area
                    best = j
            result.append(rows[best])
            prev_idx = best

        result.append(rows[-1])
        return [NavSnapshot(*r) for r in result]

    def query_ohlc(self, start: float, end: float, bucket_seconds: int) -> list[NavOHLC]:
        rows = self._conn.execute(
            "SELECT timestamp_utc, nav FROM nav_snapshots "
            "WHERE timestamp_utc >= ? AND timestamp_utc <= ? "
            "ORDER BY timestamp_utc",
            (start, end),
        ).fetchall()

        if not rows:
            return []

        buckets: dict[float, list[tuple[float, float]]] = {}
        for ts, nav in rows:
            key = (ts // bucket_seconds) * bucket_seconds
            buckets.setdefault(key, []).append((ts, nav))

        result = []
        for key in sorted(buckets):
            points = buckets[key]
            navs = [n for _, n in points]
            result.append(NavOHLC(
                timestamp_utc=key,
                open=navs[0],
                high=max(navs),
                low=min(navs),
                close=navs[-1],
            ))
        return result

    def latest(self) -> NavSnapshot | None:
        row = self._conn.execute(
            "SELECT timestamp_utc, nav, cash, portfolio_value, unrealized_pnl, position_count "
            "FROM nav_snapshots ORDER BY timestamp_utc DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return NavSnapshot(*row)

    def query_positions(self, timestamp_utc: float) -> list[PositionSnapshot]:
        rows = self._conn.execute(
            "SELECT timestamp_utc, contract_id, platform, canonical_event_id, "
            "quantity, entry_price, current_mid, market_prob, model_prob, edge, "
            "resolves_at, tte_days, fee_adjusted_breakeven "
            "FROM position_snapshots WHERE timestamp_utc = ? "
            "ORDER BY contract_id",
            (timestamp_utc,),
        ).fetchall()
        return [PositionSnapshot(*r) for r in rows]

    def latest_positions(self) -> list[PositionSnapshot]:
        row = self._conn.execute(
            "SELECT MAX(timestamp_utc) FROM position_snapshots"
        ).fetchone()
        if row is None or row[0] is None:
            return []
        return self.query_positions(row[0])

    def storage_info(self) -> dict:
        page_count = self._conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = self._conn.execute("PRAGMA page_size").fetchone()[0]
        size_bytes = page_count * page_size
        nav_rows = self._conn.execute("SELECT COUNT(*) FROM nav_snapshots").fetchone()[0]
        pos_rows = self._conn.execute("SELECT COUNT(*) FROM position_snapshots").fetchone()[0]
        return {
            "size_bytes": size_bytes,
            "nav_snapshots": nav_rows,
            "position_snapshots": pos_rows,
        }

    def clear_all(self):
        self._conn.execute("DELETE FROM position_snapshots")
        self._conn.execute("DELETE FROM nav_snapshots")
        self._conn.commit()
        self._conn.execute("VACUUM")

    def close(self):
        self._conn.close()
