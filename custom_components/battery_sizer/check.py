"""A look at the chosen statistics before the battery questions.

The setup loads the history once and shows what it found: how many hours,
the average prices and the energy per day. Values that look wrong (a buy
price without taxes, prices swapped, no solar) give a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .data import LoadedData
from .settings import Settings

# Danish all-in prices (spot, tariffs, taxes, VAT) are about 1.5 to 5 kr/kWh.
LOW_BUY_PRICE = 1.0
HIGH_BUY_PRICE = 8.0
SHORT_HISTORY_DAYS = 330
LOW_COVERAGE = 0.8

WARNINGS = (
    "low_buy_price",
    "high_buy_price",
    "sell_above_buy",
    "no_import",
    "no_export",
    "short_history",
    "gaps",
)


@dataclass(frozen=True, slots=True)
class Summary:
    """What the chosen statistics give, for the setup to show."""

    hours: int
    first: datetime | None
    last: datetime | None
    days: float
    buy_price: float
    sell_price: float
    import_per_day: float
    export_per_day: float
    coverage: float
    warnings: list[str] = field(default_factory=list)


def summarize(settings: Settings, loaded: LoadedData) -> Summary:
    """Average the loaded hours and flag what looks wrong."""
    hours = loaded.hours
    count = len(hours)
    if not count:
        return Summary(0, None, None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [])
    first, last = hours[0].start, hours[-1].start
    span_hours = (last - first).total_seconds() / 3600 + 1
    days = span_hours / 24
    buy = sum(h.buy_price for h in hours) / count
    sell = sum(h.sell_price for h in hours) / count
    imported = sum(h.import_kwh for h in hours)
    exported = sum(h.export_kwh for h in hours)
    covered_days = count / 24
    coverage = count / span_hours if span_hours else 0.0

    warnings: list[str] = []
    if buy < LOW_BUY_PRICE:
        warnings.append("low_buy_price")
    if buy > HIGH_BUY_PRICE:
        warnings.append("high_buy_price")
    if sell >= buy:
        warnings.append("sell_above_buy")
    if imported <= 0:
        warnings.append("no_import")
    expects_export = settings.source == "inverter" or bool(settings.export_statistic)
    if expects_export and exported <= 0:
        warnings.append("no_export")
    if days < SHORT_HISTORY_DAYS:
        warnings.append("short_history")
    if coverage < LOW_COVERAGE:
        warnings.append("gaps")
    return Summary(
        hours=count,
        first=first,
        last=last,
        days=days,
        buy_price=buy,
        sell_price=sell,
        import_per_day=imported / covered_days,
        export_per_day=exported / covered_days,
        coverage=coverage,
        warnings=warnings,
    )
