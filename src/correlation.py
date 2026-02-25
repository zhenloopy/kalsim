import numpy as np
import logging
from datetime import datetime, timedelta, timezone
from sklearn.covariance import LedoitWolf
from dataclasses import dataclass, field
from src.factor_model import prices_to_logit, filter_extreme_prices

logger = logging.getLogger(__name__)


@dataclass
class EventCalendar:
    """Scheduled events that trigger regime switching."""
    events: list[dict] = field(default_factory=list)

    def add_event(self, event_type: str, date: datetime, label: str = ""):
        self.events.append({
            "type": event_type,
            "date": date if date.tzinfo else date.replace(tzinfo=timezone.utc),
            "label": label or f"{event_type}_{date.strftime('%Y%m%d')}",
        })

    def upcoming_events(self, now: datetime, hours: float = 72.0):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff = now + timedelta(hours=hours)
        return [e for e in self.events if now <= e["date"] <= cutoff]


@dataclass
class CorrelationRegime:
    matrix: np.ndarray
    regime: str
    reason: str
    timestamp: datetime


def compute_baseline_correlation(daily_prices: np.ndarray, window: int = 90):
    """90-day rolling Ledoit-Wolf covariance on logit-returns."""
    if daily_prices.shape[0] < window:
        raise ValueError(f"Need at least {window} days, got {daily_prices.shape[0]}")

    windowed = daily_prices[-window:]
    filtered, mask = filter_extreme_prices(windowed)
    if filtered.shape[0] < 20:
        filtered = windowed

    logit = prices_to_logit(filtered)
    delta = np.diff(logit, axis=0)

    lw = LedoitWolf()
    lw.fit(delta)
    return lw.covariance_


def compute_pre_event_correlation(
    daily_prices: np.ndarray,
    event_dates: list[datetime],
    price_dates: list[datetime],
    pre_window: int = 7,
):
    """Estimate correlation from 7-day windows before historical instances of an event type."""
    if not event_dates or not price_dates:
        return None

    date_to_idx = {d.date() if hasattr(d, 'date') and callable(d.date) else d: i
                   for i, d in enumerate(price_dates)}

    collected_rows = []
    for ed in event_dates:
        ed_date = ed.date() if hasattr(ed, 'date') and callable(ed.date) else ed
        if ed_date not in date_to_idx:
            candidates = sorted(date_to_idx.keys(), key=lambda x: abs((x - ed_date).days))
            if candidates and abs((candidates[0] - ed_date).days) <= 3:
                ed_date = candidates[0]
            else:
                continue
        idx = date_to_idx[ed_date]
        start = max(0, idx - pre_window)
        if idx - start >= 3:
            collected_rows.append(daily_prices[start:idx])

    if not collected_rows:
        return None

    # Diff within each window first, then concatenate returns
    # (avoids garbage jumps at window boundaries)
    all_deltas = []
    for window in collected_rows:
        filtered, _ = filter_extreme_prices(window)
        if filtered.shape[0] < 3:
            filtered = window
        logit = prices_to_logit(filtered)
        delta = np.diff(logit, axis=0)
        if delta.shape[0] > 0:
            all_deltas.append(delta)

    if not all_deltas:
        return None
    combined_delta = np.vstack(all_deltas)
    if combined_delta.shape[0] < 3:
        return None

    lw = LedoitWolf()
    lw.fit(combined_delta)
    return lw.covariance_


class DynamicCorrelationModel:
    def __init__(self, calendar: EventCalendar = None, switch_hours: float = 72.0):
        self.calendar = calendar or EventCalendar()
        self.switch_hours = switch_hours
        self.baseline_cov = None
        self.pre_event_covs: dict[str, np.ndarray] = {}
        self._history: list[CorrelationRegime] = []

    def fit_baseline(self, daily_prices: np.ndarray, window: int = 90):
        self.baseline_cov = compute_baseline_correlation(daily_prices, window)

    def fit_pre_event(
        self, event_type: str, daily_prices: np.ndarray,
        event_dates: list[datetime], price_dates: list[datetime],
    ):
        cov = compute_pre_event_correlation(daily_prices, event_dates, price_dates)
        if cov is not None:
            self.pre_event_covs[event_type] = cov

    def get_current_correlation(self, now: datetime = None) -> CorrelationRegime:
        if now is None:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        upcoming = self.calendar.upcoming_events(now, self.switch_hours)

        for event in upcoming:
            etype = event["type"]
            if etype in self.pre_event_covs:
                reason = f"Pre-event regime: {event['label']} at {event['date'].isoformat()}"
                logger.info(reason)
                regime = CorrelationRegime(
                    matrix=self.pre_event_covs[etype],
                    regime="pre_event",
                    reason=reason,
                    timestamp=now,
                )
                self._history.append(regime)
                return regime

        if self.baseline_cov is None:
            raise ValueError("Baseline covariance not fitted")

        reason = "Baseline regime: no upcoming events within window"
        logger.info(reason)
        regime = CorrelationRegime(
            matrix=self.baseline_cov,
            regime="baseline",
            reason=reason,
            timestamp=now,
        )
        self._history.append(regime)
        return regime
