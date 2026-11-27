"""A sidebar panel with charts, and the websocket command that feeds it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, NAME, VERSION
from .coordinator import BatterySizerCoordinator, CalculationResult
from .engine import Strategy
from .settings import SettingsError

PANEL_URL_PATH = "battery-sizer"
PANEL_COMPONENT = "battery-sizer-panel"
PANEL_ICON = "mdi:battery-charging-high"
STATIC_URL = f"/{DOMAIN}_static"
FRONTEND_DIR = Path(__file__).parent / "frontend"
WS_RESULTS = f"{DOMAIN}/results"

_PANEL_KEY = f"{DOMAIN}_panel"
_STATIC_KEY = f"{DOMAIN}_static_path"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the command that returns every entry's result."""
    websocket_api.async_register_command(hass, ws_results)


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
