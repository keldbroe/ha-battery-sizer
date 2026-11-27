"""Setup and options: picking statistics and typing in the missing values."""

from __future__ import annotations

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.battery_sizer import coordinator as coordinator_module
from custom_components.battery_sizer.const import (
    CONF_BATTERY_PRICE,
    CONF_BUY_PRICE,
    CONF_CYCLE_LIFE,
    CONF_DISCOUNT_PCT,
    CONF_EFFICIENCY_PCT,
    CONF_EXISTING_KWH,
    CONF_EXPANSION_COST,
    CONF_EXPORT,
    CONF_GRID_LIMIT_KW,
    CONF_HISTORY_YEARS,
    CONF_IMPORT,
    CONF_LIFETIME_YEARS,
    CONF_LOAD,
    CONF_MAX_KWH,
    CONF_POWER_KW,
    CONF_SELL_DEDUCTION,
    CONF_SELL_PRICE,
    CONF_SOLAR,
    CONF_SOURCE,
    CONF_STEP_KWH,
    CONF_SYSTEM_KWH,
    CONF_SYSTEM_PRICE,
    CONF_USABLE_PCT,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("recorder_mock", "enable_custom_integrations")

PRICES = {
    CONF_BUY_PRICE: "sensor.energi_data_service",
    CONF_SELL_PRICE: "sensor.nordpool_kwh_dk2_dkk_2_10_0",
    CONF_SELL_DEDUCTION: 0.05,
}
BATTERY = {
    CONF_EXISTING_KWH: 0,
    CONF_POWER_KW: 6,
    CONF_USABLE_PCT: 90,
    CONF_EFFICIENCY_PCT: 90,
    CONF_GRID_LIMIT_KW: 17,
}
COSTS = {
    CONF_BATTERY_PRICE: 750,
    CONF_SYSTEM_PRICE: 60_000,
    CONF_SYSTEM_KWH: 16,
    CONF_EXPANSION_COST: 0,
    CONF_LIFETIME_YEARS: 15,
    CONF_CYCLE_LIFE: 6000,
    CONF_DISCOUNT_PCT: 3,
    CONF_MAX_KWH: 30,
    CONF_STEP_KWH: 2.5,
    CONF_HISTORY_YEARS: 3,
}


@pytest.fixture(autouse=True)
def no_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flow tests do not need a real calculation after setup."""

    async def fail(*args, **kwargs):
        raise coordinator_module.UpdateFailed("not in this test")

    monkeypatch.setattr(coordinator_module, "async_load_hours", fail)


async def _walk(hass, flow, *pages):
    result = flow
    for page in pages:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], page)
    return result


async def test_inverter_setup_collects_every_page(hass) -> None:
    """Source, energy, prices, battery, costs: then one entry with all values."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "source"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: "inverter"}
    )
    assert result["step_id"] == "energy"
    assert CONF_LOAD in {str(key) for key in result["data_schema"].schema}
    result = await _walk(
        hass,
        result,
        {CONF_LOAD: "sensor.load_total", CONF_SOLAR: "sensor.pv_total"},
        PRICES,
        BATTERY,
        COSTS,
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    options = result["options"]
    assert options[CONF_SOURCE] == "inverter"
    assert options[CONF_LOAD] == "sensor.load_total"
    assert options[CONF_BATTERY_PRICE] == 750
    assert options[CONF_SYSTEM_PRICE] == 60_000


async def test_grid_setup_allows_no_export(hass) -> None:
    """A home without solar has no export statistic."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await _walk(
        hass,
        result,
        {CONF_SOURCE: "grid"},
        {CONF_IMPORT: "eloverblik_dk:energy_571313174001057915"},
        PRICES,
        BATTERY,
        COSTS,
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_IMPORT].startswith("eloverblik_dk:")
    assert CONF_EXPORT not in result["options"]


async def test_a_system_price_below_its_own_battery_is_caught(hass) -> None:
    """16 kWh at 3,000 kr/kWh cannot be inside a 20,000 kr system."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await _walk(
        hass,
        result,
        {CONF_SOURCE: "grid"},
        {CONF_IMPORT: "sensor.import"},
        PRICES,
        BATTERY,
        {**COSTS, CONF_BATTERY_PRICE: 3000, CONF_SYSTEM_PRICE: 20_000},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "costs"
    assert result["errors"]["base"] == "system_price_too_low"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**COSTS, CONF_BATTERY_PRICE: 3000, CONF_SYSTEM_PRICE: 90_000},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_invalid_sizes_are_caught(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await _walk(
        hass,
        result,
        {CONF_SOURCE: "grid"},
        {CONF_IMPORT: "sensor.import"},
        PRICES,
        BATTERY,
        {**COSTS, CONF_MAX_KWH: 2, CONF_STEP_KWH: 5},
    )
    assert result["errors"]["base"] == "invalid_sizes"


async def test_options_start_from_the_current_values_and_save_changes(hass) -> None:
    """Typing in an existing battery later switches to the expansion question."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Batteri-beregner (DK)",
        data={},
        options={
            CONF_SOURCE: "inverter",
            CONF_LOAD: "sensor.load_total",
            CONF_SOLAR: "sensor.pv_total",
            **PRICES,
            **BATTERY,
            **COSTS,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "source"
    for page in (
        {CONF_SOURCE: "inverter"},
        {CONF_LOAD: "sensor.load_total", CONF_SOLAR: "sensor.pv_total"},
        PRICES,
        {**BATTERY, CONF_EXISTING_KWH: 60, CONF_POWER_KW: 12},
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], page
        )
    assert result["step_id"] == "costs"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**COSTS, CONF_EXPANSION_COST: 1500}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_EXISTING_KWH] == 60
    assert entry.options[CONF_POWER_KW] == 12
    assert entry.options[CONF_EXPANSION_COST] == 1500
    assert entry.options[CONF_LOAD] == "sensor.load_total"


async def test_switching_source_drops_the_old_statistics(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_SOURCE: "grid",
            CONF_IMPORT: "sensor.import",
            CONF_EXPORT: "sensor.export",
            **PRICES,
            **BATTERY,
            **COSTS,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    for page in (
        {CONF_SOURCE: "inverter"},
        {CONF_LOAD: "sensor.load_total", CONF_SOLAR: "sensor.pv_total"},
        PRICES,
        BATTERY,
        COSTS,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], page
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_IMPORT not in entry.options
    assert CONF_EXPORT not in entry.options
    assert entry.options[CONF_SOURCE] == "inverter"


async def test_statistics_are_offered_in_plain_drop_downs(hass) -> None:
    """The fields are drop-downs filled from the recorder, never the statistic picker.

    The statistic picker left the whole setup page blank in the frontend.
    Energy fields list cumulative kWh statistics, external ones included;
    price fields list statistics per kWh. Other statistics are left out.
    """
    from datetime import UTC, datetime, timedelta

    from homeassistant.components.recorder.statistics import (
        async_add_external_statistics,
        async_import_statistics,
    )
    from pytest_homeassistant_custom_component.components.recorder.common import (
        async_wait_recording_done,
    )

    from tests.test_data import _metadata

    start = datetime(2026, 3, 1, tzinfo=UTC)
    rows = [
        {"start": start + timedelta(hours=i), "sum": float(i), "state": float(i)}
        for i in range(3)
    ]
    async_import_statistics(
        hass, _metadata("sensor.load_total", "kWh", has_sum=True), rows
    )
    external = _metadata("eloverblik_dk:energy_571313174001057915", "kWh", has_sum=True)
    external["source"] = "eloverblik_dk"
    async_add_external_statistics(hass, external, rows)
    async_import_statistics(
        hass, _metadata("sensor.buy", "DKK/kWh", has_sum=True), rows
    )
    async_import_statistics(
        hass, _metadata("sensor.outdoor_temperature", "°C", has_sum=True), rows
    )
    await async_wait_recording_done(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: "grid"}
    )

    def options(step, key):
        field = step["data_schema"].schema[key]
        assert field.serialize()["selector"].keys() == {"select"}
        return {option["value"] for option in field.config["options"]}

    energy = options(result, CONF_IMPORT)
    assert "sensor.load_total" in energy
    assert "eloverblik_dk:energy_571313174001057915" in energy
    assert "sensor.buy" not in energy
    assert "sensor.outdoor_temperature" not in energy
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_IMPORT: "eloverblik_dk:energy_571313174001057915"}
    )
    prices = options(result, CONF_BUY_PRICE)
    assert prices == {"sensor.buy"}
    # A statistic id that is not in the list can still be typed in.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**PRICES, CONF_SELL_PRICE: "sensor.typed_in"}
    )
    assert result["step_id"] == "battery"
