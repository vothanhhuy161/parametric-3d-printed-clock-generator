"""Mechanical and print-envelope validation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

from config_handler import ClockConfig, ConfigurationError


class ConstraintError(ValueError):
    """Raised when the selected parameters violate a hard constraint."""


@dataclass(frozen=True)
class ValidationReport:
    """Validated configuration diagnostics and estimated drive power."""

    warnings: tuple[str, ...]
    available_power_uw: float
    estimated_required_power_uw: float
    pendulum_period_s: float


def validate_config(config: ClockConfig) -> ValidationReport:
    """Validate dimensions, supported features, and estimated power reserve."""
    try:
        runtime_hours = config.runtime_hours
        period_s = config.pendulum_period_s
        pendulum_length_m = config.effective_pendulum_length_m
    except ConfigurationError as exc:
        raise ConstraintError(str(exc)) from exc

    if not isinstance(config.case_style, str) or config.case_style not in {
        "wall",
        "mantel",
        "round",
    }:
        raise ConstraintError("case_style must be 'wall', 'mantel', or 'round'.")
    if not isinstance(config.escapement, str) or config.escapement not in {
        "grasshopper",
        "deadbeat",
        "brocot",
    }:
        raise ConstraintError(
            "escapement must be 'grasshopper', 'deadbeat', or 'brocot'."
        )
    if not isinstance(config.complications, (list, tuple)) or any(
        not isinstance(item, str) for item in config.complications
    ):
        raise ConstraintError("complications must be an array of string names.")
    supported_complications = {"moon_phase", "day_of_week"}
    unsupported = set(config.complications) - supported_complications
    if unsupported:
        raise ConstraintError(
            "Unsupported complication(s): "
            + ", ".join(sorted(unsupported))
            + ". Supported complications are moon_phase and day_of_week."
        )
    if len(set(config.complications)) != len(config.complications):
        raise ConstraintError("complications must not contain duplicates.")
    if "day_of_week" in config.complications and config.case_style != "round":
        raise ConstraintError(
            "day_of_week requires case_style='round'; the library's day holder "
            "is designed for round clock plates."
        )
    if "moon_phase" in config.complications and config.case_style == "round":
        raise ConstraintError(
            "moon_phase is not supported with case_style='round'; the source "
            "library fails to generate this plate/complication combination."
        )
    if {"moon_phase", "day_of_week"}.issubset(config.complications):
        raise ConstraintError(
            "moon_phase and day_of_week cannot be combined: the source library's "
            "clock examples identify this combination as not yet laid out."
        )

    _positive_dimensions("bed_dimensions_mm", config.bed_dimensions_mm)
    _positive_dimensions("case_dimensions_mm", config.case_dimensions_mm)
    if len(config.bed_dimensions_mm) != 3 or len(config.case_dimensions_mm) != 3:
        raise ConstraintError("Bed and case dimensions must each contain X, Y, Z.")
    if not _is_positive_finite(config.nozzle_size_mm):
        raise ConstraintError("nozzle_size_mm must be positive.")
    if (
        not _is_positive_finite(config.clearance_mm)
        or not 0.1 <= config.clearance_mm <= 0.5
    ):
        raise ConstraintError("clearance_mm must be between 0.1 mm and 0.5 mm.")
    if not _is_positive_finite(config.pendulum_bob_diameter_mm):
        raise ConstraintError("Pendulum bob diameter must be positive.")
    if config.gear_module_mm is not None and not _is_positive_finite(
        config.gear_module_mm
    ):
        raise ConstraintError("gear_module_mm must be positive when specified.")
    if not _is_positive_finite(config.weight_mass_kg) or not _is_positive_finite(
        config.weight_drop_mm
    ):
        raise ConstraintError("weight_mass_kg and weight_drop_mm must be positive.")
    if not _is_positive_finite(config.available_drop_path_mm):
        raise ConstraintError("available_drop_path_mm must be positive.")
    if (
        isinstance(config.estimated_friction_power_uw, bool)
        or not isinstance(config.estimated_friction_power_uw, Real)
        or not _is_finite_real(config.estimated_friction_power_uw)
        or config.estimated_friction_power_uw < 0
    ):
        raise ConstraintError("estimated_friction_power_uw cannot be negative.")
    if config.weight_drop_mm > config.available_drop_path_mm:
        raise ConstraintError(
            f"Selected {config.weight_drop_mm:.0f} mm weight drop exceeds the "
            f"available {config.available_drop_path_mm:.0f} mm drop path."
        )

    case_width, case_height, case_depth = config.case_dimensions_mm
    bob_clearance_mm = 20.0
    pendulum_envelope_mm = pendulum_length_m * 1000 + config.pendulum_bob_diameter_mm
    if pendulum_envelope_mm + bob_clearance_mm > case_height:
        raise ConstraintError(
            f"Pendulum and bob need approximately {pendulum_envelope_mm + bob_clearance_mm:.0f} "
            f"mm of case height; configured height is {case_height:.0f} mm."
        )
    if case_width < 140 or case_depth < 60:
        raise ConstraintError("Case width must be at least 140 mm and depth at least 60 mm.")
    dial_diameter_mm = (
        160.0 if config.case_style == "mantel"
        else 180.0 if config.case_style == "round"
        else 120.0
    )
    if case_width < dial_diameter_mm + 20:
        raise ConstraintError(
            f"The selected dial needs at least {dial_diameter_mm + 20:.0f} mm of case width."
        )
    if config.bed_dimensions_mm[2] <= 0:
        raise ConstraintError("Printer Z dimension must be positive.")

    runtime_s = runtime_hours * 3600.0
    try:
        available_power_uw = (
            config.weight_mass_kg
            * 9.80665
            * (config.weight_drop_mm / 1000.0)
            / runtime_s
            * 1_000_000.0
        )
        complication_load_uw = 5.0 * len(config.complications)
        required_power_uw = (
            config.estimated_friction_power_uw + complication_load_uw
        )
    except OverflowError as exc:
        raise ConstraintError(
            "The configured power values exceed the supported numeric range."
        ) from exc
    if not _is_finite_real(available_power_uw) or not _is_finite_real(
        required_power_uw
    ):
        raise ConstraintError(
            "The configured power values produce a non-finite estimate."
        )
    if available_power_uw < required_power_uw:
        raise ConstraintError(
            f"Estimated drive power is {available_power_uw:.1f} uW, below the "
            f"configured load estimate of {required_power_uw:.1f} uW. Increase "
            "weight/drop or reduce runtime/friction."
        )

    warnings: list[str] = []
    if available_power_uw < required_power_uw * 1.25:
        warnings.append(
            "Estimated drive-power margin is below 25%; actual friction and "
            "complication loads must be measured on the assembled clock."
        )
    if config.run_duration.lower() == "8day":
        warnings.append(
            "Eight-day cord/barrel runtime and winding capacity must be confirmed "
            "against the generated train and the actual cord; the power check is "
            "an estimate, not a substitute for a running test."
        )
    warnings.append(
        "Clearances and power-loss values are estimates; printed fit and torque "
        "must be verified with the selected filament and assembled clock."
    )
    warnings.append(
        "clearance_mm is recorded for manufacturing guidance; the local clock "
        "library controls its own geometry tolerances."
    )

    return ValidationReport(
        warnings=tuple(warnings),
        available_power_uw=available_power_uw,
        estimated_required_power_uw=required_power_uw,
        pendulum_period_s=period_s,
    )


def _positive_dimensions(name: str, dimensions: tuple[float, ...]) -> None:
    if not isinstance(dimensions, (list, tuple)) or len(dimensions) != 3 or any(
        not _is_positive_finite(value) for value in dimensions
    ):
        raise ConstraintError(f"{name} must contain three positive finite values.")


def _is_positive_finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, Real)
        and _is_finite_real(value)
        and value > 0
    )


def _is_finite_real(value: Real) -> bool:
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False
