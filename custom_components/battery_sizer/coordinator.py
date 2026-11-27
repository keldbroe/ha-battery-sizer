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
    SimulationResult,
    Strategy,
    recommend,
    recommend_expansion,
)
from .settings import Settings, SettingsError
from .units import UnsupportedPriceUnit

_LOGGER = logging.getLogger(__name__)

# The calculation reads years of history, so once a day is plenty.
UPDATE_INTERVAL = timedelta(days=1)

VERDICT_PAYS_OFF = "pays_off"
VERDICT_DOES_NOT_PAY_OFF = "does_not_pay_off"
VERDICT_NO_GAIN = "no_gain"
VERDICTS = [VERDICT_PAYS_OFF, VERDICT_DOES_NOT_PAY_OFF, VERDICT_NO_GAIN]
MIN_HOURS = 24 * 30


@dataclass(frozen=True, slots=True)
class Outcome:
    """The recommendation for one strategy, in plain numbers for sensors.

    ``recommended_kwh`` is 0 when nothing pays off: the advice is then not
    to buy. The other numbers still describe the best option tried
    (``candidate_kwh``), so the user sees how far from paying off it is,
    and ``verdict`` says which case applies.
    """

    strategy: Strategy
    expansion: bool
    recommended_kwh: float
    verdict: str
    candidate_kwh: float | None
    annual_savings: float | None
    payback_years: float | None
    payback_within_lifetime: bool
    net_present_value: float | None
    investment: float | None
    cycles_per_year: float | None
    table: list[dict[str, Any]] = field(default_factory=list)
    # A typical year, month by month, for the option shown (for the panel).
    monthly: list[dict[str, Any]] = field(default_factory=list)


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
    existing_monthly: dict[Strategy, list[dict[str, Any]]] = field(default_factory=dict)


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
        try:
            loaded = await async_load_hours(self.hass, settings, current_time())
        except UnsupportedPriceUnit as err:
            raise UpdateFailed(
                f"The price {err.statistic} is in {err.unit or 'no unit'}; "
                "only kr, DKK or øre per Wh, kWh or MWh can be used"
            ) from err
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
    existing_monthly: dict[Strategy, list[dict[str, Any]]] = {}
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
            existing_monthly[strategy] = monthly(expansion.existing)
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
        existing_monthly=existing_monthly,
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


def monthly(
    simulation: SimulationResult, baseline: SimulationResult | None = None
) -> list[dict[str, Any]]:
    """Savings and energy per calendar month of a typical year.

    With ``baseline`` (the battery you have), savings are the extra savings
    of the expansion; the energy is what the whole battery moves.
    """

    def months(sim: SimulationResult | None, pick) -> list[float | None]:
        return sim.typical_months(pick) if sim is not None else [0.0] * 12

    savings = months(simulation, lambda t: t.savings)
    before = months(baseline, lambda t: t.savings)
    flows = {
        "delivered_kwh": months(simulation, lambda t: t.delivered_to_home_kwh),
        "sold_kwh": months(simulation, lambda t: t.sold_from_battery_kwh),
        "charged_solar_kwh": months(simulation, lambda t: t.charged_from_solar_kwh),
        "charged_grid_kwh": months(simulation, lambda t: t.charged_from_grid_kwh),
        "cycles": months(simulation, lambda t: t.full_cycles),
    }
    rows: list[dict[str, Any]] = []
    for index in range(12):
        value = savings[index]
        row: dict[str, Any] = {
            "month": index + 1,
            "savings": None
            if value is None
            else round(value - (before[index] or 0.0), 1),
        }
        for key, values in flows.items():
            row[key] = None if values[index] is None else round(values[index], 1)
        rows.append(row)
    return rows


def _new_outcome(strategy: Strategy, rec: Recommendation) -> Outcome:
    candidates = [
        (
            size.capacity_kwh,
            size.economics.annual_savings,
            size.economics,
            size.simulation,
        )
        for size in rec.sizes
        if size.capacity_kwh > 0
    ]
    best = rec.best.capacity_kwh if rec.best is not None else None
    return _outcome(strategy, False, candidates, best, None)


def _expansion_outcome(strategy: Strategy, rec: ExpansionRecommendation) -> Outcome:
    candidates = [
        (
            option.added_kwh,
            option.extra_annual_savings,
            option.economics,
            option.simulation,
        )
        for option in rec.options
    ]
    best = rec.best.added_kwh if rec.best is not None else None
    return _outcome(strategy, True, candidates, best, rec.existing)


def _outcome(
    strategy: Strategy,
    expansion: bool,
    candidates: list[tuple[float, float, Any, SimulationResult]],
    best_kwh: float | None,
    baseline: SimulationResult | None,
) -> Outcome:
    """Describe the recommendation, or the closest option when none pays off."""
    table = [_row(kwh, savings, economics) for kwh, savings, economics, _ in candidates]
    if not candidates:
        return Outcome(
            strategy,
            expansion,
            0.0,
            VERDICT_NO_GAIN,
            None,
            None,
            None,
            False,
            None,
            None,
            None,
            table,
        )
    if best_kwh is not None:
        kwh, savings, economics, simulation = next(
            c for c in candidates if c[0] == best_kwh
        )
        verdict = VERDICT_PAYS_OFF
    else:
        kwh, savings, economics, simulation = max(
            candidates, key=lambda c: c[2].net_present_value
        )
        verdict = VERDICT_DOES_NOT_PAY_OFF if savings > 0.5 else VERDICT_NO_GAIN
    payback = economics.investment / savings if savings > 0.5 else None
    return Outcome(
        strategy=strategy,
        expansion=expansion,
        recommended_kwh=best_kwh or 0.0,
        verdict=verdict,
        candidate_kwh=kwh,
        annual_savings=round(savings),
        payback_years=round(payback, 1) if payback is not None else None,
        payback_within_lifetime=economics.payback_years is not None,
        net_present_value=round(economics.net_present_value),
        investment=round(economics.investment),
        cycles_per_year=round(economics.annual_cycles),
        table=table,
        monthly=monthly(simulation, baseline),
    )
