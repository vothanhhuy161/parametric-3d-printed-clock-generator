"""Orient, pack, and export generated STL parts into printer-sized plates."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class NestingError(RuntimeError):
    """Raised when parts cannot be packed or converted into plate STLs."""


@dataclass
class _Part:
    path: Path
    mesh: Any
    width: float
    height: float
    depth: float
    area: float


@dataclass
class _Placement:
    part: _Part
    x: float
    y: float
    rotated: bool


class NestingExporter:
    """Pack oriented meshes using a deterministic first-fit shelf strategy."""

    def __init__(
        self,
        bed_dimensions_mm: tuple[float, float, float],
        clearance_mm: float = 2.0,
    ):
        self.bed_x, self.bed_y, self.bed_z = bed_dimensions_mm
        self.clearance_mm = clearance_mm
        if min(self.bed_x, self.bed_y, self.bed_z) <= 0:
            raise ValueError("Bed dimensions must be positive.")
        if clearance_mm < 0:
            raise ValueError("Nesting clearance cannot be negative.")

    def export(
        self,
        part_paths: list[str | Path],
        output_directory: str | Path,
        config: dict[str, Any],
        gear_pairs: list[dict[str, Any]],
        validation: dict[str, Any],
        powered_wheel_ratios: list[list[int]] | None = None,
    ) -> list[Path]:
        """Pack all raw STL parts and write plate STLs plus build_summary.json."""
        try:
            import numpy as np
            import trimesh
        except ImportError as exc:
            raise NestingError(
                "trimesh and numpy are required for plate nesting."
            ) from exc

        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)
        parts = [
            self._load_part(Path(path), trimesh, np)
            for path in part_paths
            if Path(path).suffix.lower() == ".stl"
        ]
        if not parts:
            raise NestingError("No STL parts were provided for nesting.")
        parts.sort(
            key=lambda part: (max(part.width, part.height), part.area),
            reverse=True,
        )

        plates: list[list[_Placement]] = []
        shelves: list[list[tuple[float, float, float]]] = []
        for part in parts:
            if part.depth > self.bed_z:
                raise NestingError(
                    f"{part.path.name} is {part.depth:.1f} mm tall, exceeding the "
                    f"{self.bed_z:.1f} mm bed Z limit."
                )
            placement = self._place_part(part, plates, shelves)
            if placement is None:
                raise NestingError(
                    f"{part.path.name} ({part.width:.1f} x {part.height:.1f} mm) "
                    "does not fit on the configured X/Y bed, even when rotated."
                )

        written: list[Path] = []
        part_records: list[dict[str, Any]] = []
        for plate_index, placements in enumerate(plates, 1):
            positioned_meshes = []
            for placement in placements:
                mesh = placement.part.mesh.copy()
                if placement.rotated:
                    mesh.apply_transform(
                        trimesh_transform_rotation_z(np, 90.0)
                    )
                bounds = mesh.bounds
                mesh.apply_translation(
                    (
                        placement.x - bounds[0, 0],
                        placement.y - bounds[0, 1],
                        -bounds[0, 2],
                    )
                )
                positioned_meshes.append(mesh)
                part_records.append(
                    {
                        "file": placement.part.path.name,
                        "plate": plate_index,
                        "x_mm": round(placement.x, 3),
                        "y_mm": round(placement.y, 3),
                        "rotated_90_deg": placement.rotated,
                        "bounds_mm": [
                            round(placement.part.width, 3),
                            round(placement.part.height, 3),
                            round(placement.part.depth, 3),
                        ],
                    }
                )
            plate_mesh = trimesh.util.concatenate(positioned_meshes)
            plate_file = output_path / f"Plate_{plate_index}.stl"
            try:
                plate_mesh.export(str(plate_file), file_type="stl")
            except Exception as exc:
                raise NestingError(
                    f"Unable to export '{plate_file}': {exc}"
                ) from exc
            written.append(plate_file)

        metadata = {
            "upstream_library": {
                "name": "3DPrintedClocks",
                "author": "Luke Wallin",
                "source": "https://github.com/MrBunsy/3DPrintedClocks",
                "license": "CERN-OHL-S v2",
                "license_url": "https://ohwr.org/cern_ohl_s_v2.txt",
            },
            "configuration": config,
            "validation": validation,
            "design_comparison": validation.get("design_comparison"),
            "gear_pairs": gear_pairs,
            "powered_wheel_ratios": powered_wheel_ratios or [],
            "printer_bed_mm": {
                "x": self.bed_x,
                "y": self.bed_y,
                "z": self.bed_z,
            },
            "nesting_clearance_mm": self.clearance_mm,
            "plates": len(plates),
            "parts": part_records,
            "slicer_recommendations": {
                "gears": {
                    "infill_percent": 100,
                    "wall_loops": 4,
                    "supports": "Inspect each gear and arbor in the slicer.",
                },
                "structural_parts": {
                    "infill_percent": "30-50",
                    "wall_loops": 4,
                    "supports": "Inspect plate, dial, and pendulum orientations.",
                },
                "nozzle_size_mm": config.get("nozzle_size_mm"),
                "clearance_mm": config.get("clearance_mm"),
                "note": (
                    "Support needs and gear infill are recommendations; verify "
                    "each part and material in the target slicer."
                ),
            },
        }
        summary_path = output_path / "build_summary.json"
        try:
            summary_path.write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise NestingError(
                f"Unable to write build metadata '{summary_path}': {exc}"
            ) from exc
        written.append(summary_path)
        return written

    def _load_part(self, path: Path, trimesh: Any, np: Any) -> _Part:
        if not path.is_file():
            raise NestingError(f"STL part does not exist: {path}")
        try:
            mesh = trimesh.load(str(path), force="mesh")
            if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
                raise ValueError("STL contains no mesh geometry")
            self._orient_largest_facet(mesh, np)
            mesh.apply_translation(-mesh.bounds[0])
        except Exception as exc:
            raise NestingError(f"Unable to load/orient '{path}': {exc}") from exc
        extents = mesh.extents
        return _Part(
            path=path,
            mesh=mesh,
            width=float(extents[0]),
            height=float(extents[1]),
            depth=float(extents[2]),
            area=float(extents[0] * extents[1]),
        )

    @staticmethod
    def _orient_largest_facet(mesh: Any, np: Any) -> None:
        """Put the largest coplanar surface facet parallel to the build plate."""
        areas = mesh.facets_area
        normals = mesh.facets_normal
        if len(areas) == 0:
            return
        normal = normals[int(np.argmax(areas))]
        target = np.array([0.0, 0.0, 1.0])
        dot = float(np.clip(np.dot(normal, target), -1.0, 1.0))
        if dot > 1.0 - 1e-8:
            return
        if dot < -1.0 + 1e-8:
            mesh.apply_transform(trimesh_transform_rotation_x(np, 180.0))
            return
        axis = np.cross(normal, target)
        axis /= np.linalg.norm(axis)
        angle = float(np.arccos(dot))
        mesh.apply_transform(trimesh_axis_angle_transform(np, axis, angle))

    def _place_part(
        self,
        part: _Part,
        plates: list[list[_Placement]],
        shelves: list[list[tuple[float, float, float]]],
    ) -> _Placement | None:
        margin = self.clearance_mm
        for plate_index, plate_shelves in enumerate(shelves):
            for shelf_index, (shelf_y, shelf_height, used_x) in enumerate(plate_shelves):
                for rotated in (False, True):
                    width, height = (
                        (part.height, part.width) if rotated else (part.width, part.height)
                    )
                    if (
                        used_x + margin + width <= self.bed_x
                        and shelf_height >= height
                    ):
                        x = used_x + margin
                        placement = _Placement(part, x, shelf_y, rotated)
                        plates[plate_index].append(placement)
                        plate_shelves[shelf_index] = (
                            shelf_y,
                            shelf_height,
                            x + width,
                        )
                        return placement
            next_y = max(
                (shelf_y + height for shelf_y, height, _ in plate_shelves),
                default=margin,
            ) + margin
            for rotated in (False, True):
                width, height = (
                    (part.height, part.width) if rotated else (part.width, part.height)
                )
                if (
                    width + 2 * margin <= self.bed_x
                    and next_y + height + margin <= self.bed_y
                ):
                    plates[plate_index].append(
                        _Placement(part, margin, next_y, rotated)
                    )
                    plate_shelves.append((next_y, height, margin + width))
                    return plates[plate_index][-1]

        for rotated in (False, True):
            width, height = (
                (part.height, part.width) if rotated else (part.width, part.height)
            )
            if width + 2 * margin <= self.bed_x and height + 2 * margin <= self.bed_y:
                plates.append([_Placement(part, margin, margin, rotated)])
                shelves.append([(margin, height, margin + width)])
                return plates[-1][-1]
        return None


def trimesh_transform_rotation_z(np: Any, degrees: float) -> Any:
    """Build a homogeneous rotation matrix about Z without extra dependencies."""
    angle = np.deg2rad(degrees)
    cosine, sine = float(np.cos(angle)), float(np.sin(angle))
    return np.array(
        [
            [cosine, -sine, 0.0, 0.0],
            [sine, cosine, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def trimesh_transform_rotation_x(np: Any, degrees: float) -> Any:
    """Build a homogeneous rotation matrix about X."""
    angle = np.deg2rad(degrees)
    cosine, sine = float(np.cos(angle)), float(np.sin(angle))
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, cosine, -sine, 0.0],
            [0.0, sine, cosine, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def trimesh_axis_angle_transform(np: Any, axis: Any, angle: float) -> Any:
    """Build a homogeneous transform rotating around an arbitrary axis."""
    x, y, z = (float(component) for component in axis)
    cosine, sine = float(np.cos(angle)), float(np.sin(angle))
    one_minus_cosine = 1.0 - cosine
    rotation = np.array(
        [
            [
                cosine + x * x * one_minus_cosine,
                x * y * one_minus_cosine - z * sine,
                x * z * one_minus_cosine + y * sine,
            ],
            [
                y * x * one_minus_cosine + z * sine,
                cosine + y * y * one_minus_cosine,
                y * z * one_minus_cosine - x * sine,
            ],
            [
                z * x * one_minus_cosine - y * sine,
                z * y * one_minus_cosine + x * sine,
                cosine + z * z * one_minus_cosine,
            ],
        ]
    )
    transform = np.eye(4)
    transform[:3, :3] = rotation
    return transform
