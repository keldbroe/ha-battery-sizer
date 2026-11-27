"""A sidebar panel with charts, and the websocket command that feeds it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .config_flow import battery_schema, costs_schema, prices_schema
from .const import DEFAULTS, DOMAIN, NAME, VERSION
from .coordinator import BatterySizerCoordinator, CalculationResult
from .engine import Strategy
from .settings import Settings, SettingsError

PANEL_URL_PATH = "battery-sizer"
PANEL_COMPONENT = "battery-sizer-panel"
PANEL_ICON = "mdi:battery-charging-high"
STATIC_URL = f"/{DOMAIN}_static"
FRONTEND_DIR = Path(__file__).parent / "frontend"
WS_RESULTS = f"{DOMAIN}/results"
WS_SETTINGS = f"{DOMAIN}/settings"
WS_UPDATE_SETTINGS = f"{DOMAIN}/update_settings"

_PANEL_KEY = f"{DOMAIN}_panel"
_STATIC_KEY = f"{DOMAIN}_static_path"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the command that returns every entry's result."""
    websocket_api.async_register_command(hass, ws_results)
    websocket_api.async_register_command(hass, ws_settings)
    websocket_api.async_register_command(hass, ws_update_settings)


@websocket_api.websocket_command({vol.Required("type"): WS_RESULTS})
@callback
def ws_results(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the latest calculation of every loaded entry."""
    connection.send_result(msg["id"], {"entries": results_payload(hass)})


def results_payload(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Everything the panel draws, in plain JSON types."""
    registry = er.async_get(hass)
    entries: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        coordinator: BatterySizerCoordinator = entry.runtime_data
        status_entity = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_last_calculation"
        )
        item: dict[str, Any] = {
            "entry_id": entry.entry_id,
            "title": entry.title or NAME,
            "status_entity": status_entity,
            "expansion": coordinator.settings.is_expansion,
            "lifetime_years": _lifetime(coordinator),
            "last_run_succeeded": coordinator.last_update_success,
            "error": str(coordinator.last_exception)
            if not coordinator.last_update_success and coordinator.last_exception
            else None,
            "result": None,
        }
        result = coordinator.data
        if result is not None:
            item["result"] = _result(result)
        entries.append(item)
    return entries


def _lifetime(coordinator: BatterySizerCoordinator) -> float | None:
    try:
        return coordinator.settings.costs().lifetime_years
    except SettingsError:
        return None


def _result(result: CalculationResult) -> dict[str, Any]:
    strategies: dict[str, Any] = {}
    for strategy in Strategy:
        outcome = result.outcomes.get(strategy)
        if outcome is None:
            continue
        strategies[str(strategy)] = {
            "verdict": outcome.verdict,
            "recommended_kwh": outcome.recommended_kwh,
            "candidate_kwh": outcome.candidate_kwh,
            "annual_savings": outcome.annual_savings,
            "payback_years": outcome.payback_years,
            "payback_within_lifetime": outcome.payback_within_lifetime,
            "net_present_value": outcome.net_present_value,
            "investment": outcome.investment,
            "cycles_per_year": outcome.cycles_per_year,
            "sizes": outcome.table,
            "monthly": outcome.monthly,
            "existing_annual_savings": round(
                result.existing_annual_savings.get(strategy, 0.0)
            ),
            "existing_monthly": result.existing_monthly.get(strategy, []),
        }
    return {
        "calculated_at": result.calculated_at.isoformat(),
        "hours": result.hours,
        "first": result.first.isoformat() if result.first else None,
        "last": result.last.isoformat() if result.last else None,
        "months_covered": result.months_covered,
        "existing_kwh": result.existing_kwh,
        "strategies": strategies,
    }


