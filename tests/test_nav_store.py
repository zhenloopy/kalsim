import os
import tempfile
import pytest
from src.nav_store import NavStore, NavSnapshot


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

    def test_downsampled_averages_are_correct(self, tmp_db):
        store = NavStore(tmp_db)
        for i in range(100):
            store.record(_snap(float(i), nav=float(i)))
        results = store.query(0.0, 99.0, max_points=10)
        store.close()
        assert len(results) == 10
        assert abs(results[0].nav - 4.5) < 1e-6

    def test_fewer_points_than_max_returns_all(self, tmp_db):
        store = NavStore(tmp_db)
        for i in range(5):
            store.record(_snap(float(i), nav=float(i)))
        results = store.query(0.0, 4.0, max_points=100)
        store.close()
        assert len(results) == 5


class TestEmptyDB:
    def test_latest_returns_none(self, tmp_db):
        store = NavStore(tmp_db)
        assert store.latest() is None
        store.close()

    def test_query_returns_empty(self, tmp_db):
        store = NavStore(tmp_db)
        assert store.query(0.0, 1000.0) == []
        store.close()
