"""The values the user typed in, turned into engine objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
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
    DEFAULTS,
    SOURCE_GRID,
    SOURCE_INVERTER,
)
from .engine import Battery, Costs, default_sizes


class SettingsError(ValueError):
    """A value the user typed in cannot be used; ``key`` is the error key."""

    def __init__(self, key: str) -> None:
        """Remember which translated error to show."""
        super().__init__(key)
        self.key = key


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything one calculation needs."""

    source: str
    import_statistic: str | None
    export_statistic: str | None
    load_statistic: str | None
    solar_statistic: str | None
    buy_price_statistic: str
    sell_price_statistic: str
    sell_deduction: float
    existing_kwh: float
    power_kw: float
    usable_pct: float
    efficiency_pct: float
    grid_limit_kw: float
    battery_price: float
    system_price: float
    system_kwh: float
    expansion_cost: float
    lifetime_years: float
    cycle_life: float
    discount_pct: float
    max_kwh: float
    step_kwh: float
    history_years: float

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> Settings:
        """Build settings from config entry data and options."""

        def number(key: str) -> float:
            raw = values.get(key, DEFAULTS[key])
            try:
                return float(raw)
            except (TypeError, ValueError):
                return float(DEFAULTS[key])

        def text(key: str) -> str | None:
            raw = values.get(key)
            return str(raw) if raw else None

        return cls(
            source=str(values.get(CONF_SOURCE) or SOURCE_GRID),
            import_statistic=text(CONF_IMPORT),
            export_statistic=text(CONF_EXPORT),
            load_statistic=text(CONF_LOAD),
            solar_statistic=text(CONF_SOLAR),
            buy_price_statistic=str(values.get(CONF_BUY_PRICE) or ""),
            sell_price_statistic=str(values.get(CONF_SELL_PRICE) or ""),
            sell_deduction=number(CONF_SELL_DEDUCTION),
            existing_kwh=number(CONF_EXISTING_KWH),
            power_kw=number(CONF_POWER_KW),
            usable_pct=number(CONF_USABLE_PCT),
            efficiency_pct=number(CONF_EFFICIENCY_PCT),
            grid_limit_kw=number(CONF_GRID_LIMIT_KW),
            battery_price=number(CONF_BATTERY_PRICE),
            system_price=number(CONF_SYSTEM_PRICE),
            system_kwh=number(CONF_SYSTEM_KWH),
            expansion_cost=number(CONF_EXPANSION_COST),
            lifetime_years=number(CONF_LIFETIME_YEARS),
            cycle_life=number(CONF_CYCLE_LIFE),
            discount_pct=number(CONF_DISCOUNT_PCT),
            max_kwh=number(CONF_MAX_KWH),
            step_kwh=number(CONF_STEP_KWH),
            history_years=number(CONF_HISTORY_YEARS),
        )

    @property
    def is_expansion(self) -> bool:
        """Return whether the home already has a battery to extend."""
        return self.existing_kwh > 0

    @property
    def energy_statistics(self) -> list[str]:
        """Return the energy statistics this source needs, in a stable order."""
        if self.source == SOURCE_INVERTER:
            wanted = [self.load_statistic, self.solar_statistic]
        else:
            wanted = [self.import_statistic, self.export_statistic]
        return [statistic for statistic in wanted if statistic]

    def battery(self) -> Battery:
        """Return the battery template; the sweep changes only its capacity."""
        try:
            return Battery(
                capacity_kwh=0.0,
                power_kw=self.power_kw,
                usable_fraction=self.usable_pct / 100,
                round_trip_efficiency=self.efficiency_pct / 100,
                grid_limit_kw=self.grid_limit_kw if self.grid_limit_kw > 0 else None,
            )
        except ValueError as err:
            raise SettingsError("invalid_battery") from err

    def costs(self) -> Costs:
        """Return the costs, deriving the fixed part from the system price."""
        common = {
            "expansion_cost": self.expansion_cost,
            "lifetime_years": self.lifetime_years,
            "cycle_life": self.cycle_life,
            "discount_rate": self.discount_pct / 100,
        }
        try:
            return Costs.from_system_price(
                self.system_price, self.system_kwh, self.battery_price, **common
            )
        except ValueError as err:
            if "system price" in str(err):
                raise SettingsError("system_price_too_low") from err
            raise SettingsError("invalid_costs") from err

    def sizes(self) -> list[float]:
        """Return the capacities (or additions) to try."""
        if self.step_kwh <= 0 or self.max_kwh < self.step_kwh:
            raise SettingsError("invalid_sizes")
        return default_sizes(self.max_kwh, self.step_kwh)

    def validate(self) -> None:
        """Raise ``SettingsError`` for the first problem found."""
        if self.source == SOURCE_INVERTER:
            if not self.load_statistic or not self.solar_statistic:
                raise SettingsError("missing_energy")
        elif not self.import_statistic:
            raise SettingsError("missing_energy")
        if not self.buy_price_statistic or not self.sell_price_statistic:
            raise SettingsError("missing_prices")
        if self.existing_kwh < 0:
            raise SettingsError("invalid_battery")
        if self.history_years <= 0:
            raise SettingsError("invalid_sizes")
        self.battery()
        self.costs()
        self.sizes()
