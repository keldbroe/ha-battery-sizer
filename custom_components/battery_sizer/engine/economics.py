"""Investment, lifetime, payback and net present value for one battery size."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Costs:
    """What a battery costs and how long it lasts.

    ``price_per_kwh`` is the price of one more kWh of battery: the price per
    kWh of battery modules. ``fixed_cost`` is what a new system costs on top
    of its battery (hybrid inverter, installation); use ``from_system_price``
    to derive it from a quoted price. ``expansion_cost`` is paid once when an
    existing battery is extended (fitting the extra modules). The battery
    lasts ``lifetime_years`` or ``cycle_life`` full cycles, whichever comes
    first. ``discount_rate`` discounts future savings.
    """

    price_per_kwh: float = 3000.0
    fixed_cost: float = 0.0
    expansion_cost: float = 0.0
    lifetime_years: float = 15.0
    cycle_life: float = 6000.0
    discount_rate: float = 0.03

    def __post_init__(self) -> None:
        """Reject values that make the result meaningless."""
        if min(self.price_per_kwh, self.fixed_cost, self.expansion_cost) < 0:
            raise ValueError("prices must not be negative")
        if self.lifetime_years <= 0 or self.cycle_life <= 0:
            raise ValueError("lifetime_years and cycle_life must be positive")
        if self.discount_rate <= -1:
            raise ValueError("discount_rate must be above -100 %")

    @classmethod
    def from_system_price(
        cls,
        system_price: float,
        included_kwh: float,
        price_per_kwh: float,
        **kwargs: float,
    ) -> Costs:
        """Build costs from a quote for a complete system and a module price.

        A system quoted at ``system_price`` with ``included_kwh`` of battery
        costs ``system_price - included_kwh * price_per_kwh`` on top of its
        battery. Every other size then costs that plus its capacity times
        ``price_per_kwh``.
        """
        fixed = system_price - included_kwh * price_per_kwh
        if fixed < -1e-6:
            raise ValueError(
                "The system price is lower than its battery at the price per "
                "kWh; check the system price, its battery size or the price "
                "per kWh"
            )
        return cls(price_per_kwh=price_per_kwh, fixed_cost=max(fixed, 0.0), **kwargs)

    def system_investment(self, capacity_kwh: float) -> float:
        """Return what a new system with ``capacity_kwh`` costs."""
        if capacity_kwh <= 0:
            return 0.0
        return self.fixed_cost + capacity_kwh * self.price_per_kwh

    def expansion_investment(self, added_kwh: float) -> float:
        """Return what adding ``added_kwh`` to an existing battery costs."""
        if added_kwh <= 0:
            return 0.0
        return self.expansion_cost + added_kwh * self.price_per_kwh

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
    *,
    investment: float | None = None,
) -> Economics:
    """Evaluate one battery size from its simulated yearly savings.

    ``investment`` defaults to a new system of ``capacity_kwh``. For an
    expansion, pass the expansion's own investment and its extra savings.
    """
    if investment is None:
        investment = costs.system_investment(capacity_kwh)
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
