"""Turn Home Assistant long-term statistics into hourly engine input.

Energy sensors are stored as a cumulative ``sum`` per hour; the energy used
in one hour is that hour's sum minus the previous hour's. Price sensors are
read from the hourly ``state`` (or ``mean``) value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta

from .models import Hour

ONE_HOUR = timedelta(hours=1)


def hour_start(moment: datetime) -> datetime:
    """Return the UTC hour that contains ``moment``."""
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
    return aware.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def energy_from_sums(
    rows: Iterable[tuple[datetime, float | None]],
) -> dict[datetime, float]:
    """Return kWh per hour from consecutive hourly ``sum`` rows.

    A row's sum is the total at the end of its hour, so the hour's energy is
    the difference to the row one hour earlier. After a gap the difference
    spans several hours and cannot be placed, so that hour is left out. A
    sum that goes down (a meter replaced or a correction) is also left out.
    """
    result: dict[datetime, float] = {}
    previous_start: datetime | None = None
    previous_sum: float | None = None
    for start, total in sorted(
        ((hour_start(start), total) for start, total in rows), key=lambda r: r[0]
    ):
        if total is None:
            previous_start, previous_sum = None, None
            continue
        if (
            previous_start is not None
            and previous_sum is not None
            and start - previous_start == ONE_HOUR
        ):
            delta = float(total) - previous_sum
            if delta >= 0:
                result[start] = delta
        previous_start, previous_sum = start, float(total)
    return result


def values_by_hour(
    rows: Iterable[tuple[datetime, float | None]],
) -> dict[datetime, float]:
    """Return one value per hour, skipping hours without a value."""
    return {
        hour_start(start): float(value) for start, value in rows if value is not None
    }


def split_gross(
    load: Mapping[datetime, float], solar: Mapping[datetime, float]
) -> tuple[dict[datetime, float], dict[datetime, float]]:
    """Return (import, export) per hour from the home's load and solar output.

    This is what the grid would have seen without any battery, which is the
    right starting point for a home that already has one: its grid meter
    shows the effect of the existing battery.
    """
    imports: dict[datetime, float] = {}
    exports: dict[datetime, float] = {}
    for start in load.keys() & solar.keys():
        net = load[start] - solar[start]
        imports[start] = max(net, 0.0)
        exports[start] = max(-net, 0.0)
    return imports, exports


def build_hours(
    imports: Mapping[datetime, float],
    exports: Mapping[datetime, float],
    buy_prices: Mapping[datetime, float],
    sell_prices: Mapping[datetime, float],
    *,
    sell_adjustment: float = 0.0,
) -> list[Hour]:
    """Join the series on the hours where import and both prices are known.

    An hour without an export value counts as no export (no surplus that
    hour). ``sell_adjustment`` is added to the sell price, for example a
    negative supplier fee and feed-in tariff when the sell sensor is the
    bare spot price.
    """
    hours = sorted(imports.keys() & buy_prices.keys() & sell_prices.keys())
    return [
        Hour(
            start=start,
            import_kwh=max(imports[start], 0.0),
            export_kwh=max(exports.get(start, 0.0), 0.0),
            buy_price=buy_prices[start],
            sell_price=sell_prices[start] + sell_adjustment,
        )
        for start in hours
    ]
