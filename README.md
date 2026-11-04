# Parametric 3D-Printed Clock Generator

This application validates a JSON clock configuration, calls the
`3DPrintedClocksGithub/3DPrintedClocks` library to calculate the train and
generate parts, then nests the exported STL components onto one or more printer
plates.

## AI use disclosure

This application was developed with the assistance of generative AI tools.
The application does not use AI at runtime; clock calculations and CAD
generation are performed by its Python code and the 3DPrintedClocks library.

## Files

```text
Code/
|-- main.py
|-- config_handler.py
|-- validator.py
|-- gear_solver.py
|-- cad_generator.py
|-- nesting_exporter.py
|-- requirements.txt
`-- 3DPrintedClocksGithub/
    `-- 3DPrintedClocks/
        `-- clocks/
```

Install the requirements in the same Python environment used to run the
application. Clone the application with its upstream library submodule:

```powershell
git clone --recurse-submodules https://github.com/vothanhhuy161/parametric-3d-printed-clock-generator.git
cd parametric-3d-printed-clock-generator
```

If you already cloned without `--recurse-submodules`, run:

```powershell
git submodule update --init --recursive
```

Python 3.14 with CadQuery 2.8 has been tested; Python 3.15 may not have
compatible CadQuery/OCP packages available. On Windows, install the
requirements in the same Python environment used to run the application:

```powershell
py -3.14 -m pip install -r requirements.txt
```

The cloned clock library may have additional dependencies; follow its setup
documentation if its import reports a missing package.

## Publishing developer changes

When this project is open in VS Code, the
`Auto-publish saved source changes` task watches for saved Python source files
and the root `README.md`. After three seconds without further saves, it creates
a local Git commit. The task asks for a descriptive Conventional Commit subject
(for example, `feat(clock): add moon phase support`), records it under
`[Unreleased]` in `CHANGELOG.md`, then asks whether to push the commit to
GitHub. It only publishes from the `main` branch, only to this project's
configured GitHub remote, and never force-pushes. Declining the push keeps the
commit locally; pressing Enter at the commit prompt cancels the commit.

The upstream 3DPrintedClocks submodule, generated files, and VS Code machine
settings are excluded. If unrelated files are already staged, automatic
publishing stops rather than including them. VS Code may ask you to allow
automatic tasks when you first open the trusted workspace.

To update your developer checkout from GitHub, run:

```powershell
git pull --ff-only origin main
git submodule update --init --recursive
```

These developer Git operations do not add runtime self-updates for people using
the application.

## Library attribution

This application uses the **3DPrintedClocks** library by **Luke Wallin**:
[github.com/MrBunsy/3DPrintedClocks](https://github.com/MrBunsy/3DPrintedClocks).
The upstream library is licensed under the
[CERN Open Hardware Licence Version 2 - Strongly Reciprocal (CERN-OHL-S v2)](https://ohwr.org/cern_ohl_s_v2.txt);
see the bundled
[upstream LICENSE](./3DPrintedClocksGithub/3DPrintedClocks/LICENSE).

Generated geometry uses the upstream library. Please retain this attribution
and review the license when sharing generated models or hardware. The upstream
README asks that, where practicable, the source location
`https://github.com/MrBunsy/3DPrintedClocks` be visible on the exterior of
hardware made from the source. This credit does not imply that the upstream
author endorses this application.

## Ways to run

Show all supported commands and settings:

```powershell
py -3.14 main.py --help
```

Answer prompts interactively (press Enter to accept displayed defaults,
including the output folder):

```powershell
py -3.14 main.py --interactive
```

The interactive mode asks where to save the generated files. By default, the
program creates the next unused numbered folder under `GeneratedClock`, such
as `GeneratedClock\Clock_1`, then `GeneratedClock\Clock_2`. Press Enter to use
the displayed folder or enter another path.

Pass settings as command-line arguments:

```powershell
py -3.14 main.py --run-duration 8day --case-style mantel `
  --escapement brocot --pendulum-length 0.25 `
  --complications moon_phase --bed-dimensions 220 220 250 `
  --output "D:\3D Prints\Clock"
