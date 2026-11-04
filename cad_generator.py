"""CadQuery generation through the local 3DPrintedClocks classes."""

from __future__ import annotations

import inspect
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from config_handler import ClockConfig
from gear_solver import GearSolution, load_clock_library


class CadGenerationError(RuntimeError):
    """Raised when a source-library CAD operation fails."""


class CadGenerator:
    """Build clock assemblies and export printable source-library components."""

    def __init__(
        self,
        output_directory: str | Path,
        library_path: str | Path | None = None,
    ):
        self.output_directory = Path(output_directory).expanduser().resolve()
        self.library_path = (
            Path(library_path).resolve()
            if library_path is not None
            else Path(__file__).resolve().parent
            / "3DPrintedClocksGithub"
            / "3DPrintedClocks"
        )
        try:
            self.output_directory.relative_to(self.library_path)
        except ValueError:
            pass
        else:
            raise CadGenerationError(
                "The output directory cannot be inside the clock library directory."
            )

    def generate(self, config: ClockConfig, solution: GearSolution) -> list[Path]:
        """Generate clock components in a temporary raw-STL directory."""
        try:
            import cadquery as cq

            _install_cadquery_text_compatibility(cq)
            clock = load_clock_library(self.library_path)
        except ImportError as exc:
            raise CadGenerationError(
                "CadQuery or the local clock library could not be imported. "
                "Install requirements and use the configured local library."
            ) from exc

        raw_directory = (
            self.output_directory / "raw_parts" / f"run_{uuid4().hex[:8]}"
        )
        raw_directory.mkdir(parents=True, exist_ok=True)
        train = solution.train
        try:
            train.gen_gears(
                module_size=config.effective_gear_module_mm,
                module_reduction=0.9,
                thick=3,
                powered_wheel_thick=6,
            )
            day_of_week = None
            if "day_of_week" in config.complications:
                day_of_week = clock.DayOfWeekComplication(
                    module=0.65,
                    style=clock.GearStyle.ARCS,
                    bevel_module=0.9,
                    angle_deg=-45,
                    extra_z_height=6,
                    cylinder_length=11,
                    shortened_days=True,
                    text_on_plaques=True,
                    geneva_scale=0.7 / 0.65,
                )
            dial = clock.Dial(
                (
                    160
                    if config.case_style == "mantel"
                    else 180
                    if config.case_style == "round"
                    else 120
                ),
                days_complication=day_of_week,
            )
            moon = None
            if "moon_phase" in config.complications:
                moon = clock.MoonPhaseComplication3D(
                    gear_style=clock.GearStyle.ARCS,
                    module=0.9,
                    moon_inside_dial=config.case_style == "mantel",
                )
            motion_works = clock.MotionWorks(
                extra_height=20 if moon or day_of_week else 10,
                style=clock.GearStyle.ARCS,
                drives_complication=moon or day_of_week,
            )
            if moon is not None or day_of_week is not None:
                motion_works.calculate_size(arbor_distance=30)
            if moon is not None:
                moon.set_motion_works_sizes(motion_works)
            if day_of_week is not None:
                day_of_week.set_motion_works_sizes(motion_works)
            pendulum = clock.Pendulum(
                bob_d=config.pendulum_bob_diameter_mm,
                bob_thick=10,
                hand_avoider_inner_d=100,
            )
            plate_arguments: dict[str, Any] = {
                "dial": dial,
                "moon_complication": moon,
                "name": "Generated clock",
                "pendulum_sticks_out": 20,
            }
            if day_of_week is not None:
                plate_arguments["days_complication"] = day_of_week
            if config.case_style == "round":
                plates = clock.RoundClockPlates(
                    train,
                    motion_works,
                    gear_train_layout=clock.GearTrainLayout.COMPACT,
                    leg_height=0,
                    fully_round=True,
                    second_hand=False,
                    **plate_arguments,
                )
            elif config.case_style == "mantel":
                plates = clock.MantelClockPlates(
                    train,
                    motion_works,
                    **plate_arguments,
                )
            else:
                plates = clock.SimpleWallClockPlates(
                    train,
                    motion_works,
                    gear_train_layout=clock.GearTrainLayout.VERTICAL,
                    plate_thick=8,
                    back_plate_thick=8,
                    **plate_arguments,
                )
            hands = clock.Hands(
                style=clock.HandStyle.SIMPLE_ROUND,
                minute_fixing="square",
                minute_fixing_d1=motion_works.get_minute_hand_square_size(),
                hourfixing_d=motion_works.get_hour_hand_hole_d(),
                length=dial.outside_d * 0.42,
                thick=motion_works.minute_hand_slot_height,
                include_seconds_hand=False,
            )
            weight = clock.Weight(height=100, diameter=38)
            assembly = clock.Assembly(
                plates,
                hands=hands,
                weights=[weight],
                pendulum=pendulum,
                name="generated_clock",
            )
            exported: list[Path] = []
            self._export_library_parts(
                [
                    ("plates", plates),
                    ("motion_works", motion_works),
                    ("hands", hands),
                    ("pendulum", pendulum),
                    ("weight", weight),
                ],
                raw_directory,
                exported,
            )
            if day_of_week is not None:
                day_directory = raw_directory / "day_complication"
                day_directory.mkdir(parents=True, exist_ok=True)
                for part_name, shape in day_of_week.get_parts_in_situ().items():
                    safe_part_name = self._validate_part_name(part_name)
                    target = day_directory / f"{safe_part_name}.stl"
                    cq.exporters.export(shape, str(target))
                    exported.append(target)
                holder_path = day_directory / "day_holder.stl"
                cq.exporters.export(
                    plates.days_complication_holder.get_holder(),
                    str(holder_path),
                )
                exported.append(holder_path)
            for index, arbor in enumerate(getattr(plates, "arbors_for_plate", []), 1):
                shape = arbor.get_assembled(with_extras=False)
                arbor_directory = raw_directory / "gear_arbors"
                arbor_directory.mkdir(parents=True, exist_ok=True)
                target = arbor_directory / f"gear_arbor_{index:02d}.stl"
                cq.exporters.export(shape, str(target))
                exported.append(target)
            step_path = raw_directory / "generated_clock.step"
            cq.exporters.export(assembly.get_clock(), str(step_path))
            exported.append(step_path)
            if not exported:
                raise CadGenerationError(
                    "The clock library completed generation but exported no printable parts."
                )
            return exported
        except CadGenerationError:
            raise
        except Exception as exc:
            raise CadGenerationError(
                f"Clock CAD generation failed: {type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _export_library_parts(
        components: list[tuple[str, Any]],
        output_directory: Path,
        exported: list[Path],
    ) -> None:
        for label, component in components:
            output_method = getattr(component, "output_STLs", None)
            if output_method is None:
                raise CadGenerationError(
                    f"The local clock library does not expose STL export for {label}."
                )
            component_directory = output_directory / label
            component_directory.mkdir(parents=True, exist_ok=True)
            output_method(name=f"clock_{label}", path=str(component_directory))
            exported.extend(
                path
                for path in component_directory.glob("*.stl")
                if re.match(rf"clock_{re.escape(label)}(?:_|\.|$)", path.name)
            )

    @staticmethod
    def _validate_part_name(part_name: str) -> str:
        """Reject library-provided part names that could escape the output folder."""
        if (
            not isinstance(part_name, str)
            or not part_name
            or part_name in {".", ".."}
            or part_name != part_name.strip()
            or any(character in part_name for character in '<>:"/\\|?*')
            or any(ord(character) < 32 for character in part_name)
            or part_name.endswith((".", " "))
        ):
            raise CadGenerationError(
                f"The clock library returned an unsafe part name: {part_name!r}."
            )
        reserved_name = part_name.split(".", 1)[0].upper()
        if reserved_name in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{index}" for index in range(1, 10)),
            *(f"LPT{index}" for index in range(1, 10)),
        }:
            raise CadGenerationError(
                f"The clock library returned a reserved Windows part name: "
                f"{part_name!r}."
            )
        return part_name


def _install_cadquery_text_compatibility(cadquery: Any) -> None:
    """Translate the clock library's legacy text flags to CadQuery 2.8 options."""
    text_method = cadquery.Workplane.text
    if "cut" in inspect.signature(text_method).parameters:
        return

    def compatible_text(
        workplane: Any,
        *args: Any,
        cut: bool = False,
        combine: bool | str = True,
        **kwargs: Any,
    ) -> Any:
        if isinstance(combine, str):
            combine_mode: bool | str = combine
        elif combine:
            combine_mode = "cut" if cut else True
        else:
            combine_mode = False
        return text_method(
            workplane,
            *args,
            combine=combine_mode,
            **kwargs,
        )

    cadquery.Workplane.text = compatible_text
