import numpy as np
import pytest
from datetime import datetime, timedelta, timezone, date
from src.correlation import (
    EventCalendar,
    DynamicCorrelationModel,
    compute_baseline_correlation,
    compute_pre_event_correlation,
)


def make_correlated_prices(n_days=120, n_contracts=4, rho=0.3, seed=42):
    """Generate prices with known correlation structure."""
    rng = np.random.default_rng(seed)
    cov = np.full((n_contracts, n_contracts), rho)
    np.fill_diagonal(cov, 1.0)
    L = np.linalg.cholesky(cov)
    z = rng.standard_normal((n_days, n_contracts))
    correlated = z @ L.T
    logits = np.cumsum(correlated * 0.05, axis=0)
    logits -= logits.mean(axis=0)
    prices = 1.0 / (1.0 + np.exp(-logits))
    return np.clip(prices, 0.06, 0.94)


def make_high_corr_event_prices(n_days=120, n_contracts=4, seed=42):
    """Generate prices where pre-event windows have elevated correlation."""
    rng = np.random.default_rng(seed)
    all_prices = []
    for day in range(n_days):
        is_pre_event = (day % 30) >= 23
        rho = 0.8 if is_pre_event else 0.2
        cov = np.full((n_contracts, n_contracts), rho)
        np.fill_diagonal(cov, 1.0)
        L = np.linalg.cholesky(cov)
        z = rng.standard_normal(n_contracts)
        all_prices.append(L @ z * 0.05)

    logits = np.cumsum(np.array(all_prices), axis=0)
    logits -= logits.mean(axis=0)
    prices = 1.0 / (1.0 + np.exp(-logits))
    return np.clip(prices, 0.06, 0.94)


class TestEventCalendar:
    def test_upcoming_within_window(self):
        cal = EventCalendar()
        now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        cal.add_event("FOMC", now + timedelta(hours=48), "FOMC March")
        upcoming = cal.upcoming_events(now, 72.0)
        assert len(upcoming) == 1
        assert upcoming[0]["type"] == "FOMC"

    def test_not_upcoming(self):
        cal = EventCalendar()
        now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        cal.add_event("FOMC", now + timedelta(days=10), "FOMC distant")
        upcoming = cal.upcoming_events(now, 72.0)
        assert len(upcoming) == 0

    def test_past_event_excluded(self):
        cal = EventCalendar()
        now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        cal.add_event("CPI", now - timedelta(hours=1), "CPI past")
        upcoming = cal.upcoming_events(now, 72.0)
        assert len(upcoming) == 0


class TestBaselineCorrelation:
    def test_produces_valid_covariance(self):
        prices = make_correlated_prices()
        cov = compute_baseline_correlation(prices, window=90)
        assert cov.shape == (4, 4)
        eigenvalues = np.linalg.eigvalsh(cov)
        assert np.all(eigenvalues >= -1e-10)

    def test_insufficient_data_raises(self):
        prices = make_correlated_prices(n_days=30)
        with pytest.raises(ValueError):
            compute_baseline_correlation(prices, window=90)


class TestPreEventCorrelation:
    def test_pre_event_higher_than_baseline(self):
        """Pre-event windows should show elevated avg pairwise correlation
        when the data generator injects higher correlation in those windows."""
        prices = make_high_corr_event_prices(n_days=200, n_contracts=4)
        base_date = date(2026, 1, 1)
        price_dates = [base_date + timedelta(days=i) for i in range(200)]

        event_dates = [base_date + timedelta(days=30*k) for k in range(1, 7)]

        baseline = compute_baseline_correlation(prices, window=90)
        pre_event = compute_pre_event_correlation(prices, event_dates, price_dates, pre_window=7)

        assert pre_event is not None

        def avg_off_diag_corr(cov):
            d = np.sqrt(np.diag(cov))
            corr = cov / np.outer(d, d)
            n = corr.shape[0]
            mask = ~np.eye(n, dtype=bool)
            return np.mean(corr[mask])

        baseline_corr = avg_off_diag_corr(baseline)
        pre_event_corr = avg_off_diag_corr(pre_event)
        assert pre_event_corr > baseline_corr


class TestDynamicCorrelationModel:
    def test_baseline_regime(self):
        prices = make_correlated_prices(n_days=120)
        cal = EventCalendar()
        model = DynamicCorrelationModel(calendar=cal)
        model.fit_baseline(prices)
        now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        regime = model.get_current_correlation(now)
        assert regime.regime == "baseline"
        assert regime.matrix is not None

    def test_pre_event_regime_switch(self):
        prices = make_correlated_prices(n_days=120)
        base_date = date(2026, 1, 1)
        price_dates = [base_date + timedelta(days=i) for i in range(120)]
        event_dates = [base_date + timedelta(days=30), base_date + timedelta(days=60)]

        cal = EventCalendar()
        fomc_time = datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc)
        cal.add_event("FOMC", fomc_time, "FOMC March")

        model = DynamicCorrelationModel(calendar=cal)
        model.fit_baseline(prices)
        model.fit_pre_event("FOMC", prices, event_dates, price_dates)

        now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        regime = model.get_current_correlation(now)
        assert regime.regime == "pre_event"
        assert "FOMC March" in regime.reason

    def test_falls_back_to_baseline_after_event(self):
        prices = make_correlated_prices(n_days=120)
        cal = EventCalendar()
        fomc_time = datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc)
        cal.add_event("FOMC", fomc_time, "FOMC March")

        model = DynamicCorrelationModel(calendar=cal)
        model.fit_baseline(prices)

        now = datetime(2026, 3, 5, tzinfo=timezone.utc)
        regime = model.get_current_correlation(now)
        assert regime.regime == "baseline"

    def test_regime_history_logged(self):
        prices = make_correlated_prices(n_days=120)
        model = DynamicCorrelationModel()
        model.fit_baseline(prices)
        model.get_current_correlation(datetime.now(timezone.utc))
        model.get_current_correlation(datetime.now(timezone.utc))
        assert len(model._history) == 2
