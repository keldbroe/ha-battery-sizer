"""A button that runs the calculation again."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BatterySizerCoordinator
from .sensor import device_info

DESCRIPTION = ButtonEntityDescription(key="calculate", translation_key="calculate")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the recalculate button."""
    async_add_entities([CalculateButton(entry.runtime_data, entry)])


class CalculateButton(CoordinatorEntity[BatterySizerCoordinator], ButtonEntity):
    """Run the calculation now, for example after new prices or data."""

    _attr_has_entity_name = True
    entity_description = DESCRIPTION

    def __init__(
        self, coordinator: BatterySizerCoordinator, entry: ConfigEntry
    ) -> None:
        """Bind the button to the entry's device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calculate"
        self._attr_device_info = device_info(entry)

    @property
    def available(self) -> bool:
        """The button works even when the last calculation failed."""
        return True

    async def async_press(self) -> None:
        """Calculate again."""
        await self.coordinator.async_request_refresh()
