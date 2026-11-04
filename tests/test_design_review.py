import unittest
from types import SimpleNamespace

from config_handler import ClockConfig, ConfigurationError
from design_review import (
    MAX_DESIGN_DEVIATION_PERCENT,
    compare_pendulum_target,
    format_design_comparison,
)
from main import _build_parser


class DesignReviewTests(unittest.TestCase):
    def test_deviation_limit_is_not_a_user_config_or_cli_option(self):
        with self.assertRaises(ConfigurationError):
            ClockConfig.from_mapping(
                {"max_design_deviation_percent": MAX_DESIGN_DEVIATION_PERCENT}
            )

        parser_options = {
            option
            for action in _build_parser()._actions
            for option in action.option_strings
        }
        self.assertNotIn("--max-design-deviation-percent", parser_options)

    def test_pendulum_length_target_is_compared_to_calculated_length(self):
        config = ClockConfig(pendulum_length_m=0.5)
        solution = SimpleNamespace(
            calculated_pendulum_length_m=0.52,
            calculated_beat_rate_bpm=84.0,
        )

        comparison = compare_pendulum_target(config, solution)

        self.assertEqual(comparison.parameter, "Pendulum length")
        self.assertEqual(comparison.target_value, 0.5)
        self.assertEqual(comparison.calculated_value, 0.52)
        self.assertEqual(comparison.unit, "m")
        self.assertAlmostEqual(comparison.deviation_percent, 4.0)
        self.assertTrue(comparison.within_tolerance)

    def test_beat_rate_target_takes_precedence_over_default_length(self):
        config = ClockConfig(
            pendulum_length_m=0.5,
            target_beat_rate_bpm=80.0,
        )
        solution = SimpleNamespace(
            calculated_pendulum_length_m=0.6,
            calculated_beat_rate_bpm=84.0,
        )

        comparison = compare_pendulum_target(config, solution)

        self.assertEqual(comparison.parameter, "Pendulum beat rate")
        self.assertEqual(comparison.target_value, 80.0)
        self.assertEqual(comparison.calculated_value, 84.0)
        self.assertEqual(comparison.unit, "beats/min")
        self.assertEqual(comparison.deviation_percent, 5.0)
        self.assertTrue(comparison.within_tolerance)

    def test_deviation_above_five_percent_is_outside_tolerance(self):
        config = ClockConfig(pendulum_length_m=0.5)
        solution = SimpleNamespace(
            calculated_pendulum_length_m=0.526,
            calculated_beat_rate_bpm=80.0,
        )

        comparison = compare_pendulum_target(config, solution)

        self.assertGreater(
            comparison.deviation_percent,
            MAX_DESIGN_DEVIATION_PERCENT,
        )
        self.assertFalse(comparison.within_tolerance)

    def test_comparison_table_shows_requested_and_calculated_values(self):
        config = ClockConfig(pendulum_length_m=0.5)
        solution = SimpleNamespace(
            calculated_pendulum_length_m=0.50017,
            calculated_beat_rate_bpm=84.58,
        )

        table = format_design_comparison(compare_pendulum_target(config, solution))

        self.assertIn("User target", table)
        self.assertIn("Calculated", table)
        self.assertIn("Pendulum length", table)
        self.assertIn("0.50017 m", table)
        self.assertIn("0.034%", table)


if __name__ == "__main__":
    unittest.main()
