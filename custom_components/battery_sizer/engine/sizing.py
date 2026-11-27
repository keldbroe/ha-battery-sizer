"""Run a range of battery sizes and pick the one that pays best."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from zoneinfo import ZoneInfo

from .economics import Costs, Economics, evaluate
from .models import Battery, Hour, SimulationResult, Strategy
from .simulate import simulate


@dataclass(frozen=True, slots=True)
class SizeResult:
    """One battery size: its simulation and its economics."""

    simulation: SimulationResult
    economics: Economics

    @property
    def capacity_kwh(self) -> float:
        """Return the nominal capacity of this size."""
        return self.simulation.battery.capacity_kwh


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Every size that was tried, and the best one if any pays off."""

    strategy: Strategy
    sizes: list[SizeResult]
    best: SizeResult | None

    @property
    def best_capacity_kwh(self) -> float:
        """Return the recommended capacity, or 0 when no size pays off."""
        return self.best.capacity_kwh if self.best is not None else 0.0


def default_sizes(maximum_kwh: float = 30.0, step_kwh: float = 2.5) -> list[float]:
    """Return 0, step, 2*step, ... up to ``maximum_kwh``."""
    count = round(maximum_kwh / step_kwh)
    return [round(step_kwh * index, 3) for index in range(count + 1)]


def recommend(
    hours: Sequence[Hour],
    template: Battery,
    strategy: Strategy,
    costs: Costs,
    *,
    tz: ZoneInfo,
    sizes: Iterable[float] | None = None,
    include_wear: bool = True,
    progress: Callable[[int, int], None] | None = None,
) -> Recommendation:
    """Simulate every size and return the one with the highest net value.

    ``template`` gives power, efficiency and grid limit; only the capacity
    changes. With ``include_wear`` the battery's wear per kWh (from price
    and cycle life) is charged in the simulation, so it is not cycled for
    less than it wears.
    """
    capacities = sorted(set(sizes if sizes is not None else default_sizes()))
    wear = (
        costs.wear_cost_per_kwh(template.round_trip_efficiency)
        if include_wear
        else template.wear_cost_per_kwh
    )
    results: list[SizeResult] = []
    for done, capacity in enumerate(capacities, start=1):
        battery = replace(template, capacity_kwh=capacity, wear_cost_per_kwh=wear)
        simulation = simulate(hours, battery, strategy, tz=tz)
        economics = evaluate(
            capacity, simulation.annual_savings, simulation.annual_cycles, costs
        )
        results.append(SizeResult(simulation=simulation, economics=economics))
        if progress is not None:
            progress(done, len(capacities))
    paying = [
        result
        for result in results
        if result.capacity_kwh > 0 and result.economics.pays_off
    ]
    best = max(paying, key=lambda r: r.economics.net_present_value, default=None)
    return Recommendation(strategy=strategy, sizes=results, best=best)


@dataclass(frozen=True, slots=True)
class ExpansionOption:
    """Adding ``added_kwh`` to the existing battery."""

    added_kwh: float
    simulation: SimulationResult
    extra_annual_savings: float
    economics: Economics

    @property
    def total_kwh(self) -> float:
        """Return the battery's capacity after the expansion."""
        return self.simulation.battery.capacity_kwh


@dataclass(frozen=True, slots=True)
class ExpansionRecommendation:
    """The existing battery, every expansion tried, and the best one if any."""

    strategy: Strategy
    existing: SimulationResult
    options: list[ExpansionOption]
    best: ExpansionOption | None

    @property
    def best_added_kwh(self) -> float:
        """Return the recommended extra capacity, or 0 when none pays off."""
        return self.best.added_kwh if self.best is not None else 0.0


def recommend_expansion(
    hours: Sequence[Hour],
    template: Battery,
    strategy: Strategy,
    costs: Costs,
    *,
    existing_kwh: float,
    tz: ZoneInfo,
    added: Iterable[float] | None = None,
    include_wear: bool = True,
    progress: Callable[[int, int], None] | None = None,
) -> ExpansionRecommendation:
    """Find how much capacity to add to an existing battery, if any.

    The existing battery is already paid for, so only the extra savings
    count, against the price of the extra modules plus the one-off
    ``costs.expansion_cost``. ``hours`` should describe the home without
    any battery (load and solar from the inverter), so the existing battery
    is simulated too and not counted twice. The expansion lasts as long as
    the larger battery: its years or cycles, whichever ends first.
    """
    if existing_kwh <= 0:
        raise ValueError("existing_kwh must be positive; use recommend() instead")
    extra = sorted(
        {a for a in (added if added is not None else default_sizes()) if a > 0}
    )
    wear = (
        costs.wear_cost_per_kwh(template.round_trip_efficiency)
        if include_wear
        else template.wear_cost_per_kwh
    )
    total_runs = len(extra) + 1

    def run(capacity: float) -> SimulationResult:
        battery = replace(template, capacity_kwh=capacity, wear_cost_per_kwh=wear)
        return simulate(hours, battery, strategy, tz=tz)

    existing = run(existing_kwh)
    if progress is not None:
        progress(1, total_runs)
    options: list[ExpansionOption] = []
    for done, add in enumerate(extra, start=2):
        simulation = run(existing_kwh + add)
        gain = simulation.annual_savings - existing.annual_savings
        economics = evaluate(
            add,
            gain,
            simulation.annual_cycles,
            costs,
            investment=costs.expansion_investment(add),
        )
        options.append(
            ExpansionOption(
                added_kwh=add,
                simulation=simulation,
                extra_annual_savings=gain,
                economics=economics,
            )
        )
        if progress is not None:
            progress(done, total_runs)
    paying = [option for option in options if option.economics.pays_off]
    best = max(paying, key=lambda o: o.economics.net_present_value, default=None)
    return ExpansionRecommendation(
        strategy=strategy, existing=existing, options=options, best=best
    )
