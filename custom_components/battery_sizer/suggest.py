"""Suggest statistics from Home Assistant's Energy dashboard.

Most homes already told the Energy dashboard which meters count bought and
sold energy and solar production, and often which sensors hold the prices.
Those are offered first in the setup, so few have to search the lists.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_BUY_PRICE,
    CONF_EXPORT,
    CONF_IMPORT,
    CONF_SELL_PRICE,
    CONF_SOLAR,
    CONF_SOURCE,
    SOURCE_GRID,
    SOURCE_INVERTER,
)

_LOGGER = logging.getLogger(__name__)


async def async_energy_preferences(hass: HomeAssistant) -> dict[str, Any] | None:
    """Return the Energy dashboard's settings, or None if it is not set up."""
    try:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
    except Exception:  # the dashboard is optional; never block the setup
        _LOGGER.debug("Energy dashboard settings could not be read", exc_info=True)
        return None
    return manager.data


def suggestions_from_preferences(preferences: dict[str, Any] | None) -> dict[str, str]:
    """Map the Energy dashboard's meters and prices onto this setup's fields.

    The first grid meter and the first solar source are used. A home with a
    battery already gets the inverter as source: its grid meter shows what
    the battery does, not what the house needs.
    """
    found: dict[str, str] = {}

    def keep(key: str, value: Any) -> None:
        if isinstance(value, str) and value and key not in found:
            found[key] = value

    has_battery = False
    for source in (preferences or {}).get("energy_sources") or []:
        kind = source.get("type")
        if kind == "grid":
            keep(CONF_IMPORT, source.get("stat_energy_from"))
            keep(CONF_EXPORT, source.get("stat_energy_to"))
            for flow in source.get("flow_from") or []:
                keep(CONF_IMPORT, flow.get("stat_energy_from"))
                keep(CONF_BUY_PRICE, flow.get("entity_energy_price"))
            for flow in source.get("flow_to") or []:
                keep(CONF_EXPORT, flow.get("stat_energy_to"))
                keep(CONF_SELL_PRICE, flow.get("entity_energy_price"))
        elif kind == "solar":
            keep(CONF_SOLAR, source.get("stat_energy_from"))
        elif kind == "battery":
            has_battery = True
    if found:
        found[CONF_SOURCE] = SOURCE_INVERTER if has_battery else SOURCE_GRID
    return found


async def async_suggestions(hass: HomeAssistant) -> dict[str, str]:
    """Suggested values for the setup, from the Energy dashboard."""
    return suggestions_from_preferences(await async_energy_preferences(hass))
