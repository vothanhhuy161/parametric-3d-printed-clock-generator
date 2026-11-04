"""Command-line entry point for the parametric clock generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

from cad_generator import CadGenerationError, CadGenerator
from config_handler import ClockConfig, ConfigurationError
from design_review import (
    MAX_DESIGN_DEVIATION_PERCENT,
    compare_pendulum_target,
    format_design_comparison,
)
from gear_solver import GearSolver
from nesting_exporter import NestingError, NestingExporter
from validator import ConstraintError, validate_config


PROJECT_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
LIBRARY_ROOT = (
    Path(sys._MEIPASS)
    if getattr(sys, "frozen", False)
    else PROJECT_ROOT
)
DEFAULT_LIBRARY = LIBRARY_ROOT / "3DPrintedClocksGithub" / "3DPrintedClocks"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "GeneratedClock"


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser, including every supported clock setting."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a parametric 3D-printed clock. This project was developed "
            "with AI assistance; AI is not used at runtime."
        ),
        epilog=(
            "Examples:\n"
            "  py -3.14 main.py --help\n"
            "  py -3.14 main.py --interactive\n"
            "  py -3.14 main.py --run-duration 8day --case-style mantel "
            "--escapement brocot --pendulum-length 0.25\n"
            "  py -3.14 main.py --config clock_config.json "
            "--output GeneratedClock\\Clock_1"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Ask for clock settings in the terminal.",
    )
    mode.add_argument(
        "--config",
        type=Path,
        help="Path to a clock configuration JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Directory for generated files. By default, uses the next available "
            "GeneratedClock/Clock_N folder."
        ),
    )
    parser.add_argument(
        "--accept-design-deviation",
        action="store_true",
        help=(
            f"Approve a calculated pendulum deviation of up to "
            f"{MAX_DESIGN_DEVIATION_PERCENT:g}%%; deviations above "
            f"{MAX_DESIGN_DEVIATION_PERCENT:g}%% always stop generation."
        ),
    )
    parser.add_argument(
        "--library",
        type=Path,
        default=DEFAULT_LIBRARY,
        help="Path to the local 3DPrintedClocks repository directory.",
    )
    cli_defaults = {"default": argparse.SUPPRESS}
    parser.add_argument(
        "--run-duration",
        choices=("30h", "8day"),
        help="Clock runtime preset: 30 hours or 8 days.",
        **cli_defaults,
    )
    parser.add_argument(
        "--case-style",
        choices=("wall", "mantel", "round"),
        help="Clock case style: wall, skeleton mantel, or round wall plates.",
        **cli_defaults,
    )
    parser.add_argument(
        "--escapement",
        choices=("grasshopper", "deadbeat", "brocot"),
        help="Clock escapement type.",
        **cli_defaults,
    )
    parser.add_argument(
        "--pendulum-length",
        type=float,
        metavar="METERS",
        help="Pendulum length in meters.",
        **cli_defaults,
    )
    parser.add_argument(
        "--target-beat-rate",
        type=float,
        metavar="BPM",
        help="Target pendulum beat rate in beats per minute; overrides length.",
        **cli_defaults,
    )
    parser.add_argument(
        "--complications",
        nargs="*",
        choices=("moon_phase", "day_of_week"),
        metavar="NAME",
        help=(
            "Complications: moon_phase, or day_of_week (requires --case-style "
            "round; choose only one). Omit values for none."
        ),
        **cli_defaults,
    )
    parser.add_argument(
        "--bed-dimensions",
        type=float,
        nargs=3,
        metavar=("X_MM", "Y_MM", "Z_MM"),
        help="Printer bed dimensions in millimeters.",
        **cli_defaults,
    )
    parser.add_argument(
        "--nozzle-size",
        type=float,
        metavar="MM",
        help="Printer nozzle diameter in millimeters.",
        **cli_defaults,
    )
    parser.add_argument(
        "--clearance",
        type=float,
        metavar="MM",
        help="Manufacturing clearance guidance in millimeters (0.1 to 0.5).",
        **cli_defaults,
    )
    parser.add_argument(
        "--case-dimensions",
        type=float,
        nargs=3,
        metavar=("WIDTH_MM", "HEIGHT_MM", "DEPTH_MM"),
        help="Case dimensions in millimeters.",
        **cli_defaults,
    )
    parser.add_argument(
        "--pendulum-bob-diameter",
        type=float,
        metavar="MM",
        help="Pendulum bob diameter in millimeters.",
        **cli_defaults,
    )
    parser.add_argument(
        "--weight-drop",
        type=float,
        metavar="MM",
        help="Weight travel/drop distance in millimeters.",
        **cli_defaults,
    )
    parser.add_argument(
        "--available-drop-path",
        type=float,
        metavar="MM",
        help="Available internal weight path in millimeters.",
        **cli_defaults,
    )
    parser.add_argument(
        "--weight-mass",
        type=float,
        metavar="KG",
        help="Driving weight mass in kilograms.",
        **cli_defaults,
    )
    parser.add_argument(
        "--estimated-friction-power",
        type=float,
        metavar="MICROWATTS",
        help="Estimated clock friction load in microwatts.",
        **cli_defaults,
    )
    parser.add_argument(
        "--gear-module",
        type=float,
        metavar="MM",
        help="Gear module in millimeters; defaults based on run duration.",
        **cli_defaults,
    )
    return parser


_CLI_CONFIG_FIELDS = {
    "run_duration": "run_duration",
    "case_style": "case_style",
    "escapement": "escapement",
    "pendulum_length_m": "pendulum_length",
    "target_beat_rate_bpm": "target_beat_rate",
    "complications": "complications",
    "bed_dimensions_mm": "bed_dimensions",
    "nozzle_size_mm": "nozzle_size",
    "clearance_mm": "clearance",
    "case_dimensions_mm": "case_dimensions",
    "pendulum_bob_diameter_mm": "pendulum_bob_diameter",
    "weight_drop_mm": "weight_drop",
    "available_drop_path_mm": "available_drop_path",
    "weight_mass_kg": "weight_mass",
    "estimated_friction_power_uw": "estimated_friction_power",
    "gear_module_mm": "gear_module",
}


def _prompt_value(
    label: str,
    current: Any,
    converter: Callable[[str], Any],
    display: str | None = None,
) -> Any:
    """Prompt until a value is valid, retaining the current value on Enter."""
    default_text = str(current) if display is None else display
    while True:
        answer = input(f"{label} [{default_text}]: ").strip()
        if not answer:
            return current
        try:
            return converter(answer)
        except ValueError as exc:
            print(f"Invalid value: {exc}. Please try again.")


def _prompt_choice(value: str, choices: tuple[str, ...]) -> str:
    """Parse a case-insensitive value from a fixed set of choices."""
    normalized = value.lower()
    if normalized not in choices:
        raise ValueError(f"choose one of {', '.join(choices)}")
    return normalized


def _prompt_dimensions(value: str) -> tuple[float, float, float]:
    """Parse exactly three comma-separated dimensions."""
    dimensions = tuple(float(item.strip()) for item in value.split(","))
    if len(dimensions) != 3:
        raise ValueError("enter exactly three comma-separated numbers")
    return dimensions


def _prompt_complications(value: str) -> list[str]:
    """Parse supported comma-separated complication names."""
    complications = [
        item.strip().lower() for item in value.split(",") if item.strip()
    ]
    unsupported = set(complications) - {"moon_phase", "day_of_week"}
    if unsupported:
        raise ValueError(
            "supported complications: moon_phase, day_of_week; "
            f"unknown: {', '.join(sorted(unsupported))}"
        )
    if len(set(complications)) != len(complications):
        raise ValueError("do not enter the same complication more than once")
    return complications


def _interactive_config() -> ClockConfig:
    """Collect a complete configuration from terminal prompts."""
    defaults = ClockConfig()
    print("Clock setup (press Enter to keep each value in brackets).")
    values = defaults.to_dict()
    values["run_duration"] = _prompt_value(
        "Run duration (30h or 8day)",
        defaults.run_duration,
        lambda value: _prompt_choice(value, ("30h", "8day")),
    )
    values["case_style"] = _prompt_value(
        "Case style (wall, mantel, or round)",
        defaults.case_style,
        lambda value: _prompt_choice(value, ("wall", "mantel", "round")),
    )
    values["escapement"] = _prompt_value(
        "Escapement (grasshopper, deadbeat, brocot)",
        defaults.escapement,
        lambda value: _prompt_choice(
            value,
            ("grasshopper", "deadbeat", "brocot"),
        ),
    )
    values["pendulum_length_m"] = _prompt_value(
        "Pendulum length in meters",
        defaults.pendulum_length_m,
        float,
    )
    beat_rate = _prompt_value(
        "Target beat rate in BPM (optional; overrides pendulum length)",
        defaults.target_beat_rate_bpm,
        float,
        "none",
    )
    values["target_beat_rate_bpm"] = beat_rate
    values["complications"] = _prompt_value(
        "Complications (comma-separated; moon_phase or day_of_week)",
        defaults.complications,
        _prompt_complications,
        "none",
    )
    for key, label in (
        ("bed_dimensions_mm", "Printer bed X,Y,Z in mm"),
        ("case_dimensions_mm", "Case width,height,depth in mm"),
    ):
        current = tuple(values[key])
        values[key] = _prompt_value(
            label,
            current,
            _prompt_dimensions,
            ",".join(str(item) for item in current),
        )
    for key, label in (
        ("nozzle_size_mm", "Nozzle size in mm"),
        ("clearance_mm", "Clearance guidance in mm"),
        ("pendulum_bob_diameter_mm", "Pendulum bob diameter in mm"),
        ("weight_drop_mm", "Weight drop in mm"),
        ("available_drop_path_mm", "Available weight path in mm"),
        ("weight_mass_kg", "Driving weight mass in kg"),
        ("estimated_friction_power_uw", "Estimated friction power in microwatts"),
    ):
        values[key] = _prompt_value(label, values[key], float)
    values["gear_module_mm"] = _prompt_value(
        "Gear module in mm (optional)",
        defaults.gear_module_mm,
        float,
        "automatic",
    )
    return ClockConfig.from_mapping(values)


def _config_from_arguments(arguments: argparse.Namespace) -> ClockConfig:
    """Load JSON/default configuration and apply explicitly supplied options."""
    if arguments.config:
        config = ClockConfig.from_json_file(arguments.config)
        values = config.to_dict()
    else:
        values = ClockConfig().to_dict()
    for field, argument in _CLI_CONFIG_FIELDS.items():
        if hasattr(arguments, argument):
            values[field] = getattr(arguments, argument)
    return ClockConfig.from_mapping(values)


def _next_output_directory(output_root: Path | None = None) -> Path:
    """Return the first unused numbered clock directory under the output root."""
    if output_root is None:
        output_root = DEFAULT_OUTPUT_ROOT
    used_numbers: set[int] = set()
    if output_root.exists():
        for path in output_root.iterdir():
            match = re.fullmatch(r"Clock_(\d+)", path.name)
            if match is not None:
                used_numbers.add(int(match.group(1)))
    number = 1
    while number in used_numbers or (output_root / f"Clock_{number}").exists():
        number += 1
    return output_root / f"Clock_{number}"


def main(argv: list[str] | None = None) -> int:
    """Run configuration validation, train solving, CAD generation, and nesting."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)

    try:
        output_directory = arguments.output or _next_output_directory()
        if arguments.interactive:
            supplied_options = [
                f"--{name.replace('_', '-')}"
                for name in _CLI_CONFIG_FIELDS.values()
                if hasattr(arguments, name)
            ]
            if supplied_options:
                parser.error(
                    "--interactive cannot be combined with individual clock "
                    f"options: {', '.join(supplied_options)}"
                )
            output_directory = _prompt_value(
                "Output folder for generated files",
                arguments.output,
                lambda value: Path(value).expanduser(),
            )
            config = _interactive_config()
        else:
            config = _config_from_arguments(arguments)
    except (EOFError, KeyboardInterrupt):
        print("\nClock setup cancelled.", file=sys.stderr)
        return 130
    except (ConfigurationError, OSError, ValueError) as exc:
        print(f"Clock generation failed: {exc}", file=sys.stderr)
        return 2
    try:
        report = validate_config(config)
        solution = GearSolver(arguments.library).solve(config, report)
        comparison = compare_pendulum_target(config, solution)
        print(
            "Calculated design comparison "
            f"({MAX_DESIGN_DEVIATION_PERCENT:g}% maximum deviation):"
        )
        print(format_design_comparison(comparison))
        if not comparison.within_tolerance:
            print(
                f"Clock generation stopped: the calculated value deviates by "
                f"{comparison.deviation_percent:.3f}%, exceeding the "
                f"{MAX_DESIGN_DEVIATION_PERCENT:.1f}% limit. Revise the pendulum "
                "target or other clock inputs and try again.",
                file=sys.stderr,
            )
            return 2
        if not arguments.accept_design_deviation:
            try:
                if arguments.interactive or sys.stdin.isatty():
                    answer = input(
                        "Proceed with the calculated pendulum value? [y/N]: "
                    ).strip().lower()
                    if answer not in {"y", "yes"}:
                        print("Clock generation cancelled; no CAD files were created.")
                        return 2
                else:
                    print(
                        "Clock generation requires approval. Review the table and "
                        "rerun with --accept-design-deviation to proceed.",
                        file=sys.stderr,
                    )
                    return 2
            except (EOFError, KeyboardInterrupt):
                print("\nClock generation cancelled; no CAD files were created.")
                return 130
        raw_parts = CadGenerator(output_directory, arguments.library).generate(
            config, solution
        )
        gear_pairs = [
            {
                "wheel_teeth": pair.wheel_teeth,
                "pinion_teeth": pair.pinion_teeth,
                "module_mm": pair.module_mm,
                "center_distance_mm": pair.center_distance_mm,
            }
            for pair in solution.gear_pairs
        ]
        config_metadata = config.to_dict()
        config_metadata["gear_module_mm"] = config.effective_gear_module_mm
        exported = NestingExporter(config.bed_dimensions_mm).export(
            raw_parts,
            output_directory,
            config_metadata,
            gear_pairs,
            {
                "warnings": list(report.warnings),
                "available_power_uw": report.available_power_uw,
                "estimated_required_power_uw": report.estimated_required_power_uw,
                "pendulum_period_s": report.pendulum_period_s,
                "calculated_pendulum_period_s": (
                    solution.calculated_pendulum_period_s
                ),
                "design_comparison": comparison.to_dict(),
            },
            powered_wheel_ratios=[
                list(pair) for pair in solution.powered_wheel_ratios
            ],
        )
    except (
        ConfigurationError,
        ConstraintError,
        CadGenerationError,
        NestingError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"Clock generation failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "output_directory": str(output_directory.resolve()),
                "runtime_hours": solution.runtime_hours,
                "gear_pairs": gear_pairs,
                "powered_wheel_ratios": solution.powered_wheel_ratios,
                "design_comparison": comparison.to_dict(),
                "files": [str(path) for path in exported],
                "warnings": list(report.warnings),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())