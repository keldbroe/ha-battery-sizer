"""Read the hourly history the calculation needs from the recorder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    get_metadata,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant

from .engine import Hour
from .engine.series import build_hours, energy_from_sums, split_gross, values_by_hour
from .settings import Settings
from .units import UnsupportedPriceUnit, price_factor


@dataclass(frozen=True, slots=True)
class LoadedData:
    """Hours ready for the engine, and what was found for each statistic."""

    hours: list[Hour]
    rows_by_statistic: dict[str, int]

    @property
    def missing(self) -> list[str]:
        """Return the statistics that had no rows at all."""
        return [stat for stat, count in self.rows_by_statistic.items() if count == 0]

    @property
    def first(self) -> datetime | None:
        """Return the first hour used."""
        return self.hours[0].start if self.hours else None

    @property
    def last(self) -> datetime | None:
        """Return the last hour used."""
        return self.hours[-1].start if self.hours else None


async def async_load_hours(
    hass: HomeAssistant, settings: Settings, now: datetime
) -> LoadedData:
    """Load energy and prices for the configured period and join them."""
    start = now - timedelta(days=365.25 * settings.history_years)
    statistic_ids = {
        *settings.energy_statistics,
        settings.buy_price_statistic,
        settings.sell_price_statistic,
    }
    prices = {settings.buy_price_statistic, settings.sell_price_statistic}
    result, units = await get_instance(hass).async_add_executor_job(
        _read, hass, start, statistic_ids, prices
    )
    factors: dict[str, float] = {}
    for statistic in prices:
        if statistic not in units:
            continue  # no history; reported as missing
        factor = price_factor(units[statistic])
        if factor is None:
            raise UnsupportedPriceUnit(statistic, units[statistic])
        factors[statistic] = factor
    return join(settings, result, factors)


def _read(
    hass: HomeAssistant, start: datetime, statistic_ids: set[str], prices: set[str]
) -> tuple[Mapping[str, Sequence[Mapping[str, Any]]], dict[str, str | None]]:
    """Read the rows, energy in kWh whatever the sensor's unit, and price units."""
    result = statistics_during_period(
        hass,
        start,
        None,
        statistic_ids,
        "hour",
        {"energy": "kWh"},
        {"sum", "state", "mean"},
    )
    metadata = get_metadata(hass, statistic_ids=prices)
    units = {
        statistic: meta.get("unit_of_measurement")
        for statistic, (_, meta) in metadata.items()
    }
    return result, units


def join(
    settings: Settings,
    result: Mapping[str, Sequence[Mapping[str, Any]]],
    price_factors: Mapping[str, float] | None = None,
) -> LoadedData:
    """Turn recorder rows into engine hours (kept separate for testing).

    ``price_factors`` turns each price statistic into kr/kWh.
    """

    def rows(statistic: str | None) -> Sequence[Mapping[str, Any]]:
        return (result or {}).get(statistic or "", []) or []

    def energy(statistic: str | None) -> dict[datetime, float]:
        return energy_from_sums(
            (_start(row), row.get("sum")) for row in rows(statistic)
        )

    def prices(statistic: str) -> dict[datetime, float]:
        factor = (price_factors or {}).get(statistic, 1.0)
        return values_by_hour(
            (_start(row), _scaled(_price(row), factor)) for row in rows(statistic)
        )

    if settings.source == "inverter":
        imports, exports = split_gross(
            energy(settings.load_statistic), energy(settings.solar_statistic)
        )
    else:
        imports = energy(settings.import_statistic)
        exports = energy(settings.export_statistic) if settings.export_statistic else {}
    hours = build_hours(
        imports,
        exports,
        prices(settings.buy_price_statistic),
        prices(settings.sell_price_statistic),
        sell_adjustment=-settings.sell_deduction,
    )
    counts = {
        statistic: len(rows(statistic))
        for statistic in (
            *settings.energy_statistics,
            settings.buy_price_statistic,
            settings.sell_price_statistic,
        )
    }
    return LoadedData(hours=hours, rows_by_statistic=counts)


def _start(row: Mapping[str, Any]) -> datetime:
    value = row["start"]
    if isinstance(value, datetime):
        return value
    seconds = float(value)
    if seconds > 10_000_000_000:
        seconds /= 1000
    return datetime.fromtimestamp(seconds, tz=UTC)


def _scaled(value: float | None, factor: float) -> float | None:
    return None if value is None else value * factor


def _price(row: Mapping[str, Any]) -> float | None:
    """A price sensor is kept either as a state (with a sum) or as a mean."""
    for key in ("state", "mean"):
        value = row.get(key)
        if value is not None:
            return float(value)
    return None
