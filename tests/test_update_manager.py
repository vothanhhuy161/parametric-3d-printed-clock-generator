import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from update_manager import check_for_updates


def _git_result(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class UpdateManagerTests(unittest.TestCase):
    @patch("update_manager._run_git")
    def test_up_to_date_branch_does_not_prompt(self, run_git):
        run_git.side_effect = [
            _git_result(
                "https://github.com/vothanhhuy161/"
                "parametric-3d-printed-clock-generator.git\n"
            ),
            _git_result("main\n"),
            _git_result(),
            _git_result("0\t0\n"),
        ]

        result = check_for_updates(
            Path("."),
            input_func=lambda _: self.fail("Should not prompt"),
            is_interactive=True,
        )

        self.assertEqual(result.status, "current")
        self.assertFalse(result.updated)
        self.assertEqual(run_git.call_count, 4)

    @patch("update_manager._run_git")
    def test_user_approval_fast_forwards_and_updates_submodule(self, run_git):
        run_git.side_effect = [
            _git_result(
                "git@github.com:vothanhhuy161/"
                "parametric-3d-printed-clock-generator.git\n"
            ),
            _git_result("main\n"),
            _git_result(),
            _git_result("0\t2\n"),
            _git_result(),
            _git_result(),
            _git_result(),
        ]
        prompts = []

        def approve(prompt):
            prompts.append(prompt)
            return "yes"

        result = check_for_updates(
            Path("."),
            input_func=approve,
            is_interactive=True,
        )

        self.assertEqual(result.status, "updated")
        self.assertTrue(result.updated)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(run_git.call_args_list[-2].args[1:], (
            "merge",
            "--ff-only",
            "origin/main",
        ))
        self.assertEqual(run_git.call_args_list[-1].args[1:], (
            "submodule",
            "update",
            "--init",
            "--recursive",
        ))

    @patch("update_manager._run_git")
    def test_local_changes_prevent_update_prompt_and_merge(self, run_git):
        run_git.side_effect = [
            _git_result(
                "https://github.com/vothanhhuy161/"
                "parametric-3d-printed-clock-generator.git\n"
            ),
            _git_result("main\n"),
            _git_result(),
            _git_result("0\t1\n"),
            _git_result(" M main.py\n"),
        ]

        result = check_for_updates(
            Path("."),
            input_func=lambda _: self.fail("Dirty worktree must not prompt"),
            is_interactive=True,
        )

        self.assertEqual(result.status, "local_changes")
        self.assertFalse(result.updated)
        self.assertEqual(run_git.call_count, 5)

    @patch("update_manager._run_git")
    def test_non_interactive_mode_reports_update_without_applying(self, run_git):
        run_git.side_effect = [
            _git_result(
                "https://github.com/vothanhhuy161/"
                "parametric-3d-printed-clock-generator.git\n"
            ),
            _git_result("main\n"),
            _git_result(),
            _git_result("0\t1\n"),
            _git_result(),
        ]

        result = check_for_updates(Path("."), is_interactive=False)

        self.assertEqual(result.status, "available")
        self.assertFalse(result.updated)
        self.assertEqual(run_git.call_count, 5)

    @patch("update_manager._run_git")
    def test_user_can_decline_update_without_changing_files(self, run_git):
        run_git.side_effect = [
            _git_result(
                "https://github.com/vothanhhuy161/"
                "parametric-3d-printed-clock-generator.git\n"
            ),
            _git_result("main\n"),
            _git_result(),
            _git_result("0\t1\n"),
            _git_result(),
        ]

        result = check_for_updates(
            Path("."),
            input_func=lambda _: "n",
            is_interactive=True,
        )

        self.assertEqual(result.status, "declined")
        self.assertFalse(result.updated)
        self.assertEqual(run_git.call_count, 5)

    @patch("update_manager._run_git")
    def test_other_remotes_are_never_updated(self, run_git):
        run_git.return_value = _git_result("https://example.com/other/project.git\n")

        result = check_for_updates(Path("."), is_interactive=True)

        self.assertEqual(result.status, "not_available")
        self.assertEqual(run_git.call_count, 1)


if __name__ == "__main__":
    unittest.main()
