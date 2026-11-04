"""Safe startup update checks for the application's GitHub repository."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from typing import Callable


APPLICATION_REMOTE = (
    "https://github.com/vothanhhuy161/"
    "parametric-3d-printed-clock-generator.git"
)
APPLICATION_BRANCH = "main"


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of checking for and optionally applying an application update."""

    status: str
    message: str
    updated: bool = False
    fatal: bool = False


def _normalize_remote(url: str) -> str:
    """Normalize HTTPS and SSH forms of the configured application remote."""
    normalized = url.strip().removesuffix(".git").rstrip("/").lower()
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized.removeprefix(
            "git@github.com:"
        )
    elif normalized.startswith("ssh://git@github.com/"):
        normalized = "https://github.com/" + normalized.removeprefix(
            "ssh://git@github.com/"
        )
    return normalized


def _run_git(
    repository: Path,
    *arguments: str,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run Git without interactive prompts and capture its output."""
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=environment,
    )


def check_for_updates(
    repository: str | Path,
    *,
    input_func: Callable[[str], str] = input,
    is_interactive: bool = False,
) -> UpdateResult:
    """Check the configured GitHub main branch and ask before safe fast-forward."""
    repository_path = Path(repository).resolve()
    try:
        remote = _run_git(repository_path, "remote", "get-url", "origin")
        if remote.returncode != 0:
            return UpdateResult(
                "not_available",
                "Automatic updates are unavailable: this folder has no Git origin.",
            )
        if _normalize_remote(remote.stdout) != _normalize_remote(APPLICATION_REMOTE):
            return UpdateResult(
                "not_available",
                "Automatic updates were skipped: origin is not the configured "
                "application repository.",
            )

        branch = _run_git(repository_path, "branch", "--show-current")
        if branch.returncode != 0:
            return UpdateResult(
                "check_failed",
                f"Unable to determine the current Git branch: "
                f"{branch.stderr.strip()}",
            )
        current_branch = branch.stdout.strip()
        if current_branch != APPLICATION_BRANCH:
            return UpdateResult(
                "not_available",
                f"Automatic updates are only checked on the "
                f"'{APPLICATION_BRANCH}' branch; current branch is "
                f"'{current_branch or '(detached HEAD)'}'.",
            )

        fetched = _run_git(repository_path, "fetch", "--quiet", "origin")
        if fetched.returncode != 0:
            return UpdateResult(
                "check_failed",
                "Unable to check GitHub for updates. Check your network and GitHub "
                f"authentication: {fetched.stderr.strip()}",
            )

        divergence = _run_git(
            repository_path,
            "rev-list",
            "--left-right",
            "--count",
            f"HEAD...origin/{APPLICATION_BRANCH}",
        )
        if divergence.returncode != 0:
            return UpdateResult(
                "check_failed",
                f"Unable to compare the local and GitHub branches: "
                f"{divergence.stderr.strip()}",
            )
        try:
            ahead, behind = (
                int(value) for value in divergence.stdout.split()
            )
        except (ValueError, TypeError):
            return UpdateResult(
                "check_failed",
                "Git returned an unreadable local/remote commit comparison: "
                f"{divergence.stdout.strip()}",
            )

        if behind == 0:
            return UpdateResult("current", "Application is up to date.")
        if ahead:
            return UpdateResult(
                "diverged",
                "An update is available, but the local main branch also has "
                "commits not on GitHub. No changes were made; reconcile the "
                "branches manually.",
            )

        changes = _run_git(
            repository_path,
            "status",
            "--porcelain",
            "--untracked-files=normal",
        )
        if changes.returncode != 0:
            return UpdateResult(
                "check_failed",
                f"Unable to check for local changes: {changes.stderr.strip()}",
            )
        if changes.stdout.strip():
            return UpdateResult(
                "local_changes",
                "A GitHub update is available, but local files have uncommitted "
                "changes. Nothing was changed; commit or stash your work before "
                "updating.",
            )

        if not is_interactive:
            return UpdateResult(
                "available",
                "An application update is available. Run this program in a "
                "terminal to review and approve it.",
            )

        try:
            answer = input_func(
                "A new application update is available from GitHub. "
                "Update now? [y/N]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return UpdateResult(
                "declined",
                "Update prompt interrupted; no files were changed.",
            )
        if answer not in {"y", "yes"}:
            return UpdateResult(
                "declined",
                "Application update skipped; no files were changed.",
            )

        merged = _run_git(
            repository_path,
            "merge",
            "--ff-only",
            f"origin/{APPLICATION_BRANCH}",
        )
        if merged.returncode != 0:
            return UpdateResult(
                "update_failed",
                f"Unable to apply the update safely: {merged.stderr.strip()}",
                fatal=True,
            )

        submodule = _run_git(
            repository_path,
            "submodule",
            "update",
            "--init",
            "--recursive",
        )
        if submodule.returncode != 0:
            return UpdateResult(
                "update_failed",
                "Application code was updated, but its clock-library submodule "
                f"could not be synchronized: {submodule.stderr.strip()}",
                fatal=True,
            )

        return UpdateResult(
            "updated",
            "Application and clock-library submodule updated. Restart the "
            "program to use the new version.",
            updated=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UpdateResult(
            "check_failed",
            f"Unable to check for application updates: {exc}",
        )
