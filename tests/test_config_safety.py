import tempfile
import unittest
from pathlib import Path

from cad_generator import CadGenerationError, CadGenerator
from config_handler import (
    MAX_CONFIG_FILE_BYTES,
    ClockConfig,
    ConfigurationError,
)
from validator import ConstraintError, validate_config


class ConfigurationSafetyTests(unittest.TestCase):
    def test_numeric_strings_are_not_coerced(self):
        with self.assertRaisesRegex(ConfigurationError, "JSON number"):
            ClockConfig.from_mapping({"weight_mass_kg": "2"})

    def test_boolean_is_not_accepted_as_numeric_input(self):
        with self.assertRaisesRegex(ConfigurationError, "JSON number"):
            ClockConfig.from_mapping({"bed_dimensions_mm": [220, True, 250]})

    def test_non_finite_numbers_are_rejected(self):
        with self.assertRaisesRegex(ConfigurationError, "finite"):
            ClockConfig.from_mapping({"pendulum_length_m": float("inf")})

    def test_dimension_arrays_require_exactly_three_values(self):
        with self.assertRaisesRegex(ConfigurationError, "exactly three"):
            ClockConfig.from_mapping({"bed_dimensions_mm": [220, 220]})

    def test_complications_require_string_names(self):
        with self.assertRaisesRegex(ConfigurationError, "only string names"):
            ClockConfig.from_mapping({"complications": ["moon_phase", 1]})

    def test_oversized_json_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "clock.json"
            config_path.write_bytes(b" " * (MAX_CONFIG_FILE_BYTES + 1))

            with self.assertRaisesRegex(ConfigurationError, "exceeds"):
                ClockConfig.from_json_file(config_path)

    def test_direct_dataclass_construction_still_rejects_boolean_dimensions(self):
        config = ClockConfig(bed_dimensions_mm=(220, True, 250))

        with self.assertRaisesRegex(ConstraintError, "bed_dimensions_mm"):
            validate_config(config)


class ExportPathSafetyTests(unittest.TestCase):
    def test_output_directory_inside_clock_library_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            library_directory = Path(temporary_directory) / "clock-library"
            output_directory = library_directory / "generated"
            library_directory.mkdir()

            with self.assertRaisesRegex(CadGenerationError, "inside the clock library"):
                CadGenerator(output_directory, library_directory)

    def test_library_part_name_must_not_contain_path_components(self):
        for unsafe_name in ("../escape", "folder\\escape", "CON", "part?.stl"):
            with self.subTest(unsafe_name=unsafe_name):
                with self.assertRaises(CadGenerationError):
                    CadGenerator._validate_part_name(unsafe_name)

    def test_plain_library_part_name_is_preserved(self):
        self.assertEqual(
            CadGenerator._validate_part_name("day_hand"),
            "day_hand",
        )


if __name__ == "__main__":
    unittest.main()
