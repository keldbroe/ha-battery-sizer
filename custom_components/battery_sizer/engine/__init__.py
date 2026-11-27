"""Battery sizing engine, free of Home Assistant imports.

It is shared by the Home Assistant integration and the add-on.
"""

from .economics import Costs, Economics, evaluate
from .models import Battery, Hour, HourResult, SimulationResult, Strategy, Totals
from .simulate import simulate
from .sizing import (
    ExpansionOption,
    ExpansionRecommendation,
    Recommendation,
    SizeResult,
    default_sizes,
    recommend,
    recommend_expansion,
)

__all__ = [
    "Battery",
    "Costs",
    "Economics",
    "ExpansionOption",
    "ExpansionRecommendation",
    "Hour",
    "HourResult",
    "Recommendation",
    "SimulationResult",
    "SizeResult",
    "Strategy",
    "Totals",
    "default_sizes",
    "evaluate",
    "recommend",
    "recommend_expansion",
    "simulate",
]
