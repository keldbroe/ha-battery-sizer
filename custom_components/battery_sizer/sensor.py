"""Sensors with the recommended battery size per strategy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, VERSION
from .coordinator import BatterySizerCoordinator, CalculationResult, Outcome
from .engine import Strategy

CURRENCY = "DKK"


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the one service device that holds all entities of an entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or NAME,
        manufacturer="Batteri-beregner",
        model="Battery sizing",
        sw_version=VERSION,
        entry_type=DeviceEntryType.SERVICE,
    )


@dataclass(frozen=True, kw_only=True)
class OutcomeDescription(SensorEntityDescription):
    """A sensor that reads one number from a strategy's outcome."""

    value: Callable[[Outcome], float | None]
    with_table: bool = False


def _metric_descriptions(
    strategy: Strategy, expansion: bool
) -> list[OutcomeDescription]:
    size_key = "recommended_expansion" if expansion else "recommended_size"
    return [
        OutcomeDescription(
            key=f"{strategy}_{size_key}",
            translation_key=f"{strategy}_{size_key}",
            device_class=SensorDeviceClass.ENERGY_STORAGE,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=1,
            value=lambda o: o.recommended_kwh,
            with_table=True,
        ),
        OutcomeDescription(
            key=f"{strategy}_annual_savings",
            translation_key=f"{strategy}_annual_savings",
            device_class=SensorDeviceClass.MONETARY,
            native_unit_of_measurement=CURRENCY,
            suggested_display_precision=0,
            value=lambda o: o.annual_savings,
        ),
        OutcomeDescription(
            key=f"{strategy}_payback",
            translation_key=f"{strategy}_payback",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.YEARS,
            suggested_display_precision=1,
            value=lambda o: o.payback_years,
        ),
        OutcomeDescription(
            key=f"{strategy}_net_present_value",
            translation_key=f"{strategy}_net_present_value",
            device_class=SensorDeviceClass.MONETARY,
            native_unit_of_measurement=CURRENCY,
            suggested_display_precision=0,
            value=lambda o: o.net_present_value,
        ),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add four sensors per strategy and one status sensor."""
    coordinator: BatterySizerCoordinator = entry.runtime_data
    expansion = coordinator.settings.is_expansion
    entities: list[SensorEntity] = [CalculationStatusSensor(coordinator, entry)]
    for strategy in Strategy:
        entities.extend(
            OutcomeSensor(coordinator, entry, strategy, description)
            for description in _metric_descriptions(strategy, expansion)
        )
    async_add_entities(entities)


class _Base(CoordinatorEntity[BatterySizerCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatterySizerCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(entry)

    @property
    def _result(self) -> CalculationResult | None:
        return self.coordinator.data


class OutcomeSensor(_Base):
    """One number from one strategy's recommendation."""

    entity_description: OutcomeDescription

    def __init__(
        self,
        coordinator: BatterySizerCoordinator,
        entry: ConfigEntry,
        strategy: Strategy,
        description: OutcomeDescription,
    ) -> None:
        """Bind the sensor to a strategy and a metric."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._strategy = strategy

    @property
    def available(self) -> bool:
        """Show the last result even if a later run failed."""
        return self._outcome is not None

    @property
    def _outcome(self) -> Outcome | None:
        result = self._result
        return result.outcomes.get(self._strategy) if result else None

    @property
    def native_value(self) -> float | None:
        """Return the metric, or unknown when no size pays off."""
        outcome = self._outcome
        if outcome is None:
            return None
        return self.entity_description.value(outcome)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """On the size sensor: every size tried, for charts and comparison."""
        outcome = self._outcome
        if outcome is None or not self.entity_description.with_table:
            return None
        attributes: dict[str, Any] = {
            "strategy": str(self._strategy),
            "expansion": outcome.expansion,
            "pays_off": outcome.recommended_kwh > 0,
            "investment": outcome.investment,
            "cycles_per_year": outcome.cycles_per_year,
            "sizes": outcome.table,
        }
        result = self._result
        if outcome.expansion and result is not None:
            attributes["existing_kwh"] = result.existing_kwh
            attributes["existing_annual_savings"] = round(
                result.existing_annual_savings.get(self._strategy, 0.0)
            )
        return attributes


class CalculationStatusSensor(_Base):
    """When the calculation ran, and on how much data."""

    _attr_translation_key = "last_calculation"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: BatterySizerCoordinator, entry: ConfigEntry
    ) -> None:
        """Bind the status sensor to the entry."""
        super().__init__(coordinator, entry, "last_calculation")

    @property
    def available(self) -> bool:
        """Always available, so a failure can be read from its attributes."""
        return True

    @property
    def native_value(self):
        """Return when the last successful calculation finished."""
        result = self._result
        return result.calculated_at if result else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the period used and the last error, if any."""
        result = self._result
        attributes: dict[str, Any] = {
            "last_run_succeeded": self.coordinator.last_update_success,
            "error": str(self.coordinator.last_exception)
            if not self.coordinator.last_update_success
            and self.coordinator.last_exception
            else None,
        }
        if result is not None:
            attributes.update(
                {
                    "hours_used": result.hours,
                    "first_hour": result.first.isoformat() if result.first else None,
                    "last_hour": result.last.isoformat() if result.last else None,
                    "months_covered": result.months_covered,
                }
            )
        return attributes
