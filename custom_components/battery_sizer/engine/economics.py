"""Investment, lifetime, payback and net present value for one battery size."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Costs:
    """What a battery costs and how long it lasts.

    ``price_per_kwh`` is the installed price per kWh of capacity (battery,
    not the inverter). ``fixed_cost`` is paid once whatever the size, for
    example installation or a hybrid inverter you would not buy otherwise.
    The battery lasts ``lifetime_years`` or ``cycle_life`` full cycles,
    whichever comes first. ``discount_rate`` discounts future savings.
    """

    price_per_kwh: float = 3000.0
    fixed_cost: float = 0.0
    lifetime_years: float = 15.0
    cycle_life: float = 6000.0
    discount_rate: float = 0.03

    def __post_init__(self) -> None:
        """Reject values that make the result meaningless."""
        if self.price_per_kwh < 0 or self.fixed_cost < 0:
            raise ValueError("prices must not be negative")
        if self.lifetime_years <= 0 or self.cycle_life <= 0:
            raise ValueError("lifetime_years and cycle_life must be positive")
        if self.discount_rate <= -1:
            raise ValueError("discount_rate must be above -100 %")

    def wear_cost_per_kwh(self, round_trip_efficiency: float) -> float:
        """Return the battery wear per kWh delivered, from price and cycle life.

        One full cycle delivers the usable capacity times the efficiency, so
        a 6000-cycle battery at 3000 kr/kWh wears about 0.56 kr per kWh
        delivered at 90 % efficiency. Using this in the simulation keeps the
        battery from cycling for a smaller gain than it costs in wear.
        """
        return self.price_per_kwh / (self.cycle_life * round_trip_efficiency)


@dataclass(frozen=True, slots=True)
class Economics:
    """The money side of one battery size."""

    capacity_kwh: float
    investment: float
    annual_savings: float
    annual_cycles: float
    lifetime_years: float
    net_present_value: float
    payback_years: float | None

    @property
    def pays_off(self) -> bool:
        """Return whether the battery earns more than it costs."""
        return self.net_present_value > 0


def evaluate(
    capacity_kwh: float,
    annual_savings: float,
    annual_cycles: float,
    costs: Costs,
) -> Economics:
    """Evaluate one battery size from its simulated yearly savings."""
    investment = (
        capacity_kwh * costs.price_per_kwh + costs.fixed_cost
        if capacity_kwh > 0
        else 0.0
    )
    life = costs.lifetime_years
    if annual_cycles > 0:
        life = min(life, costs.cycle_life / annual_cycles)
    present = _annuity(annual_savings, costs.discount_rate, life)
    payback = None
    if annual_savings > 0 and investment / annual_savings <= life:
        payback = investment / annual_savings
    return Economics(
        capacity_kwh=capacity_kwh,
        investment=investment,
        annual_savings=annual_savings,
        annual_cycles=annual_cycles,
        lifetime_years=life,
        net_present_value=present - investment,
        payback_years=payback,
    )


def _annuity(amount: float, rate: float, years: float) -> float:
    """Present value of ``amount`` a year for ``years`` (fractions allowed)."""
    if years <= 0:
        return 0.0
    if abs(rate) < 1e-12:
        return amount * years
    return amount * (1 - (1 + rate) ** -years) / rate
