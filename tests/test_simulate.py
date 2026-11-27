"""Hand-checkable scenarios for the battery simulation."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.battery_sizer.engine import Battery, Hour, Strategy, simulate

TZ = ZoneInfo("Europe/Copenhagen")


def _day(values: dict[int, tuple[float, float, float, float]], *, days: int = 1):
    """Hours from 00:00 local; ``values`` maps hour -> (import, export, buy, sell).

    Hours not listed have no import or export and a flat price.
    """
    start = datetime(2026, 3, 2, tzinfo=TZ)
    hours = []
    for index in range(24 * days):
        imp, exp, buy, sell = values.get(index, (0.0, 0.0, 1.0, 0.5))
        hours.append(Hour(start + timedelta(hours=index), imp, exp, buy, sell))
    return hours


def _battery(capacity: float, **overrides) -> Battery:
    settings = {
        "capacity_kwh": capacity,
        "power_kw": 100.0,
        "usable_fraction": 1.0,
        "round_trip_efficiency": 1.0,
    }
    settings.update(overrides)
    return Battery(**settings)


def test_no_battery_saves_nothing() -> None:
    hours = _day({12: (0, 3, 1, 0.5), 18: (2, 0, 3, 0.5)})
    result = simulate(hours, _battery(0), Strategy.SELF_CONSUMPTION, tz=TZ)
    assert result.total.savings == pytest.approx(0)
    assert result.total.hours == 24


def test_solar_surplus_covers_the_most_expensive_hours_first() -> None:
    """3 kWh of surplus goes to the 3 kr hour, then the 2 kr hour, not the 1 kr."""
    hours = _day(
        {
            12: (0, 3, 1.0, 0.5),
            17: (2, 0, 1.0, 0.5),
            18: (2, 0, 3.0, 0.5),
            19: (2, 0, 2.0, 0.5),
        }
    )
    result = simulate(
        hours, _battery(10), Strategy.SELF_CONSUMPTION, tz=TZ, keep_hourly=True
    )
    delivered = {r.start.hour: r.delivered_to_home for r in result.hourly}
    assert delivered[18] == pytest.approx(2)
    assert delivered[19] == pytest.approx(1)
    assert delivered[17] == pytest.approx(0)
    # 2 kWh at 3 kr + 1 kWh at 2 kr, minus 3 kWh no longer sold at 0.5 kr.
    assert result.total.savings == pytest.approx(6.5)


def test_cheap_night_hours_are_left_to_the_grid() -> None:
    """With little surplus (winter), the 4 kr peak is covered, not later cheap hours.

    The cheap hours come after the surplus too, so they really compete for it.
    """
    hours = _day(
        {
            12: (0, 1, 1.0, 0.5),
            15: (1, 0, 1.2, 0.5),
            18: (1, 0, 4.0, 0.5),
            23: (1, 0, 0.9, 0.5),
            27: (1, 0, 0.8, 0.5),
        },
        days=2,
    )
    result = simulate(
        hours, _battery(10), Strategy.SELF_CONSUMPTION, tz=TZ, keep_hourly=True
    )
    delivered = [r.delivered_to_home for r in result.hourly]
    assert delivered[18] == pytest.approx(1)
    assert delivered[15] == pytest.approx(0)
    assert delivered[23] == pytest.approx(0)
    assert delivered[27] == pytest.approx(0)


def test_capacity_and_usable_fraction_limit_what_is_stored() -> None:
    hours = _day({12: (0, 5, 1.0, 0.5), 18: (5, 0, 3.0, 0.5)})
    result = simulate(
        hours,
        _battery(4, usable_fraction=0.5),
        Strategy.SELF_CONSUMPTION,
        tz=TZ,
    )
    assert result.total.charged_from_solar_kwh == pytest.approx(2)
    assert result.total.delivered_to_home_kwh == pytest.approx(2)


def test_power_limit_spreads_delivery_over_several_hours() -> None:
    hours = _day(
        {
            12: (0, 4, 1.0, 0.5),
            18: (4, 0, 3.0, 0.5),
            19: (4, 0, 2.0, 0.5),
        }
    )
    result = simulate(
        hours,
        _battery(10, power_kw=2),
        Strategy.SELF_CONSUMPTION,
        tz=TZ,
        keep_hourly=True,
    )
    by_hour = {r.start.hour: r for r in result.hourly}
    assert by_hour[12].charged_from_solar == pytest.approx(2)
    assert by_hour[18].delivered_to_home == pytest.approx(2)
    assert by_hour[19].delivered_to_home == pytest.approx(0)


def test_efficiency_loses_energy_and_can_make_storing_pointless() -> None:
    hours = _day({12: (0, 1, 1.0, 0.5), 18: (2, 0, 3.0, 0.5)})
    lossy = simulate(
        hours,
        _battery(10, round_trip_efficiency=0.8),
        Strategy.SELF_CONSUMPTION,
        tz=TZ,
    )
    assert lossy.total.delivered_to_home_kwh == pytest.approx(0.8)
    # Selling at 2.6 now beats 0.8 * 3.0 = 2.4 later, so nothing is stored.
    hours = _day({12: (0, 1, 1.0, 2.6), 18: (2, 0, 3.0, 0.5)})
    skipped = simulate(
        hours,
        _battery(10, round_trip_efficiency=0.8),
        Strategy.SELF_CONSUMPTION,
        tz=TZ,
    )
    assert skipped.total.charged_from_solar_kwh == pytest.approx(0)


def test_self_consumption_never_buys_to_store_or_sells_from_the_battery() -> None:
    hours = _day({2: (1, 0, 0.2, 0.1), 12: (0, 2, 1.0, 0.5), 18: (1, 0, 5.0, 4.0)})
    result = simulate(hours, _battery(10), Strategy.SELF_CONSUMPTION, tz=TZ)
    assert result.total.charged_from_grid_kwh == 0
    assert result.total.sold_from_battery_kwh == 0


def test_solar_trading_sells_surplus_later_when_that_pays_more() -> None:
    hours = _day({12: (0, 2, 1.0, 0.3), 19: (0, 0, 1.0, 2.0)})
    result = simulate(hours, _battery(10), Strategy.SOLAR_TRADING, tz=TZ)
    assert result.total.sold_from_battery_kwh == pytest.approx(2)
    assert result.total.charged_from_grid_kwh == 0
    assert result.total.savings == pytest.approx(2 * (2.0 - 0.3))


def test_grid_trading_needs_a_spread_larger_than_losses_and_wear() -> None:
    """Buy at 1 kr at night, avoid 4 kr in the evening: pays, unless wear eats it."""
    values = {3: (0, 0, 1.0, 0.5), 18: (2, 0, 4.0, 0.5)}
    hours = _day(values, days=1)
    trading = simulate(
        hours,
        _battery(10, round_trip_efficiency=0.9),
        Strategy.GRID_TRADING,
        tz=TZ,
    )
    assert trading.total.charged_from_grid_kwh == pytest.approx(2 / 0.9)
    assert trading.total.savings == pytest.approx(2 * 4.0 - (2 / 0.9) * 1.0)
    worn = simulate(
        hours,
        _battery(10, round_trip_efficiency=0.9, wear_cost_per_kwh=3.0),
        Strategy.GRID_TRADING,
        tz=TZ,
    )
    assert worn.total.charged_from_grid_kwh == pytest.approx(0)


def test_night_charge_for_tomorrow_morning_is_planned_at_13() -> None:
    """At 13:00 tomorrow's prices are known, so the 02:00 charge can serve 07:00."""
    start = datetime(2026, 3, 2, 13, tzinfo=TZ)
    hours = []
    for index in range(24):
        moment = start + timedelta(hours=index)
        local = moment.hour
        buy = 0.5 if local == 2 else (5.0 if local == 7 else 2.0)
        imp = 2.0 if local == 7 else 0.0
        hours.append(Hour(moment, imp, 0.0, buy, 0.1))
    result = simulate(
        hours, _battery(10), Strategy.GRID_TRADING, tz=TZ, keep_hourly=True
    )
    by_hour = {r.start.astimezone(TZ).hour: r for r in result.hourly}
    assert by_hour[2].charged_from_grid == pytest.approx(2)
    assert by_hour[7].delivered_to_home == pytest.approx(2)


