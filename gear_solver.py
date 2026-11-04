"""Adapter between validated configuration and the local 3DPrintedClocks library."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import math
from pathlib import Path
import sys
from typing import Any

from config_handler import ClockConfig
from validator import ValidationReport


@dataclass(frozen=True)
class GearPair:
    """One selected wheel/pinion pair and its nominal center distance."""

    wheel_teeth: int
    pinion_teeth: int
    module_mm: float
    center_distance_mm: float


@dataclass
class GearSolution:
    """Computed gear-train data and its source-library train instance."""

    runtime_hours: float
    pendulum_period_s: float
    pendulum_length_m: float
    calculated_pendulum_period_s: float
    calculated_pendulum_length_m: float
    calculated_beat_rate_bpm: float
    escapement_name: str
    gear_pairs: list[GearPair]
    powered_wheel_ratios: list[tuple[int, int]]
    train: Any


class GearSolver:
    """Create and calculate a going train using the local clock library."""

    def __init__(self, library_path: str | Path):
        self.library_path = Path(library_path).resolve()

    def solve(
        self,
        config: ClockConfig,
        validation: ValidationReport,
    ) -> GearSolution:
        """Run the source library's ratio search and report nominal gear centers."""
        if not self.library_path.is_dir():
            raise FileNotFoundError(
                f"Clock library directory does not exist: {self.library_path}"
            )
        try:
            clock = load_clock_library(self.library_path)
        except ImportError as exc:
            raise RuntimeError(
                f"Unable to import the local clock library from "
                f"'{self.library_path}' with Python '{sys.executable}': {exc}. "
                "Install the project and source-library dependencies into this "
                "same Python environment."
            ) from exc

        escapement = self._make_escapement(clock, config, validation)
        is_eight_day = config.run_duration.lower() == "8day"
        power_wheel = None
        powered_wheels = 0
        wheels = 3
        if is_eight_day:
            power_wheel = clock.CordBarrel(
                diameter=30,
                ratchet_thick=6,
                rod_metric_size=4,
                thick=16,
                use_key=True,
                cord_thick=1.5,
                cord_length=config.weight_drop_mm,
                style=clock.GearStyle.ARCS,
                loose_on_rod=False,
                use_steel_tube=False,
            )
            powered_wheels = 1

        train = clock.GoingTrain(
            pendulum_period=validation.pendulum_period_s,
            wheels=wheels,
            escapement=escapement,
            powered_wheels=powered_wheels,
            runtime_hours=config.runtime_hours,
            max_weight_drop=config.weight_drop_mm,
            powered_wheel=power_wheel,
        )
        try:
            train.calculate_ratios(
                max_wheel_teeth=130,
                min_pinion_teeth=9,
                wheel_min_teeth=60,
                pinion_max_teeth=15,
                max_error=0.1,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                "The local clock library found no train within 0.1 seconds of "
                "the requested pendulum rate. Try a nearby beat rate or review "
                "the gear tooth search limits."
            ) from exc
        if not getattr(train, "trains", None):
            raise RuntimeError("The clock library found no valid going-train ratios.")
        if is_eight_day:
            train.calculate_powered_wheel_ratios()
            if not getattr(train, "chain_wheel_ratios", None):
                raise RuntimeError(
                    "The clock library could not calculate the eight-day barrel ratios."
                )
        else:
            train.gen_cord_wheels(
                ratchet_thick=5,
                cord_thick=1.5,
                cord_coil_thick=11,
            )

        ratios = train.trains[0]["train"]
        total_ratio = math.prod(pair[0] for pair in ratios) / math.prod(
            pair[1] for pair in ratios
        )
        calculated_period = (
            3600.0 / (total_ratio * train.escapement.teeth)
        )
        calculated_length = 9.80665 * (
            calculated_period / (2.0 * math.pi)
        ) ** 2
        pairs: list[GearPair] = []
        module = config.effective_gear_module_mm
        for index, pair in enumerate(ratios):
            wheel_teeth, pinion_teeth = int(pair[0]), int(pair[1])
            pair_module = module * (0.9**index)
            center_distance = pair_module * (wheel_teeth + pinion_teeth) / 2.0
            pairs.append(
                GearPair(
                    wheel_teeth=wheel_teeth,
                    pinion_teeth=pinion_teeth,
                    module_mm=pair_module,
                    center_distance_mm=center_distance,
                )
            )
        return GearSolution(
            runtime_hours=config.runtime_hours,
            pendulum_period_s=validation.pendulum_period_s,
            pendulum_length_m=config.effective_pendulum_length_m,
            calculated_pendulum_period_s=calculated_period,
            calculated_pendulum_length_m=calculated_length,
            calculated_beat_rate_bpm=120.0 / calculated_period,
            escapement_name=config.escapement,
            gear_pairs=pairs,
            powered_wheel_ratios=[
                (int(pair[0]), int(pair[1]))
                for pair in getattr(train, "chain_wheel_ratios", [])
            ],
            train=train,
        )

    @staticmethod
    def _make_escapement(
        clock: Any,
        config: ClockConfig,
        report: ValidationReport,
    ) -> Any:
        if config.escapement == "grasshopper":
            return clock.GrasshopperEscapement.get_harrison_compliant_grasshopper(
                pendulum_length_m=config.effective_pendulum_length_m,
                T=report.pendulum_period_s,
            )
        teeth = max(20, min(120, round(60.0 / report.pendulum_period_s)))
        if config.escapement == "brocot":
            return clock.BrocotEscapment(teeth=teeth)
        return clock.AnchorEscapement.get_with_optimal_pallets(teeth=teeth)


def load_clock_library(library_path: str | Path) -> Any:
    """Load the source library while preserving its NumPy 1.x expectations."""
    root = str(Path(library_path).resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    numpy = importlib.import_module("numpy")
    try:
        importlib.import_module("numpy.linalg.linalg")
    except ModuleNotFoundError as exc:
        if exc.name != "numpy.linalg.linalg":
            raise
        sys.modules["numpy.linalg.linalg"] = numpy.linalg
    cross = numpy.cross
    if not getattr(cross, "_legacy_2d_compatible", False):
        def cross_with_legacy_2d_support(
            first: Any,
            second: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            first_array = numpy.asarray(first)
            second_array = numpy.asarray(second)
            if (
                not args
                and not kwargs
                and first_array.ndim > 0
                and second_array.ndim > 0
                and first_array.shape[-1] == 2
                and second_array.shape[-1] == 2
            ):
                return (
                    first_array[..., 0] * second_array[..., 1]
                    - first_array[..., 1] * second_array[..., 0]
                )
            return cross(first, second, *args, **kwargs)

        cross_with_legacy_2d_support._legacy_2d_compatible = True
        numpy.cross = cross_with_legacy_2d_support
    return importlib.import_module("clocks")