```

If `--output` is omitted, command-line mode uses the same next available
`GeneratedClock\Clock_N` folder as interactive mode.

Before creating CAD files, the application compares the requested pendulum
length (or beat rate, if supplied) with the value calculated from the selected
gear train. The global threshold is `MAX_DESIGN_DEVIATION_PERCENT` in
`design_review.py`. It is a developer-maintained source-code constant, not a
user setting: changing the allowed deviation requires a developer to edit that
constant. It is not exposed through the interactive prompts, JSON configuration,
or command-line options.
The application displays the comparison table and requires approval when the
difference is within the configured threshold. In terminal mode, answer the
prompt; for noninteractive CLI runs, pass `--accept-design-deviation`. A
difference above the threshold always stops generation and requires revised
inputs; approval cannot override this limit.
This comparison does not scale or silently resize any geometry. Case dimensions
remain clearance constraints, and printer-bed dimensions remain hard part-fit
limits during nesting; neither currently represents a calculated whole-clock
target.

Generate a round wall clock with a weekday display:

```powershell
py -3.14 main.py --run-duration 30h --case-style round `
  --complications day_of_week --bed-dimensions 250 250 250 `
  --output generated_weekday_clock
```

Or load a JSON configuration. Individual CLI clock options can override values
from the JSON file:

```powershell
py -3.14 main.py --config clock_config.json --run-duration 30h `
  --output "D:\3D Prints\Clock"
```

With no clock options or configuration file, the application uses the
`ClockConfig` defaults: 30-hour wall clock, deadbeat escapement, and a
220 x 220 x 250 mm bed. The CLI `--help` output documents every setting and its
units.

Example `clock_config.json`:

```json
{
  "run_duration": "8day",
  "case_style": "mantel",
  "escapement": "brocot",
  "pendulum_length_m": 0.25,
  "target_beat_rate_bpm": null,
  "complications": ["moon_phase"],
  "bed_dimensions_mm": [220, 220, 250],
  "nozzle_size_mm": 0.4,
  "clearance_mm": 0.25,
  "case_dimensions_mm": [250, 800, 160],
  "pendulum_bob_diameter_mm": 80,
  "weight_drop_mm": 1800,
  "available_drop_path_mm": 2000,
  "weight_mass_kg": 2,
  "estimated_friction_power_uw": 25,
  "gear_module_mm": null
}
```

Leaving `gear_module_mm` unset selects 0.8 mm for a 30-hour train and 0.55 mm
for an eight-day train to keep the tested wall-clock plates within a 220 mm
build area. Set a positive value to override this sizing.

`target_beat_rate_bpm` means beats per minute (two beats per complete
pendulum period). If supplied, it takes precedence over `pendulum_length_m`.
`case_style` supports `wall`, `mantel` (the library's skeleton mantel plates),
and `round` (fully round, wall-mounted plates). The `moon_phase` complication
is available with wall and mantel plates. `day_of_week` is available with
round plates only, matching the source library's day-complication holder
design. The two complications cannot currently be combined: the source
library's own example records that their joint layout is not yet resolved.
Moon phase on round plates is rejected because the source library produces an
invalid negative geometry dimension for that combination. The day display
uses abbreviated weekday labels.

The library has no calendar date/month complication class. Its striking
mechanism is not exposed: the rack implementation is incomplete, and there is
no completed striking clock assembly in the documented designs. Standalone
whistle/bellows and music-box mechanisms are separate projects, not integrated
clock complications. They are intentionally not offered as completed clock
options. The current generator remains weight-driven; although the source
library documents successful spring-powered clocks, spring-specific train
configuration and power validation have not yet been integrated.

The 2D moon-phase model is marked unfinished upstream and is not exposed. The
round mantel plate class is also excluded because the source marks it as an
experiment that does not work. The currently exposed escapements are
deadbeat (anchor), grasshopper, and Brocot.

This is not yet parity with every source-library option: mainspring drive and
the hand, dial, gear, pillar, and decorative plate style enums are not exposed
as user settings. They need design-specific compatibility checks rather than
being accepted as arbitrary combinations.

The generated directory contains `raw_parts/`, `Plate_1.stl` (and additional
plates when needed), and `build_summary.json`. The packer aligns the largest
coplanar facet of each mesh to the build plate and uses deterministic
first-fit shelf packing with a 2 mm default part-to-part margin. The report
includes the estimated mechanical checks and slicer recommendations.

The local clock library's gear profile and tooth geometry are authoritative.
The reported center distances are nominal module-based values; the adapter
does not convert the library's profiles into involute gears or certify
backlash. Clearances, barrel runtime, weight torque, and support needs require
physical validation with the chosen material, slicer, and clock assembly.

The local `calculate_gears.py` and `power_calculations.py` files are executable
examples with top-level work, not import-safe calculation modules. The adapter
uses the `clocks.GoingTrain` API demonstrated by those examples and applies the
same gravitational potential-energy power estimate in `validator.py` without
executing the scripts during import.