def test_main_fuse_limits_charging_from_the_grid() -> None:
    hours = _day({3: (2, 0, 0.5, 0.1), 18: (10, 0, 4.0, 0.1)})
    result = simulate(
        hours,
        _battery(20, grid_limit_kw=3),
        Strategy.GRID_TRADING,
        tz=TZ,
        keep_hourly=True,
    )
    assert result.hourly[3].charged_from_grid <= 1 + 1e-9


def test_random_days_never_overfill_or_overdraw_and_never_lose_money() -> None:
    """Invariants on random data, for every strategy."""
    rng = random.Random(4)
    start = datetime(2026, 1, 1, tzinfo=TZ)
    hours = []
    for index in range(24 * 40):
        moment = start + timedelta(hours=index)
        solar = max(0.0, rng.gauss(1.5, 1.5)) if 9 <= moment.hour <= 16 else 0.0
        load = max(0.0, rng.gauss(0.8, 0.5))
        spot = rng.uniform(0.0, 2.5)
        hours.append(
            Hour(
                moment,
                max(load - solar, 0.0),
                max(solar - load, 0.0),
                spot * 1.25 + (1.3 if 17 <= moment.hour <= 20 else 0.4),
                spot - 0.05,
            )
        )
    battery = Battery(10, power_kw=3, usable_fraction=0.9, round_trip_efficiency=0.9)
    for strategy in Strategy:
        result = simulate(hours, battery, strategy, tz=TZ, keep_hourly=True)
        assert result.total.savings >= -1e-6
        for record in result.hourly:
            assert -1e-6 <= record.stored_kwh <= battery.usable_kwh + 1e-6
            charging = record.charged_from_solar + record.charged_from_grid
            delivering = record.delivered_to_home + record.sold_from_battery
            assert charging <= battery.power_kw + 1e-6
            assert delivering <= battery.power_kw + 1e-6
            assert charging < 1e-9 or delivering < 1e-9
        for hour, record in zip(hours, result.hourly, strict=True):
            assert record.delivered_to_home <= hour.import_kwh + 1e-6
            assert record.charged_from_solar <= hour.export_kwh + 1e-6
        if strategy is Strategy.SELF_CONSUMPTION:
            assert result.total.charged_from_grid_kwh == 0
            assert result.total.sold_from_battery_kwh == 0


