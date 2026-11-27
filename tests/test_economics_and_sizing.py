"""Economics, the size sweep, statistics conversion and price rebuilding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.battery_sizer.engine import (
    Battery,
    Costs,
    Hour,
    Strategy,
    default_sizes,
    evaluate,
    recommend,
    recommend_expansion,
)
from custom_components.battery_sizer.engine.pricing import (
    buy_price,
    with_current_tariffs,
)
from custom_components.battery_sizer.engine.series import (
    build_hours,
    energy_from_sums,
    split_gross,
    values_by_hour,
)

TZ = ZoneInfo("Europe/Copenhagen")
T0 = datetime(2026, 3, 2, tzinfo=UTC)


def _h(offset: int) -> datetime:
    return T0 + timedelta(hours=offset)


# --- economics --------------------------------------------------------------


def test_investment_payback_and_net_present_value() -> None:
    costs = Costs(
        price_per_kwh=3000,
        fixed_cost=5000,
        lifetime_years=10,
        cycle_life=10_000,
        discount_rate=0.0,
    )
    result = evaluate(10, annual_savings=5000, annual_cycles=300, costs=costs)
    assert result.investment == pytest.approx(35_000)
    assert result.payback_years == pytest.approx(7)
    assert result.lifetime_years == pytest.approx(10)
    assert result.net_present_value == pytest.approx(50_000 - 35_000)
    assert result.pays_off


def test_cycle_life_can_end_the_battery_before_its_years() -> None:
    costs = Costs(
        price_per_kwh=1000, lifetime_years=20, cycle_life=3000, discount_rate=0.0
    )
    result = evaluate(5, annual_savings=1000, annual_cycles=600, costs=costs)
    assert result.lifetime_years == pytest.approx(5)
    assert result.net_present_value == pytest.approx(5 * 1000 - 5000)
    assert result.payback_years == pytest.approx(5)


def test_no_payback_when_savings_do_not_cover_the_price() -> None:
    costs = Costs(price_per_kwh=4000, lifetime_years=10, discount_rate=0.05)
    result = evaluate(10, annual_savings=1000, annual_cycles=100, costs=costs)
    assert result.payback_years is None
    assert not result.pays_off


def test_discounting_lowers_the_value_of_later_savings() -> None:
    flat = evaluate(1, 1000, 100, Costs(price_per_kwh=0, discount_rate=0.0))
    discounted = evaluate(1, 1000, 100, Costs(price_per_kwh=0, discount_rate=0.05))
    assert discounted.net_present_value < flat.net_present_value


def test_wear_per_kwh_comes_from_price_and_cycle_life() -> None:
    costs = Costs(price_per_kwh=3000, cycle_life=6000)
    assert costs.wear_cost_per_kwh(0.9) == pytest.approx(3000 / 5400)


# --- size sweep -------------------------------------------------------------


def _summer_days(days: int = 60) -> list[Hour]:
    """Every day: 6 kWh surplus at midday, 1.5 kWh bought each evening hour."""
    start = datetime(2026, 5, 1, tzinfo=TZ)
    hours = []
    for index in range(24 * days):
        moment = start + timedelta(hours=index)
        local = moment.hour
        export = 2.0 if 11 <= local <= 13 else 0.0
        imp = 1.5 if 17 <= local <= 22 else 0.0
        buy = 3.0 if 17 <= local <= 20 else 1.5
        hours.append(Hour(moment, imp, export, buy, 0.4))
    return hours


def test_savings_grow_until_the_daily_surplus_is_used_up() -> None:
    hours = _summer_days()
    template = Battery(0, power_kw=5, usable_fraction=1.0, round_trip_efficiency=1.0)
    rec = recommend(
        hours,
        template,
        Strategy.SELF_CONSUMPTION,
        Costs(price_per_kwh=0.0),
        tz=TZ,
        sizes=[0, 2, 4, 6, 8, 10],
        include_wear=False,
    )
    savings = {r.capacity_kwh: r.simulation.annual_savings for r in rec.sizes}
    assert savings[0] == 0
    assert savings[2] < savings[4] < savings[6]
    # 6 kWh of daily surplus: more capacity than that adds nothing.
    assert savings[8] == pytest.approx(savings[6])
    assert savings[10] == pytest.approx(savings[6])


def test_recommendation_is_the_size_with_the_highest_net_value() -> None:
    hours = _summer_days()
    template = Battery(0, power_kw=5, usable_fraction=1.0, round_trip_efficiency=1.0)
    rec = recommend(
        hours,
        template,
        Strategy.SELF_CONSUMPTION,
        Costs(
            price_per_kwh=500, lifetime_years=10, cycle_life=100_000, discount_rate=0.0
        ),
        tz=TZ,
        sizes=[0, 2, 4, 6, 8],
        include_wear=False,
    )
    best = max(
        (r for r in rec.sizes if r.capacity_kwh > 0),
        key=lambda r: r.economics.net_present_value,
    )
    assert rec.best is best
    # A bigger battery than the daily surplus only adds cost.
    assert rec.best_capacity_kwh <= 6


def test_no_recommendation_when_nothing_pays_off() -> None:
    hours = _summer_days(10)
    rec = recommend(
        hours,
        Battery(0, power_kw=5),
        Strategy.SELF_CONSUMPTION,
        Costs(price_per_kwh=50_000),
        tz=TZ,
        sizes=[0, 5, 10],
    )
    assert rec.best is None
    assert rec.best_capacity_kwh == 0


def test_progress_is_reported_per_size() -> None:
    seen: list[tuple[int, int]] = []
    recommend(
        _summer_days(2),
        Battery(0),
        Strategy.SELF_CONSUMPTION,
        Costs(),
        tz=TZ,
        sizes=[0, 5],
        progress=lambda done, total: seen.append((done, total)),
    )
    assert seen == [(1, 2), (2, 2)]


def test_default_sizes() -> None:
    assert default_sizes(10, 2.5) == [0, 2.5, 5, 7.5, 10]


# --- statistics to hours ----------------------------------------------------


def test_energy_is_the_difference_between_consecutive_sums() -> None:
    rows = [(_h(0), 10.0), (_h(1), 11.5), (_h(2), 11.5), (_h(3), 14.0)]
    assert energy_from_sums(rows) == {
        _h(1): pytest.approx(1.5),
        _h(2): pytest.approx(0.0),
        _h(3): pytest.approx(2.5),
    }


def test_gaps_missing_values_and_decreasing_sums_are_left_out() -> None:
    rows = [
        (_h(0), 10.0),
        (_h(1), 11.0),
        (_h(3), 15.0),  # gap: hour 2 missing, so hour 3 cannot be placed
        (_h(4), 16.0),
        (_h(5), None),
        (_h(6), 18.0),
        (_h(7), 2.0),  # meter replaced
        (_h(8), 3.0),
    ]
    assert energy_from_sums(rows) == {
        _h(1): pytest.approx(1.0),
        _h(4): pytest.approx(1.0),
        _h(8): pytest.approx(1.0),
    }


def test_prices_by_hour_skip_empty_values_and_align_to_the_hour() -> None:
    rows = [(_h(0) + timedelta(minutes=0), 2.5), (_h(1), None), (_h(2), 1.0)]
    assert values_by_hour(rows) == {_h(0): 2.5, _h(2): 1.0}


def test_gross_load_and_solar_become_import_and_export() -> None:
    imports, exports = split_gross(
        {_h(0): 2.0, _h(1): 0.5, _h(2): 1.0}, {_h(0): 0.5, _h(1): 2.0}
    )
    assert imports == {_h(0): 1.5, _h(1): 0.0}
    assert exports == {_h(0): 0.0, _h(1): 1.5}


def test_hours_are_built_where_import_and_both_prices_exist() -> None:
    hours = build_hours(
        imports={_h(0): 1.0, _h(1): 2.0, _h(2): 3.0},
        exports={_h(1): 0.5},
        buy_prices={_h(0): 2.0, _h(1): 2.5},
        sell_prices={_h(0): 1.0, _h(1): 1.2, _h(2): 1.3},
        sell_adjustment=-0.1,
    )
    assert [h.start for h in hours] == [_h(0), _h(1)]
    assert hours[0].export_kwh == 0.0
    assert hours[1].export_kwh == 0.5
    assert hours[1].sell_price == pytest.approx(1.1)


# --- prices -----------------------------------------------------------------


def test_buy_price_adds_tariffs_then_vat() -> None:
    assert buy_price(
        1.0, grid_tariff=0.43, other_tariffs=0.15, supplier_markup=0.02
    ) == pytest.approx((1.6) * 1.25)


def test_current_tariffs_replace_the_recorded_buy_price_by_local_hour() -> None:
    evening = datetime(2026, 1, 15, 17, tzinfo=TZ).astimezone(UTC)
    night = datetime(2026, 1, 15, 3, tzinfo=TZ).astimezone(UTC)
    unknown = datetime(2026, 1, 15, 5, tzinfo=TZ).astimezone(UTC)
    hours = [
        Hour(evening, 1.0, 0.0, 9.9, 0.5),
        Hour(night, 1.0, 0.0, 9.9, 0.5),
        Hour(unknown, 1.0, 0.0, 9.9, 0.5),
    ]
    rebuilt = with_current_tariffs(
        hours,
        {evening: 1.0, night: 0.2},
        grid_tariff_by_hour={17: 1.3, 3: 0.14},
        other_tariffs=0.15,
        tz=TZ,
    )
    assert rebuilt[0].buy_price == pytest.approx((1.0 + 1.3 + 0.15) * 1.25)
    assert rebuilt[1].buy_price == pytest.approx((0.2 + 0.14 + 0.15) * 1.25)
    assert rebuilt[2].buy_price == 9.9


# --- prices you type in, and expansion --------------------------------------


def test_system_price_includes_a_battery_and_sets_the_rest_as_fixed() -> None:
    """A 120,000 kr system with 10 kWh at 3,000 kr/kWh: 90,000 kr besides it."""
    costs = Costs.from_system_price(120_000, 10, 3000, lifetime_years=12)
    assert costs.fixed_cost == pytest.approx(90_000)
    assert costs.lifetime_years == 12
    assert costs.system_investment(10) == pytest.approx(120_000)
    assert costs.system_investment(15) == pytest.approx(135_000)
    assert costs.system_investment(0) == 0


def test_system_price_below_its_own_battery_is_rejected() -> None:
    with pytest.raises(ValueError, match="system price"):
        Costs.from_system_price(20_000, 10, 3000)


def test_expansion_pays_for_modules_and_fitting_only() -> None:
    costs = Costs(price_per_kwh=2500, fixed_cost=80_000, expansion_cost=3000)
    assert costs.expansion_investment(5) == pytest.approx(15_500)
    assert costs.expansion_investment(0) == 0


def test_expansion_is_judged_on_extra_savings_only() -> None:
    """6 kWh of daily surplus: going from 2 to 6 kWh pays, beyond 6 adds nothing."""
    hours = _summer_days()
    template = Battery(0, power_kw=5, usable_fraction=1.0, round_trip_efficiency=1.0)
    costs = Costs(
        price_per_kwh=100,
        expansion_cost=0,
        lifetime_years=10,
        cycle_life=100_000,
        discount_rate=0.0,
    )
    rec = recommend_expansion(
        hours,
        template,
        Strategy.SELF_CONSUMPTION,
        costs,
        existing_kwh=2,
        tz=TZ,
        added=[2, 4, 6],
        include_wear=False,
    )
    by_added = {o.added_kwh: o for o in rec.options}
    assert by_added[2].total_kwh == 4
    expected = by_added[4].simulation.annual_savings - rec.existing.annual_savings
    assert by_added[4].extra_annual_savings == pytest.approx(expected)
    assert by_added[4].economics.investment == pytest.approx(400)
    # Beyond the 6 kWh surplus (2 + 4) there is nothing more to gain.
    assert by_added[6].extra_annual_savings == pytest.approx(
        by_added[4].extra_annual_savings
    )
    assert rec.best is by_added[4]
    assert rec.best_added_kwh == 4


def test_no_expansion_is_recommended_when_the_battery_is_already_big() -> None:
    hours = _summer_days(20)
    rec = recommend_expansion(
        hours,
        Battery(0, power_kw=5, usable_fraction=1.0, round_trip_efficiency=1.0),
        Strategy.SELF_CONSUMPTION,
        Costs(price_per_kwh=2500, expansion_cost=2000),
        existing_kwh=10,
        tz=TZ,
        added=[2.5, 5],
    )
    assert all(o.extra_annual_savings == pytest.approx(0) for o in rec.options)
    assert rec.best is None
    assert rec.best_added_kwh == 0


def test_expansion_needs_an_existing_battery() -> None:
    with pytest.raises(ValueError, match="existing_kwh"):
        recommend_expansion(
            [], Battery(0), Strategy.SELF_CONSUMPTION, Costs(), existing_kwh=0, tz=TZ
        )
