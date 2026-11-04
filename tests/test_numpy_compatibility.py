import importlib.util
import importlib
import unittest
from pathlib import Path

import numpy as np

from gear_solver import _install_numpy_compatibility, load_clock_library


class NumpyCompatibilityShimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_numpy_compatibility()

    def test_two_dimensional_cross_product_returns_determinant(self):
        np.testing.assert_allclose(
            np.cross((1.0, 0.0), (0.0, 1.0)),
            1.0,
        )

    def test_mixed_two_and_three_dimensional_cross_product(self):
        np.testing.assert_allclose(
            np.cross((1.0, 0.0), (0.0, 0.0, 1.0)),
            (0.0, -1.0, 0.0),
        )

    def test_legacy_numpy_linalg_import_resolves(self):
        self.assertIs(importlib.import_module("numpy.linalg.linalg"), np.linalg)


@unittest.skipUnless(importlib.util.find_spec("cadquery"), "CadQuery is required.")
class ClockLibraryNumpyCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repository_root = Path(__file__).resolve().parents[1]
        library_path = repository_root / "3DPrintedClocksGithub" / "3DPrintedClocks"
        cls.clock = load_clock_library(library_path)

    def test_two_dimensional_perpendicular_does_not_use_cross(self):
        np.testing.assert_allclose(
            self.clock.get_perpendicular_direction((1.0, 0.0)),
            (0.0, -1.0),
        )

    def test_line_perpendicular_and_distance_are_correct(self):
        line = self.clock.Line((0.0, 0.0), direction=(1.0, 0.0))

        np.testing.assert_allclose(
            line.get_perpendicular_direction(),
            (0.0, -1.0),
        )
        self.assertAlmostEqual(
            line.get_shortest_distance_to_point((0.0, 1.0)),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