async def async_register_panel(hass: HomeAssistant) -> None:
    """Add the sidebar panel once, if the frontend is running."""
    if hass.data.get(_PANEL_KEY) or "frontend" not in hass.config.components:
        return
    from homeassistant.components import panel_custom
    from homeassistant.components.http import StaticPathConfig

    if not hass.data.get(_STATIC_KEY):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[_STATIC_KEY] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="Batteri-beregner",
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL}/panel.js?v={VERSION}",
        require_admin=False,
    )
    hass.data[_PANEL_KEY] = True


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the panel when the last entry is gone.

    The static path stays registered: Home Assistant cannot remove one, and
    registering it twice fails, so a later setup reuses it.
    """
    if not hass.data.get(_PANEL_KEY):
        return
    from homeassistant.components import frontend

    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    hass.data[_PANEL_KEY] = False


# ---------- settings that can be changed from the panel ----------


def editable_groups() -> list[tuple[str, dict[str, selector.NumberSelector]]]:
    """The number fields of the setup pages, by page.

    The statistics are left out: they are picked once in the setup. The
    limits and units come from the same selectors the setup uses.
    """
    groups: list[tuple[str, dict[str, selector.NumberSelector]]] = []
    for step, schema in (
        ("battery", battery_schema()),
        ("prices", prices_schema()),
        ("costs", costs_schema()),
    ):
        fields = {
            str(key): value
            for key, value in schema.schema.items()
            if isinstance(value, selector.NumberSelector)
        }
        groups.append((step, fields))
    return groups


def _editable_fields() -> dict[str, selector.NumberSelector]:
    return {
        key: field for _, fields in editable_groups() for key, field in fields.items()
    }


def _entry(hass: HomeAssistant, entry_id: str):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        return None
    return entry


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SETTINGS,
        vol.Optional("language"): str,
    }
)
@websocket_api.async_response
async def ws_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the fields the panel can change, with labels in the user's language."""
    language = msg.get("language") or hass.config.language
    texts = await async_get_translations(hass, language, "config", [DOMAIN])
    prefix = f"component.{DOMAIN}.config"
    entries: dict[str, Any] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        values = {**DEFAULTS, **entry.data, **entry.options}
        groups = []
        for step, fields in editable_groups():
            groups.append(
                {
                    "key": step,
                    "title": texts.get(f"{prefix}.step.{step}.title", step),
                    "fields": [
                        {
                            "key": key,
                            "label": texts.get(f"{prefix}.step.{step}.data.{key}", key),
                            "description": texts.get(
                                f"{prefix}.step.{step}.data_description.{key}", ""
                            ),
                            "min": field.config.get("min"),
                            "max": field.config.get("max"),
                            "step": field.config.get("step"),
                            "unit": field.config.get("unit_of_measurement"),
                            "value": values.get(key),
                        }
                        for key, field in fields.items()
                    ],
                }
            )
        entries[entry.entry_id] = {"groups": groups}
    errors = {
        key.rsplit(".", 1)[-1]: text
        for key, text in texts.items()
        if key.startswith(f"{prefix}.error.")
    }
    connection.send_result(
        msg["id"],
        {
            "entries": entries,
            "errors": errors,
            "can_edit": bool(connection.user and connection.user.is_admin),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_UPDATE_SETTINGS,
        vol.Required("entry_id"): str,
        vol.Required("values"): dict,
    }
)
@websocket_api.require_admin
@callback
def ws_update_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Save new values and calculate again (the entry reloads)."""
    entry = _entry(hass, msg["entry_id"])
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Unknown entry")
        return
    fields = _editable_fields()
    values: dict[str, Any] = {}
    for key, value in msg["values"].items():
        field = fields.get(key)
        if field is None:
            connection.send_error(msg["id"], "invalid_format", f"Cannot change {key}")
            return
        try:
            values[key] = field(value)
        except vol.Invalid as err:
            connection.send_error(msg["id"], "out_of_range", f"{key}: {err}")
            return
    options = {**entry.data, **entry.options, **values}
    try:
        Settings.from_mapping(options).validate()
    except SettingsError as err:
        connection.send_error(msg["id"], "invalid_settings", err.key)
        return
    changed = hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"], {"changed": changed})
