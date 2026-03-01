import os
import tempfile
import pytest
from src.nav_store import NavStore, NavSnapshot, NavOHLC, PositionSnapshot


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_nav.db")


def _snap(ts, nav=1000.0, cash=500.0, pv=500.0, pnl=50.0, count=3):
    return NavSnapshot(ts, nav, cash, pv, pnl, count)


class TestRoundTrip:
    def test_write_close_reopen_read(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(100.0, nav=1234.56))
        store.close()

        store2 = NavStore(tmp_db)
        result = store2.latest()
        store2.close()

        assert result is not None
        assert abs(result.nav - 1234.56) < 1e-6
        assert abs(result.timestamp_utc - 100.0) < 1e-6

    def test_multiple_snapshots_latest_returns_most_recent(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(100.0, nav=1000.0))
        store.record(_snap(200.0, nav=2000.0))
        store.record(_snap(150.0, nav=1500.0))
        result = store.latest()
        store.close()
        assert abs(result.timestamp_utc - 200.0) < 1e-6
        assert abs(result.nav - 2000.0) < 1e-6


class TestTimeRangeQuery:
    def test_filters_by_time_range(self, tmp_db):
        store = NavStore(tmp_db)
        for i in range(10):
            store.record(_snap(float(i * 100), nav=1000.0 + i))
        results = store.query(200.0, 600.0)
        store.close()
        assert len(results) == 5
        assert results[0].timestamp_utc == 200.0
        assert results[-1].timestamp_utc == 600.0

    def test_empty_range_returns_empty(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(100.0))
        results = store.query(500.0, 600.0)
        store.close()
        assert results == []


class TestDownsampling:
    def test_1000_points_downsampled_to_100(self, tmp_db):
        store = NavStore(tmp_db)
        for i in range(1000):
            store.record(_snap(float(i), nav=float(i)))
        results = store.query(0.0, 999.0, max_points=100)
        store.close()
        assert len(results) == 100
        assert results[0].timestamp_utc < results[-1].timestamp_utc

    def test_lttb_preserves_first_and_last(self, tmp_db):
        store = NavStore(tmp_db)
        for i in range(100):
            store.record(_snap(float(i), nav=float(i)))
        results = store.query(0.0, 99.0, max_points=10)
        store.close()
        assert len(results) == 10
        assert results[0].timestamp_utc == 0.0
        assert results[-1].timestamp_utc == 99.0

    def test_lttb_returns_real_points(self, tmp_db):
        store = NavStore(tmp_db)
        originals = set()
        for i in range(200):
            nav = float(i) * 1.1
            originals.add((float(i), nav))
            store.record(_snap(float(i), nav=nav))
        results = store.query(0.0, 199.0, max_points=50)
        store.close()
        for r in results:
            assert (r.timestamp_utc, r.nav) in originals

    def test_lttb_preserves_spike(self, tmp_db):
        store = NavStore(tmp_db)
        for i in range(100):
            nav = 1000.0
            if i == 50:
                nav = 2000.0
            store.record(_snap(float(i), nav=nav))
        results = store.query(0.0, 99.0, max_points=20)
        store.close()
        navs = [r.nav for r in results]
        assert max(navs) == 2000.0

    def test_fewer_points_than_max_returns_all(self, tmp_db):
        store = NavStore(tmp_db)
        for i in range(5):
            store.record(_snap(float(i), nav=float(i)))
        results = store.query(0.0, 4.0, max_points=100)
        store.close()
        assert len(results) == 5


class TestPositionSnapshots:
    def _pos(self, ts, contract_id, quantity=10, mid=0.65):
        return PositionSnapshot(
            timestamp_utc=ts, contract_id=contract_id, platform="kalshi",
            canonical_event_id="EVT-1", quantity=quantity, entry_price=0.55,
            current_mid=mid, market_prob=mid, model_prob=mid, edge=0.0,
            resolves_at=9999999.0, tte_days=5.0, fee_adjusted_breakeven=0.56,
        )

    def test_record_and_query_positions(self, tmp_db):
        store = NavStore(tmp_db)
        positions = [self._pos(100.0, "A"), self._pos(100.0, "B", quantity=-5)]
        store.record(_snap(100.0), positions)
        result = store.query_positions(100.0)
        store.close()
        assert len(result) == 2
        assert result[0].contract_id == "A"
        assert result[1].contract_id == "B"
        assert result[1].quantity == -5

    def test_latest_positions(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(100.0), [self._pos(100.0, "A")])
        store.record(_snap(200.0), [self._pos(200.0, "A"), self._pos(200.0, "C")])
        result = store.latest_positions()
        store.close()
        assert len(result) == 2
        assert {p.contract_id for p in result} == {"A", "C"}

    def test_no_positions_returns_empty(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(100.0))
        assert store.latest_positions() == []
        assert store.query_positions(100.0) == []
        store.close()


class TestQueryOHLC:
    def test_single_bucket_ohlc(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(10.0, nav=100.0))
        store.record(_snap(20.0, nav=120.0))
        store.record(_snap(30.0, nav=90.0))
        store.record(_snap(40.0, nav=110.0))
        store.record(_snap(50.0, nav=105.0))
        result = store.query_ohlc(0.0, 100.0, bucket_seconds=100)
        store.close()
        assert len(result) == 1
        c = result[0]
        assert c.open == 100.0
        assert c.high == 120.0
        assert c.low == 90.0
        assert c.close == 105.0

    def test_multiple_buckets(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(10.0, nav=100.0))
        store.record(_snap(20.0, nav=110.0))
        store.record(_snap(70.0, nav=200.0))
        store.record(_snap(80.0, nav=180.0))
        result = store.query_ohlc(0.0, 100.0, bucket_seconds=60)
        store.close()
        assert len(result) == 2
        assert result[0].open == 100.0
        assert result[0].close == 110.0
        assert result[1].open == 200.0
        assert result[1].close == 180.0

    def test_empty_bucket_gaps(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(10.0, nav=100.0))
        store.record(_snap(130.0, nav=200.0))
        result = store.query_ohlc(0.0, 200.0, bucket_seconds=60)
        store.close()
        assert len(result) == 2
        assert result[0].timestamp_utc == 0.0
        assert result[1].timestamp_utc == 120.0

    def test_single_point_candle(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(50.0, nav=999.0))
        result = store.query_ohlc(0.0, 100.0, bucket_seconds=60)
        store.close()
        assert len(result) == 1
        c = result[0]
        assert c.open == c.high == c.low == c.close == 999.0

    def test_range_exclusion(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(10.0, nav=100.0))
        store.record(_snap(50.0, nav=200.0))
        store.record(_snap(110.0, nav=300.0))
        result = store.query_ohlc(20.0, 100.0, bucket_seconds=60)
        store.close()
        assert len(result) == 1
        assert result[0].open == 200.0

    def test_empty_range_returns_empty(self, tmp_db):
        store = NavStore(tmp_db)
        store.record(_snap(10.0, nav=100.0))
        result = store.query_ohlc(500.0, 600.0, bucket_seconds=60)
        store.close()
        assert result == []


class TestEmptyDB:
    def test_latest_returns_none(self, tmp_db):
        store = NavStore(tmp_db)
        assert store.latest() is None
        store.close()

    def test_query_returns_empty(self, tmp_db):
        store = NavStore(tmp_db)
        assert store.query(0.0, 1000.0) == []
        store.close()
