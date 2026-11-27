"""The integration in a real Home Assistant test instance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers import entity_registry as er
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
    CONF_GRID_LIMIT_KW,
    CONF_HISTORY_YEARS,
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
from custom_components.battery_sizer.data import LoadedData
from custom_components.battery_sizer.engine import Hour

pytestmark = pytest.mark.usefixtures("recorder_mock", "enable_custom_integrations")

TZ = ZoneInfo("Europe/Copenhagen")
OPTIONS = {
    CONF_SOURCE: "inverter",
    CONF_LOAD: "sensor.load_total",
    CONF_SOLAR: "sensor.pv_total",
    CONF_BUY_PRICE: "sensor.buy",
    CONF_SELL_PRICE: "sensor.spot",
    CONF_SELL_DEDUCTION: 0.05,
    CONF_EXISTING_KWH: 0,
    CONF_POWER_KW: 5,
    CONF_USABLE_PCT: 100,
    CONF_EFFICIENCY_PCT: 100,
    CONF_GRID_LIMIT_KW: 0,
    CONF_BATTERY_PRICE: 300,
    CONF_SYSTEM_PRICE: 0,
    CONF_SYSTEM_KWH: 0,
    CONF_EXPANSION_COST: 0,
    CONF_LIFETIME_YEARS: 10,
    CONF_CYCLE_LIFE: 10_000,
    CONF_DISCOUNT_PCT: 0,
    CONF_MAX_KWH: 10,
    CONF_STEP_KWH: 2,
    CONF_HISTORY_YEARS: 1,
}


def _summer(days: int = 60) -> list[Hour]:
    """6 kWh surplus at midday, 1.5 kWh bought each evening hour at 3 kr."""
    start = datetime(2026, 5, 1, tzinfo=TZ)
    hours = []
    for index in range(24 * days):
        moment = start + timedelta(hours=index)
        local = moment.hour
        hours.append(
            Hour(
                moment.astimezone(UTC),
                1.5 if 17 <= local <= 22 else 0.0,
                2.0 if 11 <= local <= 13 else 0.0,
                3.0 if 17 <= local <= 20 else 1.5,
                0.4,
            )
        )
    return hours


@pytest.fixture
def loads(monkeypatch: pytest.MonkeyPatch) -> list:
    """Replace the recorder read with fixed hours; record each call."""
    calls: list = []

    async def fake_load(hass, settings, now):
        calls.append(settings)
        return LoadedData(
            hours=_summer(),
            rows_by_statistic={s: 100 for s in settings.energy_statistics},
        )

    monkeypatch.setattr(coordinator_module, "async_load_hours", fake_load)
    return calls


async def _setup(hass, options=OPTIONS) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    entry = MockConfigEntry(domain=DOMAIN, title="Batteri", data={}, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


def _state(hass, key: str, entry):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None, key
    return hass.states.get(entity_id)


async def test_a_new_system_is_calculated_for_every_strategy(hass, loads) -> None:
    entry = await _setup(hass)
    assert len(loads) == 1
    size = _state(hass, "self_consumption_recommended_size", entry)
    # 6 kWh daily surplus: the best size within 0-10 kWh in steps of 2 is 6.
    assert float(size.state) == pytest.approx(6)
    assert size.attributes["unit_of_measurement"] == "kWh"
    assert size.attributes["pays_off"] is True
    table = size.attributes["sizes"]
    assert [row["kwh"] for row in table] == [2, 4, 6, 8, 10]
    assert {
        "annual_savings",
        "investment",
        "payback_years",
        "net_present_value",
        "cycles_per_year",
    } <= set(table[0])
    savings = _state(hass, "self_consumption_annual_savings", entry)
    assert float(savings.state) > 0
    assert savings.attributes["unit_of_measurement"] == "DKK"
    for strategy in ("solar_trading", "grid_trading"):
        assert (
            _state(hass, f"{strategy}_recommended_size", entry).state != "unavailable"
        )
    status = _state(hass, "last_calculation", entry)
    assert status.attributes["last_run_succeeded"] is True
    assert status.attributes["hours_used"] == 60 * 24


async def test_an_existing_battery_turns_it_into_an_expansion(hass, loads) -> None:
    """With 2 kWh already, adding 4 kWh uses up the 6 kWh surplus."""
    entry = await _setup(hass, {**OPTIONS, CONF_EXISTING_KWH: 2})
    added = _state(hass, "self_consumption_recommended_expansion", entry)
    assert float(added.state) == pytest.approx(4)
    assert added.attributes["expansion"] is True
    assert added.attributes["existing_kwh"] == 2
    assert added.attributes["existing_annual_savings"] > 0
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_self_consumption_recommended_size"
        )
        is None
    )


async def test_wear_above_any_gain_is_no_gain(hass, loads) -> None:
    entry = await _setup(hass, {**OPTIONS, CONF_BATTERY_PRICE: 50_000})
    size = _state(hass, "self_consumption_recommended_size", entry)
    assert float(size.state) == 0
    assert _state(hass, "self_consumption_verdict", entry).state == "no_gain"
    assert _state(hass, "self_consumption_payback", entry).state == "unknown"


async def test_nothing_pays_off_shows_the_closest_option(hass, loads) -> None:
    entry = await _setup(
        hass, {**OPTIONS, CONF_BATTERY_PRICE: 20_000, CONF_CYCLE_LIFE: 50_000}
    )
    size = _state(hass, "self_consumption_recommended_size", entry)
    assert float(size.state) == 0
    assert size.attributes["pays_off"] is False
    assert size.attributes["verdict"] == "does_not_pay_off"
    assert size.attributes["candidate_kwh"] > 0
    assert size.attributes["sizes"]
    verdict = _state(hass, "self_consumption_verdict", entry)
    assert verdict.state == "does_not_pay_off"
    assert float(_state(hass, "self_consumption_annual_savings", entry).state) > 0
    assert float(_state(hass, "self_consumption_net_present_value", entry).state) < 0
    payback = _state(hass, "self_consumption_payback", entry)
    assert float(payback.state) > 1
    assert payback.attributes["within_lifetime"] is False


async def test_verdict_when_it_pays_off(hass, loads) -> None:
    entry = await _setup(hass)
    assert _state(hass, "self_consumption_verdict", entry).state == "pays_off"
    payback = _state(hass, "self_consumption_payback", entry)
    assert payback.attributes["within_lifetime"] is True


async def test_button_and_action_calculate_again(hass, loads) -> None:
    entry = await _setup(hass)
    button = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_calculate"
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(DOMAIN, "calculate", blocking=True)
    assert len(loads) >= 3


async def test_missing_history_is_reported_on_the_status_sensor(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def empty(hass, settings, now):
        return LoadedData(
            hours=[], rows_by_statistic={"sensor.load_total": 0, "sensor.buy": 10}
        )

    monkeypatch.setattr(coordinator_module, "async_load_hours", empty)
    entry = await _setup(hass)
    status = _state(hass, "last_calculation", entry)
    assert status.attributes["last_run_succeeded"] is False
    assert "sensor.load_total" in status.attributes["error"]
    assert (
        _state(hass, "self_consumption_recommended_size", entry).state == "unavailable"
    )


async def test_too_little_overlap_is_reported(hass, monkeypatch) -> None:
    async def short(hass, settings, now):
        return LoadedData(hours=_summer(5), rows_by_statistic={"x": 1})

    monkeypatch.setattr(coordinator_module, "async_load_hours", short)
    entry = await _setup(hass)
    error = _state(hass, "last_calculation", entry).attributes["error"]
    assert "30 days" in error


async def test_results_command_feeds_the_panel(hass, loads, hass_ws_client) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "battery_sizer/results"})
    reply = await client.receive_json()
    assert reply["success"]
    [item] = reply["result"]["entries"]
    assert item["entry_id"] == entry.entry_id
    assert item["status_entity"].startswith("sensor.")
    assert item["lifetime_years"] == 10
    result = item["result"]
    assert result["hours"] == 24 * 60
    own = result["strategies"]["self_consumption"]
    assert own["verdict"] == "pays_off"
    assert own["sizes"]
    assert [row["month"] for row in own["monthly"]] == list(range(1, 13))
    by_month = {row["month"]: row for row in own["monthly"]}
    # The history covers May and June only.
    assert by_month[5]["savings"] > 0
    assert by_month[5]["delivered_kwh"] > 0
    assert by_month[1]["savings"] is None


async def test_expansion_monthly_counts_only_the_extra(
    hass, loads, hass_ws_client
) -> None:
    await _setup(hass, {**OPTIONS, CONF_EXISTING_KWH: 2})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "battery_sizer/results"})
    reply = await client.receive_json()
    own = reply["result"]["entries"][0]["result"]["strategies"]["self_consumption"]
    existing = {row["month"]: row for row in own["existing_monthly"]}
    extra = {row["month"]: row for row in own["monthly"]}
    assert existing[5]["savings"] > 0
    # Only what the added kWh save on top of the 2 kWh already there: May
    # and June (61 days), scaled to a year, give the extra annual savings.
    assert extra[5]["savings"] > 0
    total = sum(row["savings"] or 0 for row in own["monthly"])
    assert total * 365 / 61 == pytest.approx(own["annual_savings"], rel=0.01)


async def test_panel_is_added_with_the_frontend_and_removed_with_the_entry(
    hass, loads, monkeypatch
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from homeassistant.components import frontend, panel_custom

    register = AsyncMock()
    remove = MagicMock()
    monkeypatch.setattr(panel_custom, "async_register_panel", register)
    monkeypatch.setattr(frontend, "async_remove_panel", remove)
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components.add("frontend")

    entry = await _setup(hass)
    register.assert_awaited_once()
    assert register.await_args.kwargs["frontend_url_path"] == "battery-sizer"
    assert register.await_args.kwargs["module_url"].startswith(
        "/battery_sizer_static/panel.js"
    )
    hass.http.async_register_static_paths.assert_awaited_once()

    assert await hass.config_entries.async_unload(entry.entry_id)
    remove.assert_called_once_with(hass, "battery-sizer")

    # Set up again: the panel comes back, the static path is not added twice.
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert register.await_count == 2
    hass.http.async_register_static_paths.assert_awaited_once()


async def test_settings_command_lists_the_fields_in_danish(
    hass, loads, hass_ws_client
) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "battery_sizer/settings", "language": "da"}
    )
    reply = await client.receive_json()
    assert reply["success"]
    result = reply["result"]
    assert result["can_edit"] is True
    groups = result["entries"][entry.entry_id]["groups"]
    assert [group["key"] for group in groups] == ["battery", "prices", "costs"]
    fields = {field["key"]: field for group in groups for field in group["fields"]}
    assert "buy_price_statistic" not in fields
    assert fields["power_kw"]["label"] == "Inverterens effekt"
    assert fields["power_kw"]["value"] == 5
    assert fields["power_kw"]["unit"] == "kW"
    assert fields["battery_price_per_kwh"]["max"] == 50_000
    assert "system_price_too_low" in result["errors"]


async def test_update_settings_saves_and_calculates_again(
    hass, loads, hass_ws_client
) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": "battery_sizer/update_settings",
            "entry_id": entry.entry_id,
            "values": {"power_kw": 12, "battery_price_per_kwh": 750},
        }
    )
    reply = await client.receive_json()
    assert reply["success"], reply
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.options["power_kw"] == 12
    assert entry.options["battery_price_per_kwh"] == 750
    # Untouched values and the statistics stay.
    assert entry.options[CONF_LOAD] == "sensor.load_total"
    assert len(loads) == 2
    assert loads[-1].power_kw == 12


async def test_update_settings_rejects_bad_values(hass, loads, hass_ws_client) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    cases = [
        ({"power_kw": 0}, "out_of_range"),
        ({"buy_price_statistic": "sensor.x"}, "invalid_format"),
        ({CONF_SYSTEM_PRICE: 100, CONF_SYSTEM_KWH: 10}, "invalid_settings"),
    ]
    for index, (values, code) in enumerate(cases, start=1):
        await client.send_json(
            {
                "id": index,
                "type": "battery_sizer/update_settings",
                "entry_id": entry.entry_id,
                "values": values,
            }
        )
        reply = await client.receive_json()
        assert not reply["success"]
        assert reply["error"]["code"] == code
    assert entry.options == OPTIONS
    assert len(loads) == 1


async def test_only_an_admin_can_change_settings(
    hass, loads, hass_ws_client, hass_read_only_access_token
) -> None:
    entry = await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "battery_sizer/settings"})
    reply = await client.receive_json()
    assert reply["result"]["can_edit"] is False
    await client.send_json(
        {
            "id": 2,
            "type": "battery_sizer/update_settings",
            "entry_id": entry.entry_id,
            "values": {"power_kw": 12},
        }
    )
    reply = await client.receive_json()
    assert reply["error"]["code"] == "unauthorized"
    assert entry.options == OPTIONS
