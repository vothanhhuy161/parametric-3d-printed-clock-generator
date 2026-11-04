"""Compare user pendulum targets with values achieved by the selected gear train."""

from __future__ import annotations

from dataclasses import dataclass
import math

from config_handler import ClockConfig
from gear_solver import GearSolution


# Developer-maintained policy constant; intentionally excluded from user settings.
MAX_DESIGN_DEVIATION_PERCENT = 5.0


@dataclass(frozen=True)
class DesignComparison:
    """A user target and the corresponding value calculated from the gear train."""

    parameter: str
    target_value: float
    calculated_value: float
    unit: str
    deviation_percent: float

    @property
    def within_tolerance(self) -> bool:
        """Return whether the calculated design is within the allowed deviation."""
        return self.deviation_percent <= MAX_DESIGN_DEVIATION_PERCENT or math.isclose(
            self.deviation_percent,
            MAX_DESIGN_DEVIATION_PERCENT,
            rel_tol=0.0,
            abs_tol=1e-9,
        )

    def to_dict(self) -> dict[str, float | str]:
        """Return a JSON-compatible comparison record."""
        return {
            "parameter": self.parameter,
            "user_target": self.target_value,
            "calculated_value": self.calculated_value,
            "unit": self.unit,
            "deviation_percent": self.deviation_percent,
            "maximum_deviation_percent": MAX_DESIGN_DEVIATION_PERCENT,
        }


def compare_pendulum_target(
    config: ClockConfig,
    solution: GearSolution,
) -> DesignComparison:
    """Compare the selected train's achieved value with the user's active target."""
    if config.target_beat_rate_bpm is not None:
        parameter = "Pendulum beat rate"
        target_value = config.target_beat_rate_bpm
        calculated_value = solution.calculated_beat_rate_bpm
        unit = "beats/min"
    else:
        parameter = "Pendulum length"
        target_value = config.effective_pendulum_length_m
        calculated_value = solution.calculated_pendulum_length_m
        unit = "m"

    deviation_percent = abs(calculated_value - target_value) / target_value * 100.0
    return DesignComparison(
        parameter=parameter,
        target_value=target_value,
        calculated_value=calculated_value,
        unit=unit,
        deviation_percent=deviation_percent,
    )


def format_design_comparison(comparison: DesignComparison) -> str:
    """Format the design comparison as a compact console table."""
    parameter_width = max(len("Parameter"), len(comparison.parameter))
    target = f"{comparison.target_value:.6g} {comparison.unit}"
    calculated = f"{comparison.calculated_value:.6g} {comparison.unit}"
    target_width = max(len("User target"), len(target))
    calculated_width = max(len("Calculated"), len(calculated))
    deviation = f"{comparison.deviation_percent:.3f}%"
    deviation_width = max(len("Deviation"), len(deviation))
    separator = (
        f"+-{'-' * parameter_width}-+-{'-' * target_width}"
        f"-+-{'-' * calculated_width}-+-{'-' * deviation_width}-+"
    )
    header = (
        f"| {'Parameter':<{parameter_width}} | {'User target':>{target_width}} "
        f"| {'Calculated':>{calculated_width}} | {'Deviation':>{deviation_width}} |"
    )
    row = (
        f"| {comparison.parameter:<{parameter_width}} | {target:>{target_width}} "
        f"| {calculated:>{calculated_width}} | {deviation:>{deviation_width}} |"
    )
    return "\n".join((separator, header, separator, row, separator))
