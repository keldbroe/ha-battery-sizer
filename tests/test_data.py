"""Reading energy and price statistics from Home Assistant's real recorder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.components.recorder.models import StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.battery_sizer.data import async_load_hours
from custom_components.battery_sizer.settings import Settings
from custom_components.battery_sizer.units import UnsupportedPriceUnit

START = datetime(2026, 3, 1, tzinfo=UTC)
NOW = START + timedelta(days=3)


def _metadata(statistic_id: str, unit: str, *, has_sum: bool) -> dict:
    """Build metadata with only the fields this Home Assistant declares."""
    annotations = set(getattr(StatisticMetaData, "__annotations__", {}))
    meta = {
        "has_sum": has_sum,
        "name": None,
        "source": "recorder",
        "statistic_id": statistic_id,
        "unit_of_measurement": unit,
    }
    if "mean_type" in annotations:
        from homeassistant.components.recorder.models import StatisticMeanType

        meta["mean_type"] = StatisticMeanType.NONE
    if "has_mean" in annotations:
        meta["has_mean"] = False
    if "unit_class" in annotations:
        meta["unit_class"] = "energy" if unit in {"Wh", "kWh", "MWh"} else None
    return meta


def _import(hass, statistic_id: str, unit: str, rows: list[dict], *, has_sum: bool):
    async_import_statistics(hass, _metadata(statistic_id, unit, has_sum=has_sum), rows)


@pytest.mark.usefixtures("recorder_mock")
async def test_inverter_history_becomes_hours_with_prices(hass) -> None:
    """Load and solar sums give import/export; price states give the prices."""
    hours = [START + timedelta(hours=i) for i in range(6)]
    load = [1.0, 1.0, 2.0, 0.5, 1.0, 3.0]
    solar = [0.0, 0.0, 3.0, 2.5, 0.0, 0.0]

    def sums(values):
        total = 100.0
        rows = []
        for moment, value in zip(hours, values, strict=True):
            total += value
            rows.append({"start": moment, "sum": total, "state": total})
        return rows

    _import(hass, "sensor.load_total", "kWh", sums(load), has_sum=True)
    _import(hass, "sensor.pv_total", "kWh", sums(solar), has_sum=True)
    _import(
        hass,
        "sensor.buy",
        "DKK/kWh",
        [{"start": t, "state": 2.0 + i, "sum": 0.0} for i, t in enumerate(hours)],
        has_sum=True,
    )
    _import(
        hass,
        "sensor.spot",
        "DKK/kWh",
        [{"start": t, "state": 0.5, "sum": 0.0} for t in hours],
        has_sum=True,
    )
    await async_wait_recording_done(hass)

    settings = Settings.from_mapping(
        {
            "source": "inverter",
            "load_statistic": "sensor.load_total",
            "solar_statistic": "sensor.pv_total",
            "buy_price_statistic": "sensor.buy",
            "sell_price_statistic": "sensor.spot",
            "sell_deduction": 0.1,
            "history_years": 1,
        }
    )
    loaded = await async_load_hours(hass, settings, NOW)
    assert loaded.missing == []
    # The first row only starts the running sum, so five hours have energy.
    assert len(loaded.hours) == 5
    by_start = {hour.start: hour for hour in loaded.hours}
    third = by_start[hours[2]]
    assert third.import_kwh == pytest.approx(0.0)
    assert third.export_kwh == pytest.approx(1.0)
    assert third.buy_price == pytest.approx(4.0)
    assert third.sell_price == pytest.approx(0.4)
    last = by_start[hours[5]]
    assert last.import_kwh == pytest.approx(3.0)
    assert last.export_kwh == pytest.approx(0.0)


@pytest.mark.usefixtures("recorder_mock")
async def test_a_statistic_without_rows_is_reported_missing(hass) -> None:
    settings = Settings.from_mapping(
        {
            "source": "grid",
            "import_statistic": "sensor.not_recorded",
            "buy_price_statistic": "sensor.buy_missing",
            "sell_price_statistic": "sensor.spot_missing",
        }
    )
    loaded = await async_load_hours(hass, settings, NOW)
    assert set(loaded.missing) == {
        "sensor.not_recorded",
        "sensor.buy_missing",
        "sensor.spot_missing",
    }
    assert loaded.hours == []


def _sums(hours, values, start=100.0):
    total = start
    rows = []
    for moment, value in zip(hours, values, strict=True):
        total += value
        rows.append({"start": moment, "sum": total, "state": total})
    return rows


def _flat(hours, value):
    return [{"start": t, "state": value, "sum": 0.0} for t in hours]


GRID = {
    "source": "grid",
    "import_statistic": "sensor.import_wh",
    "buy_price_statistic": "sensor.buy",
    "sell_price_statistic": "sensor.spot",
    "history_years": 1,
}


@pytest.mark.usefixtures("recorder_mock")
async def test_energy_in_wh_and_prices_per_mwh_or_in_ore_are_converted(hass) -> None:
    hours = [START + timedelta(hours=i) for i in range(4)]
    _import(hass, "sensor.import_wh", "Wh", _sums(hours, [1500.0] * 4), has_sum=True)
    _import(hass, "sensor.buy", "øre/kWh", _flat(hours, 250.0), has_sum=True)
    _import(hass, "sensor.spot", "DKK/MWh", _flat(hours, 600.0), has_sum=True)
    await async_wait_recording_done(hass)

    loaded = await async_load_hours(hass, Settings.from_mapping(GRID), NOW)
    assert len(loaded.hours) == 3
    hour = loaded.hours[0]
    assert hour.import_kwh == pytest.approx(1.5)
    assert hour.buy_price == pytest.approx(2.5)
    assert hour.sell_price == pytest.approx(0.6 - 0.05)


@pytest.mark.usefixtures("recorder_mock")
async def test_a_price_in_euro_is_refused(hass) -> None:
    hours = [START + timedelta(hours=i) for i in range(4)]
    _import(hass, "sensor.import_wh", "kWh", _sums(hours, [1.0] * 4), has_sum=True)
    _import(hass, "sensor.buy", "DKK/kWh", _flat(hours, 2.5), has_sum=True)
    _import(hass, "sensor.spot", "EUR/MWh", _flat(hours, 80.0), has_sum=True)
    await async_wait_recording_done(hass)

    with pytest.raises(UnsupportedPriceUnit) as err:
        await async_load_hours(hass, Settings.from_mapping(GRID), NOW)
    assert err.value.statistic == "sensor.spot"
    assert err.value.unit == "EUR/MWh"
