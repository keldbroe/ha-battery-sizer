"""Batteri-beregner (DK): recommended home battery size from your own data."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SERVICE_CALCULATE
from .coordinator import BatterySizerCoordinator
from .panel import async_register_panel, async_register_websocket, async_remove_panel

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the calculate action. Configuration is done in the UI."""

    async def _async_calculate(call: ServiceCall) -> None:
        del call
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise HomeAssistantError("Batteri-beregner is not set up")
        for entry in entries:
            coordinator: BatterySizerCoordinator = entry.runtime_data
            await coordinator.async_refresh()
            if not coordinator.last_update_success:
                raise HomeAssistantError(
                    f"The calculation failed: {coordinator.last_exception}"
                )

    hass.services.async_register(DOMAIN, SERVICE_CALCULATE, _async_calculate)
    async_register_websocket(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the sensors and calculate in the background.

    The calculation reads years of history and takes a few seconds, so it
    does not hold up Home Assistant's start; the sensors fill in when done.
    """
    coordinator = BatterySizerCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await async_register_panel(hass)
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN}_first_calculation"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the sensors and the button; the panel goes with the last entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
    ]
    if unloaded and not others:
        async_remove_panel(hass)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Calculate again with the new values."""
    await hass.config_entries.async_reload(entry.entry_id)
