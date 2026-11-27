"""Data types for the battery sizing engine.

The engine has no Home Assistant imports. It works on hourly values that the
integration (or the add-on) reads from long-term statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

_LONG = {1, 3, 5, 7, 8, 10, 12}


class Strategy(StrEnum):
    """How the battery may be used.

    ``SELF_CONSUMPTION``: charged only from solar surplus, discharged only to
    cover the home's own purchases, in the most expensive hours first.
    ``SOLAR_TRADING``: charged only from solar surplus, discharged to the home
    or sold to the grid, whichever pays more.
    ``GRID_TRADING``: may also charge from the grid in cheap hours and sell
    in expensive ones. Grid power is bought at the full price, with tariffs,
    taxes and VAT, but sold at the sell price, so this only pays off when
    the spread is large.
    """

    SELF_CONSUMPTION = "self_consumption"
    SOLAR_TRADING = "solar_trading"
    GRID_TRADING = "grid_trading"


@dataclass(frozen=True, slots=True)
class Hour:
    """One hour without a battery.

    ``import_kwh`` is what the home bought from the grid and
    ``export_kwh`` what it delivered to the grid, after its own solar use.
    ``buy_price`` is the full price per kWh bought (spot, supplier, grid
    tariffs, taxes and VAT); ``sell_price`` is what one kWh sold earns.
    """

    start: datetime
    import_kwh: float
    export_kwh: float
    buy_price: float
    sell_price: float


@dataclass(frozen=True, slots=True)
class Battery:
    """A battery and the inverter in front of it.

    ``power_kw`` limits both charging and discharging, measured on the AC
    side. ``usable_fraction`` is the share of the nominal capacity the
    battery management lets you use. ``round_trip_efficiency`` is applied on
    the way out: storing 1 kWh delivers ``round_trip_efficiency`` kWh.
    ``wear_cost_per_kwh`` is charged per kWh delivered, so the battery is
    not cycled for a gain smaller than its wear. ``grid_limit_kw`` is the
    main fuse (3x25 A is about 17 kW); ``None`` means no limit.
    """

    capacity_kwh: float
    power_kw: float = 5.0
    usable_fraction: float = 0.9
    round_trip_efficiency: float = 0.9
    wear_cost_per_kwh: float = 0.0
    grid_limit_kw: float | None = None

    def __post_init__(self) -> None:
        """Reject values that would make the simulation meaningless."""
        if self.capacity_kwh < 0:
            raise ValueError("capacity_kwh must not be negative")
        if self.power_kw <= 0:
            raise ValueError("power_kw must be positive")
        if not 0 < self.usable_fraction <= 1:
            raise ValueError("usable_fraction must be in (0, 1]")
        if not 0 < self.round_trip_efficiency <= 1:
            raise ValueError("round_trip_efficiency must be in (0, 1]")
        if self.wear_cost_per_kwh < 0:
            raise ValueError("wear_cost_per_kwh must not be negative")
        if self.grid_limit_kw is not None and self.grid_limit_kw <= 0:
            raise ValueError("grid_limit_kw must be positive")

    @property
    def usable_kwh(self) -> float:
        """Return the energy that can actually be stored."""
        return self.capacity_kwh * self.usable_fraction


@dataclass(slots=True)
class Totals:
    """Energy and money over a period, with and without the battery."""

    hours: int = 0
    baseline_cost: float = 0.0
    cost: float = 0.0
    delivered_to_home_kwh: float = 0.0
    sold_from_battery_kwh: float = 0.0
    charged_from_solar_kwh: float = 0.0
    charged_from_grid_kwh: float = 0.0
    full_cycles: float = 0.0
    # Wear is reported, not deducted: the investment already pays for it.
    wear_cost: float = 0.0

    @property
    def savings(self) -> float:
        """Return how much cheaper the period was with the battery."""
        return self.baseline_cost - self.cost

    def add(self, other: Totals) -> None:
        """Add another period's totals to this one."""
        self.hours += other.hours
        self.baseline_cost += other.baseline_cost
        self.cost += other.cost
        self.delivered_to_home_kwh += other.delivered_to_home_kwh
        self.sold_from_battery_kwh += other.sold_from_battery_kwh
        self.charged_from_solar_kwh += other.charged_from_solar_kwh
        self.charged_from_grid_kwh += other.charged_from_grid_kwh
        self.full_cycles += other.full_cycles
        self.wear_cost += other.wear_cost


@dataclass(frozen=True, slots=True)
class HourResult:
    """What the battery did in one hour (kWh on the AC side)."""

    start: datetime
    charged_from_solar: float
    charged_from_grid: float
    delivered_to_home: float
    sold_from_battery: float
    stored_kwh: float


@dataclass(slots=True)
class SimulationResult:
    """The outcome of running one battery and one strategy over the data."""

    battery: Battery
    strategy: Strategy
    total: Totals
    by_year: dict[int, Totals] = field(default_factory=dict)
    by_month: dict[tuple[int, int], Totals] = field(default_factory=dict)
    hourly: list[HourResult] | None = None

    @property
    def annual_savings(self) -> float:
        """Return the savings for a typical year.

        When every calendar month is in the data, each month's average is
        taken and the twelve are added, so a period that covers some months
        more often than others (September 2024 to November 2026, say) does
        not over-weight them. Otherwise the total is scaled to 8,760 hours.
        """
        return self._typical_year(lambda totals: totals.savings)

    @property
    def annual_cycles(self) -> float:
        """Return the full cycles for a typical year, weighted like savings."""
        return self._typical_year(lambda totals: totals.full_cycles)

    @property
    def months_covered(self) -> int:
        """Return how many of the twelve calendar months have data."""
        return len({month for _, month in self.by_month})

    def _typical_year(self, pick) -> float:
        if self.total.hours == 0:
            return 0.0
        if self.months_covered < 12:
            return pick(self.total) * 8760 / self.total.hours
        year = 0.0
        for month in range(1, 13):
            periods = [t for (_, m), t in self.by_month.items() if m == month]
            hours = sum(t.hours for t in periods)
            value = sum(pick(t) for t in periods)
            # February counts 28.25 days, so the year is 365.25 days long.
            days = 28.25 if month == 2 else 31.0 if month in _LONG else 30.0
            year += value * (days * 24) / hours
        return year
