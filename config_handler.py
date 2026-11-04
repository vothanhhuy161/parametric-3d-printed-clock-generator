"""Configuration models and JSON loading for the clock generator."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """Raised when a user configuration cannot be parsed or validated."""


@dataclass(frozen=True)
class ClockConfig:
    """User-selectable clock, print, and estimated mechanical parameters."""

    run_duration: str = "30h"
    case_style: str = "wall"
    escapement: str = "deadbeat"
    pendulum_length_m: float | None = 0.5
    target_beat_rate_bpm: float | None = None
    complications: list[str] = field(default_factory=list)
    bed_dimensions_mm: tuple[float, float, float] = (220.0, 220.0, 250.0)
    nozzle_size_mm: float = 0.4
    clearance_mm: float = 0.25
    case_dimensions_mm: tuple[float, float, float] = (250.0, 800.0, 160.0)
    pendulum_bob_diameter_mm: float = 80.0
    weight_drop_mm: float = 1800.0
    available_drop_path_mm: float = 2000.0
    weight_mass_kg: float = 2.0
    estimated_friction_power_uw: float = 25.0
    gear_module_mm: float | None = None

    @property
    def runtime_hours(self) -> float:
        """Return the duration represented by the selected preset."""
        if not isinstance(self.run_duration, str):
            raise ConfigurationError("run_duration must be a string preset.")
        durations = {"30h": 30.0, "8day": 8.0 * 24.0}
        try:
            return durations[self.run_duration.lower()]
        except KeyError as exc:
            raise ConfigurationError(
                "run_duration must be either '30h' or '8day'."
            ) from exc

    @property
    def pendulum_period_s(self) -> float:
        """Return the full-swing pendulum period from length or beat rate."""
        if self.target_beat_rate_bpm is not None:
            if (
                not isinstance(self.target_beat_rate_bpm, (int, float))
                or not math.isfinite(self.target_beat_rate_bpm)
                or self.target_beat_rate_bpm <= 0
            ):
                raise ConfigurationError("target_beat_rate_bpm must be positive.")
            return 120.0 / self.target_beat_rate_bpm
        if (
            self.pendulum_length_m is None
            or not isinstance(self.pendulum_length_m, (int, float))
            or not math.isfinite(self.pendulum_length_m)
            or self.pendulum_length_m <= 0
        ):
            raise ConfigurationError(
                "Set a positive pendulum_length_m or target_beat_rate_bpm."
            )
        return 2.0 * 3.141592653589793 * (
            self.pendulum_length_m / 9.80665
        ) ** 0.5

    @property
    def effective_pendulum_length_m(self) -> float:
        """Return pendulum length, deriving it from the beat rate if needed."""
        if self.target_beat_rate_bpm is None and self.pendulum_length_m is not None:
            return self.pendulum_length_m
        period = self.pendulum_period_s
        return 9.80665 * (period / (2.0 * 3.141592653589793)) ** 2

    @property
    def effective_gear_module_mm(self) -> float:
        """Return the requested module or a bed-conscious preset default."""
        if self.gear_module_mm is not None:
            return self.gear_module_mm
        return 0.55 if self.run_duration.lower() == "8day" else 0.8

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ClockConfig:
        """Build a configuration from a JSON-compatible mapping."""
        if not isinstance(data, dict):
            raise ConfigurationError("Configuration data must be a JSON object.")
        allowed = set(cls.__dataclass_fields__)
        unknown = set(data) - allowed
        if unknown:
            raise ConfigurationError(
                f"Unknown configuration option(s): {', '.join(sorted(unknown))}"
            )
        try:
            values = dict(data)
            for key in ("bed_dimensions_mm", "case_dimensions_mm"):
                if key in values:
                    if not isinstance(values[key], (list, tuple)):
                        raise ConfigurationError(
                            f"{key} must be an array of three values."
                        )
                    values[key] = tuple(values[key])
            if "complications" in values:
                if not isinstance(values["complications"], (list, tuple)):
                    raise ConfigurationError("complications must be an array of names.")
                values["complications"] = list(values["complications"])
            config = cls(**values)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid configuration: {exc}") from exc
        config.runtime_hours
        config.pendulum_period_s
        return config

    @classmethod
    def from_json_file(cls, path: str | Path) -> ClockConfig:
        """Load a clock configuration from a JSON file."""
        config_path = Path(path)
        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                data = json.load(config_file)
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to read configuration file '{config_path}': {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"Invalid JSON in '{config_path}' at line {exc.lineno}: {exc.msg}"
            ) from exc
        if not isinstance(data, dict):
            raise ConfigurationError("The configuration JSON root must be an object.")
        return cls.from_mapping(data)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this configuration."""
        result = asdict(self)
        result["bed_dimensions_mm"] = list(self.bed_dimensions_mm)
        result["case_dimensions_mm"] = list(self.case_dimensions_mm)
        return result
