"""Hour-by-hour battery simulation with day-ahead planning.

Danish day-ahead prices for tomorrow are published around 13:00. The
simulation therefore plans once a day at 13:00 (local time), looking ahead to
the end of the next day, and carries out the first 24 hours of that plan
before planning again. The battery's charge at that moment carries over to
the next plan.

A plan moves energy from a *source* to a later *sink*:

- sources: solar surplus (worth its sell price, since it could have been
  sold), the grid (at the full buy price), and what is already in the battery
  (already paid for);
- sinks: the home's own purchases (worth the buy price) and sale to the grid
  (worth the sell price).

Every (source, sink) pair with a positive gain is ranked, and energy is moved
along the best pairs first, as far as power, capacity and the hour's energy
allow. That is why the most expensive hours are covered first, and why cheap
hours are simply left to the grid when there is not enough stored energy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Battery, Hour, HourResult, SimulationResult, Strategy, Totals

PLAN_HOUR = 13
_EPS = 1e-9

_INIT = 0
_SOLAR = 1
_GRID = 2
_HOME = 0
_SELL = 1


@dataclass(slots=True)
class _Actions:
    """What the battery did in one hour, all in kWh on the AC side."""

    charge_solar: float = 0.0
    charge_grid: float = 0.0
    to_home: float = 0.0
    to_grid: float = 0.0

    @property
    def charging(self) -> float:
        return self.charge_solar + self.charge_grid

    @property
    def discharging(self) -> float:
        return self.to_home + self.to_grid


def simulate(
    hours: Sequence[Hour],
    battery: Battery,
    strategy: Strategy,
    *,
    tz: ZoneInfo,
    keep_hourly: bool = False,
) -> SimulationResult:
    """Run one battery over ``hours`` (one entry per hour, any order).

    With ``keep_hourly`` the result also lists every hour's charging,
    discharging and stored energy, for charts and checks.
    """
    ordered = sorted(hours, key=lambda hour: hour.start)
    actions = [_Actions() for _ in ordered]
    if battery.usable_kwh > _EPS and ordered:
        _run_plans(ordered, actions, battery, strategy, tz)
    return _summarize(ordered, actions, battery, strategy, tz, keep_hourly)


def _run_plans(
    hours: Sequence[Hour],
    actions: list[_Actions],
    battery: Battery,
    strategy: Strategy,
    tz: ZoneInfo,
) -> None:
    soc = 0.0
    start = 0
    count = len(hours)
    while start < count:
        plan_time = hours[start].start
        execute_until = _next_plan_time(plan_time, tz)
        horizon_end = _horizon_end(plan_time, tz)
        end = start
        while end < count and hours[end].start < horizon_end:
            end += 1
        executed = start
        while executed < end and hours[executed].start < execute_until:
            executed += 1
        executed = max(executed, start + 1)
        window = hours[start:end]
        plan, soc_path = _plan(window, soc, battery, strategy)
        for offset in range(executed - start):
            actions[start + offset] = plan[offset]
        soc = soc_path[executed - start - 1]
        start = executed


def _next_plan_time(moment: datetime, tz: ZoneInfo) -> datetime:
    """Return the first 13:00 (local) strictly after ``moment``."""
    local = moment.astimezone(tz)
    candidate = local.replace(hour=PLAN_HOUR, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate = _local_midnight(local.date() + timedelta(days=1), tz).replace(
            hour=PLAN_HOUR
        )
    return candidate


def _horizon_end(moment: datetime, tz: ZoneInfo) -> datetime:
    """Return the end of the last day whose prices are known at ``moment``.

    Before 13:00 only today's prices are known; from 13:00 also tomorrow's.
    """
    local = moment.astimezone(tz)
    days = 2 if local.hour >= PLAN_HOUR else 1
    return _local_midnight(local.date() + timedelta(days=days), tz)


def _local_midnight(day, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=tz)


def _plan(
    window: Sequence[Hour],
    initial_soc: float,
    battery: Battery,
    strategy: Strategy,
) -> tuple[list[_Actions], list[float]]:
    """Plan one window greedily; return per-hour actions and end-of-hour charge."""
    count = len(window)
    eta = battery.round_trip_efficiency
    power = battery.power_kw
    usable = battery.usable_kwh
    grid_limit = battery.grid_limit_kw
    wear = battery.wear_cost_per_kwh
    plan = [_Actions() for _ in window]
    soc = [initial_soc] * count
    init_left = initial_soc

    sources: list[tuple[int, int, float]] = []
    if initial_soc > _EPS:
        sources.append((_INIT, -1, 0.0))
    sinks: list[tuple[int, int, float]] = []
    for index, hour in enumerate(window):
        if hour.export_kwh > _EPS:
            sources.append((_SOLAR, index, hour.sell_price))
        if strategy is Strategy.GRID_TRADING:
            sources.append((_GRID, index, hour.buy_price))
        if hour.import_kwh > _EPS:
            sinks.append((_HOME, index, hour.buy_price))
        if strategy is not Strategy.SELF_CONSUMPTION:
            sinks.append((_SELL, index, hour.sell_price))

    candidates: list[tuple[float, int, int, int, int]] = []
    for source_kind, source_index, cost in sources:
        for sink_kind, sink_index, value in sinks:
            if sink_index <= source_index:
                continue
            gain = eta * (value - wear) - cost
            if gain > _EPS:
                candidates.append(
                    (gain, source_kind, source_index, sink_kind, sink_index)
                )
    candidates.sort(key=lambda item: item[0], reverse=True)

    for _gain, source_kind, i, sink_kind, j in candidates:
        sink = plan[j]
        if sink.charging > _EPS:
            continue
        hour_j = window[j]
        if sink_kind == _HOME:
            deliverable = min(
                hour_j.import_kwh - sink.to_home, power - sink.discharging
            )
        else:
            deliverable = power - sink.discharging
            if grid_limit is not None:
                deliverable = min(
                    deliverable, grid_limit - hour_j.export_kwh - sink.to_grid
                )
        if deliverable <= _EPS:
            continue
        stored = deliverable / eta
        if source_kind == _INIT:
            stored = min(stored, init_left)
        else:
            source = plan[i]
            if source.discharging > _EPS:
                continue
            hour_i = window[i]
            room = power - source.charging
            if source_kind == _SOLAR:
                room = min(room, hour_i.export_kwh - source.charge_solar)
            elif grid_limit is not None:
                room = min(room, grid_limit - hour_i.import_kwh - source.charge_grid)
            stored = min(stored, room, usable - max(soc[i:j]))
        if stored <= _EPS:
            continue
        if source_kind == _INIT:
            init_left -= stored
            for k in range(j, count):
                soc[k] -= stored
        else:
            source = plan[i]
            if source_kind == _SOLAR:
                source.charge_solar += stored
            else:
                source.charge_grid += stored
            for k in range(i, j):
                soc[k] += stored
        if sink_kind == _HOME:
            sink.to_home += stored * eta
        else:
            sink.to_grid += stored * eta
    return plan, soc


def _summarize(
    hours: Sequence[Hour],
    actions: Sequence[_Actions],
    battery: Battery,
    strategy: Strategy,
    tz: ZoneInfo,
    keep_hourly: bool,
) -> SimulationResult:
    total = Totals()
    by_month: dict[tuple[int, int], Totals] = {}
    hourly: list[HourResult] | None = [] if keep_hourly else None
    stored = 0.0
    by_year: dict[int, Totals] = {}
    eta = battery.round_trip_efficiency
    usable = battery.usable_kwh
    for hour, action in zip(hours, actions, strict=True):
        bought = hour.import_kwh - action.to_home + action.charge_grid
        sold = hour.export_kwh - action.charge_solar + action.to_grid
        delivered = action.discharging
        period = Totals(
            hours=1,
            baseline_cost=hour.import_kwh * hour.buy_price
            - hour.export_kwh * hour.sell_price,
            cost=bought * hour.buy_price - sold * hour.sell_price,
            wear_cost=delivered * battery.wear_cost_per_kwh,
            delivered_to_home_kwh=action.to_home,
            sold_from_battery_kwh=action.to_grid,
            charged_from_solar_kwh=action.charge_solar,
            charged_from_grid_kwh=action.charge_grid,
            full_cycles=(delivered / eta / usable) if usable > _EPS else 0.0,
        )
        total.add(period)
        local = hour.start.astimezone(tz)
        by_year.setdefault(local.year, Totals()).add(period)
        by_month.setdefault((local.year, local.month), Totals()).add(period)
        stored += action.charging - delivered / eta
        if hourly is not None:
            hourly.append(
                HourResult(
                    start=hour.start,
                    charged_from_solar=action.charge_solar,
                    charged_from_grid=action.charge_grid,
                    delivered_to_home=action.to_home,
                    sold_from_battery=action.to_grid,
                    stored_kwh=stored,
                )
            )
    return SimulationResult(
        battery=battery,
        strategy=strategy,
        total=total,
        by_year=by_year,
        by_month=by_month,
        hourly=hourly,
    )
