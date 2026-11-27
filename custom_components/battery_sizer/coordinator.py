"""Run the battery calculation and keep its result for the sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import NAME
from .data import LoadedData, async_load_hours
from .engine import (
    ExpansionRecommendation,
    Recommendation,
    Strategy,
    recommend,
    recommend_expansion,
)
from .settings import Settings, SettingsError

_LOGGER = logging.getLogger(__name__)

# The calculation reads years of history, so once a day is plenty.
UPDATE_INTERVAL = timedelta(days=1)
MIN_HOURS = 24 * 30


@dataclass(frozen=True, slots=True)
class Outcome:
    """The recommendation for one strategy, in plain numbers for sensors."""

    strategy: Strategy
    expansion: bool
    recommended_kwh: float
    annual_savings: float | None
    payback_years: float | None
    net_present_value: float | None
    investment: float | None
    cycles_per_year: float | None
    table: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CalculationResult:
    """One run of the calculation."""

    calculated_at: datetime
    hours: int
    first: datetime | None
    last: datetime | None
    months_covered: int
    existing_kwh: float
    existing_annual_savings: dict[Strategy, float]
    outcomes: dict[Strategy, Outcome]


def current_time() -> datetime:
    """Return now. Tests replace this clock."""
    return dt_util.utcnow()


class BatterySizerCoordinator(DataUpdateCoordinator[CalculationResult]):
    """Load the history, run every strategy, keep the result."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Calculate once a day and whenever asked to."""
        super().__init__(
            hass,
            _LOGGER,
            name=NAME,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.entry = entry

    @property
    def settings(self) -> Settings:
        """Return the entry's current settings."""
        return Settings.from_mapping({**self.entry.data, **self.entry.options})

    async def _async_update_data(self) -> CalculationResult:
        settings = self.settings
        try:
            settings.validate()
        except SettingsError as err:
            raise UpdateFailed(f"Invalid settings: {err.key}") from err
        loaded = await async_load_hours(self.hass, settings, current_time())
        if loaded.missing:
            raise UpdateFailed(
                "No history in Home Assistant for: " + ", ".join(loaded.missing)
            )
        if len(loaded.hours) < MIN_HOURS:
            raise UpdateFailed(
                f"Only {len(loaded.hours)} hours have both energy and prices; "
                f"at least {MIN_HOURS} (30 days) are needed"
            )
        zone = ZoneInfo(str(self.hass.config.time_zone or "Europe/Copenhagen"))
        return await self.hass.async_add_executor_job(
            _calculate, settings, loaded, zone
        )


def _calculate(
    settings: Settings, loaded: LoadedData, zone: ZoneInfo
) -> CalculationResult:
    """Run all strategies. This is CPU work and runs in the executor."""
    template = settings.battery()
    costs = settings.costs()
    sizes = settings.sizes()
    outcomes: dict[Strategy, Outcome] = {}
    existing: dict[Strategy, float] = {}
    months = 0
    for strategy in Strategy:
        if settings.is_expansion:
            expansion = recommend_expansion(
                loaded.hours,
                template,
                strategy,
                costs,
                existing_kwh=settings.existing_kwh,
                tz=zone,
                added=sizes,
            )
            existing[strategy] = expansion.existing.annual_savings
            months = expansion.existing.months_covered
            outcomes[strategy] = _expansion_outcome(strategy, expansion)
        else:
            rec = recommend(
                loaded.hours, template, strategy, costs, tz=zone, sizes=sizes
            )
            if rec.sizes:
                months = rec.sizes[0].simulation.months_covered
            outcomes[strategy] = _new_outcome(strategy, rec)
    return CalculationResult(
        calculated_at=current_time(),
        hours=len(loaded.hours),
        first=loaded.first,
        last=loaded.last,
        months_covered=months,
        existing_kwh=settings.existing_kwh,
        existing_annual_savings=existing,
        outcomes=outcomes,
    )


def _row(kwh: float, savings: float, economics: Any) -> dict[str, Any]:
    return {
        "kwh": kwh,
        "annual_savings": round(savings),
        "investment": round(economics.investment),
        "payback_years": round(economics.payback_years, 1)
        if economics.payback_years is not None
        else None,
        "net_present_value": round(economics.net_present_value),
        "cycles_per_year": round(economics.annual_cycles),
    }


def _new_outcome(strategy: Strategy, rec: Recommendation) -> Outcome:
    table = [
        _row(size.capacity_kwh, size.economics.annual_savings, size.economics)
        for size in rec.sizes
        if size.capacity_kwh > 0
    ]
    best = rec.best
    if best is None:
        return Outcome(strategy, False, 0.0, None, None, None, None, None, table)
    economics = best.economics
    return Outcome(
        strategy=strategy,
        expansion=False,
        recommended_kwh=best.capacity_kwh,
        annual_savings=round(economics.annual_savings),
        payback_years=economics.payback_years,
        net_present_value=round(economics.net_present_value),
        investment=round(economics.investment),
        cycles_per_year=round(economics.annual_cycles),
        table=table,
    )


def _expansion_outcome(strategy: Strategy, rec: ExpansionRecommendation) -> Outcome:
    table = [
        _row(option.added_kwh, option.extra_annual_savings, option.economics)
        for option in rec.options
    ]
    best = rec.best
    if best is None:
        return Outcome(strategy, True, 0.0, None, None, None, None, None, table)
    economics = best.economics
    return Outcome(
        strategy=strategy,
        expansion=True,
        recommended_kwh=best.added_kwh,
        annual_savings=round(best.extra_annual_savings),
        payback_years=economics.payback_years,
        net_present_value=round(economics.net_present_value),
        investment=round(economics.investment),
        cycles_per_year=round(economics.annual_cycles),
        table=table,
    )
