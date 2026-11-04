# Changelog

All notable changes to this project are documented in this file.

This changelog follows Keep a Changelog and Conventional Commits.

## [0.1.0] - 2026-11-05

### Added

- `feat(workflow): automate developer code publishing`
- Regression tests for configuration safety, export paths, solver failures, and NumPy compatibility.

### Changed

- Declare the clock generator's direct Python dependencies in `requirements.txt` and document one-command installation.
- Clarify that MIT covers the project code while the upstream clock library retains its separate CERN-OHL-S v2 license.
- Reject malformed or oversized clock configurations, guard generated-part paths, and report common upstream gear-solver failures clearly.
- Preserve compatibility with legacy NumPy geometry operations in the upstream clock library when running with NumPy 2.
