"""Danish electricity prices: rebuild the buy price from spot and tariffs.

The recorded buy price is what was actually paid, including the electricity
tax of that time (about 0.72 kr/kWh until 2025, 0.008 kr/kWh in 2026 and
2027). To ask "what would a battery save with today's tariffs and taxes", the
buy price can be rebuilt from the recorded spot price and today's tariffs:

    buy = (spot + supplier markup + grid tariff(hour) + other tariffs) * (1 + VAT)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import Hour

DANISH_VAT = 0.25


def buy_price(
    spot: float,
    *,
    grid_tariff: float,
    other_tariffs: float,
    supplier_markup: float = 0.0,
    vat: float = DANISH_VAT,
) -> float:
    """Return the price per kWh bought, everything included."""
    return (spot + supplier_markup + grid_tariff + other_tariffs) * (1 + vat)


def with_current_tariffs(
    hours: Sequence[Hour],
    spot: Mapping[datetime, float],
    *,
    grid_tariff_by_hour: Mapping[int, float],
    other_tariffs: float,
    tz: ZoneInfo,
    supplier_markup: float = 0.0,
    vat: float = DANISH_VAT,
) -> list[Hour]:
    """Replace each hour's buy price with today's tariffs on that hour's spot.

    ``grid_tariff_by_hour`` maps local hour 0-23 to the grid company's tariff
    (excluding VAT), and ``other_tariffs`` is the sum of Energinet's tariffs
    and the electricity tax (excluding VAT). Hours without a spot price keep
    their recorded buy price.
    """
    rebuilt: list[Hour] = []
    for hour in hours:
        price = spot.get(hour.start)
        if price is None:
            rebuilt.append(hour)
            continue
        local_hour = hour.start.astimezone(tz).hour
        rebuilt.append(
            replace(
                hour,
                buy_price=buy_price(
                    price,
                    grid_tariff=grid_tariff_by_hour.get(local_hour, 0.0),
                    other_tariffs=other_tariffs,
                    supplier_markup=supplier_markup,
                    vat=vat,
                ),
            )
        )
    return rebuilt