def test_more_freedom_never_saves_less() -> None:
    """Grid trading can do all that solar trading can, which can do all of self use."""
    rng = random.Random(9)
    start = datetime(2026, 6, 1, tzinfo=TZ)
    hours = [
        Hour(
            start + timedelta(hours=i),
            rng.uniform(0, 1.5),
            rng.uniform(0, 2) if 9 <= (i % 24) <= 16 else 0.0,
            rng.uniform(1, 4),
            rng.uniform(0, 1.5),
        )
        for i in range(24 * 20)
    ]
    battery = Battery(8, power_kw=4, round_trip_efficiency=0.92)
    savings = [
        simulate(hours, battery, strategy, tz=TZ).total.savings
        for strategy in (
            Strategy.SELF_CONSUMPTION,
            Strategy.SOLAR_TRADING,
            Strategy.GRID_TRADING,
        )
    ]
    # The planner is greedy, so allow a small tolerance.
    assert savings[1] >= savings[0] * 0.97
    assert savings[2] >= savings[1] * 0.97


def test_results_are_split_by_local_year() -> None:
    start = datetime(2025, 12, 31, 20, tzinfo=TZ)
    hours = [Hour(start + timedelta(hours=i), 1.0, 0.0, 2.0, 0.5) for i in range(8)]
    result = simulate(hours, _battery(0), Strategy.SELF_CONSUMPTION, tz=TZ)
    assert result.by_year[2025].hours == 4
    assert result.by_year[2026].hours == 4
    assert result.annual_savings == 0


def test_a_typical_year_weights_every_calendar_month_once() -> None:
    """Two Januaries and one July still count as one January and one July."""
    hours = []
    for year, month, saving_price in ((2025, 1, 3.0), (2026, 1, 3.0), (2025, 7, 1.0)):
        start = datetime(year, month, 1, tzinfo=TZ)
        for index in range(24 * 31):
            moment = start + timedelta(hours=index)
            midday = moment.hour == 12
            evening = moment.hour == 18
            hours.append(
                Hour(
                    moment,
                    1.0 if evening else 0.0,
                    1.0 if midday else 0.0,
                    saving_price if evening else 1.0,
                    0.0,
                )
            )
    result = simulate(hours, _battery(5), Strategy.SELF_CONSUMPTION, tz=TZ)
    assert result.months_covered == 2
    # Fewer than 12 months: plain scaling of the total.
    assert result.annual_savings == pytest.approx(
        result.total.savings * 8760 / result.total.hours
    )


def test_a_full_year_of_months_uses_month_averages() -> None:
    """With all 12 months, a month seen twice is averaged, not double-counted."""
    hours = []
    for year, month in [(2025, m) for m in range(1, 13)] + [(2026, 1)]:
        start = datetime(year, month, 1, tzinfo=TZ)
        nxt = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=TZ)
        moment = start
        while moment < nxt:
            evening = moment.hour == 18
            price = 5.0 if (year, month) == (2026, 1) else 2.0
            hours.append(
                Hour(
                    moment,
                    1.0 if evening else 0.0,
                    1.0 if moment.hour == 12 else 0.0,
                    price if evening else 1.0,
                    0.0,
                )
            )
            moment += timedelta(hours=1)
    result = simulate(hours, _battery(5), Strategy.SELF_CONSUMPTION, tz=TZ)
    assert result.months_covered == 12
    january = [t for (y, m), t in result.by_month.items() if m == 1]
    assert len(january) == 2
    # January's share is the average of the two Januaries (2 and 5 kr/day).
    jan_daily = (january[0].savings + january[1].savings) / (31 * 2)
    assert jan_daily == pytest.approx((2.0 + 5.0) / 2, rel=0.05)
    plain = result.total.savings * 8760 / result.total.hours
    assert result.annual_savings < plain
