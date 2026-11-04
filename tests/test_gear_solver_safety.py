import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config_handler import ClockConfig
from gear_solver import GearSolver
from validator import validate_config


class GearSolverSafetyTests(unittest.TestCase):
    def test_numeric_failure_from_ratio_solver_becomes_actionable_error(self):
        class FakeTrain:
            def calculate_ratios(self, **kwargs):
                raise ZeroDivisionError("invalid test ratio")

        fake_clock = SimpleNamespace(GoingTrain=lambda **kwargs: FakeTrain())
        config = ClockConfig()

        with tempfile.TemporaryDirectory() as temporary_directory:
            library_path = Path(temporary_directory)
            with (
                patch("gear_solver.load_clock_library", return_value=fake_clock),
                patch.object(
                    GearSolver,
                    "_make_escapement",
                    return_value=object(),
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "found no train.*ZeroDivisionError: invalid test ratio",
                ):
                    GearSolver(library_path).solve(
                        config,
                        validate_config(config),
                    )


if __name__ == "__main__":
    unittest.main()
