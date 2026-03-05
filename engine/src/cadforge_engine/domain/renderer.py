"""Headless STL→PNG renderer using trimesh + pyrender.

Generates multiple camera angle views of a 3D model for visual QA.
Uses pyrender's offscreen renderer (EGL on Linux, osmesa fallback)
which is thread-safe and does not require a display or main-thread access.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def render_stl_to_png(
    stl_path: Path,
    png_path: Path,
    camera_angles: list[tuple[float, float, float]] | None = None,
    window_size: tuple[int, int] = (1024, 768),
) -> list[Path]:
    """Render an STL file to PNG images from multiple camera angles.

    Args:
        stl_path: Path to the input STL file.
        png_path: Base path for output PNGs (suffix replaced with view name).
        camera_angles: List of (azimuth, elevation, roll) tuples in degrees.
            Defaults to isometric, front, and right side views.
        window_size: Render resolution (width, height).

    Returns:
        List of paths to generated PNG files.
    """
    import trimesh
    import pyrender

    import os
    import platform as plat

    # Pick a headless OpenGL backend: osmesa on Linux, skip on macOS
    if plat.system() != "Darwin":
        os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")

    mesh = trimesh.load(str(stl_path))
    if isinstance(mesh, trimesh.Scene):
        meshes = list(mesh.geometry.values())
        if not meshes:
            logger.warning("Empty mesh file: %s", stl_path)
            return []
        mesh = trimesh.util.concatenate(meshes)

    # Build pyrender scene
    pr_mesh = pyrender.Mesh.from_trimesh(
        mesh,
        smooth=True,
        material=pyrender.MetallicRoughnessMaterial(
            baseColorFactor=[0.68, 0.85, 0.90, 1.0],  # lightblue
            metallicFactor=0.2,
            roughnessFactor=0.6,
        ),
    )

    if camera_angles is None:
        camera_angles = [
            (45, 30, 0),    # isometric
            (0, 0, 0),      # front
            (90, 0, 0),     # right side
        ]

    view_names = ["isometric", "front", "right"]

    # Compute camera distance from mesh bounds
    bounds = mesh.bounds
    center = (bounds[0] + bounds[1]) / 2.0
    extent = np.linalg.norm(bounds[1] - bounds[0])
    camera_distance = extent * 1.5

    output_paths: list[Path] = []
    r = pyrender.OffscreenRenderer(
        viewport_width=window_size[0],
        viewport_height=window_size[1],
    )

    try:
        for i, (azimuth, elevation, roll) in enumerate(camera_angles):
            view_name = view_names[i] if i < len(view_names) else f"view{i}"
            stem = png_path.stem
            out = png_path.parent / f"{stem}_{view_name}.png"
            out.parent.mkdir(parents=True, exist_ok=True)

            scene = pyrender.Scene(
                bg_color=[1.0, 1.0, 1.0, 1.0],
                ambient_light=[0.3, 0.3, 0.3],
            )
            scene.add(pr_mesh)

            # Camera pose from azimuth/elevation/roll
            camera_pose = _camera_pose(
                center, camera_distance, azimuth, elevation, roll,
            )
            camera = pyrender.PerspectiveCamera(
                yfov=math.radians(45),
                aspectRatio=window_size[0] / window_size[1],
            )
            scene.add(camera, pose=camera_pose)

            # Key light + fill light
            key_light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0)
            scene.add(key_light, pose=camera_pose)
            fill_pose = _camera_pose(
                center, camera_distance, azimuth + 90, elevation - 15, 0,
            )
            fill_light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=1.5)
            scene.add(fill_light, pose=fill_pose)

            color, _ = r.render(scene)

            # Save via PIL
            from PIL import Image
            img = Image.fromarray(color)
            img.save(str(out))
            output_paths.append(out)

    finally:
        r.delete()

    return output_paths


def _camera_pose(
    center: np.ndarray,
    distance: float,
    azimuth: float,
    elevation: float,
    roll: float,
) -> np.ndarray:
    """Compute a 4x4 camera pose matrix looking at `center`.

    Args:
        center: Target point the camera looks at.
        distance: Distance from center to camera.
        azimuth: Horizontal rotation in degrees.
        elevation: Vertical rotation in degrees.
        roll: Roll rotation in degrees.

    Returns:
        4x4 numpy array (camera-to-world transform).
    """
    az = math.radians(azimuth)
    el = math.radians(elevation)
    ro = math.radians(roll)

    # Camera position on a sphere around center
    x = distance * math.cos(el) * math.sin(az)
    y = distance * math.sin(el)
    z = distance * math.cos(el) * math.cos(az)
    eye = center + np.array([x, y, z])

    # Look-at vectors
    forward = center - eye
    forward = forward / np.linalg.norm(forward)

    world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, world_up)
    if np.linalg.norm(right) < 1e-6:
        world_up = np.array([0.0, 0.0, 1.0])
        right = np.cross(forward, world_up)
    right = right / np.linalg.norm(right)
    up = np.cross(right, forward)
    up = up / np.linalg.norm(up)

    # Apply roll
    if abs(ro) > 1e-6:
        cos_r, sin_r = math.cos(ro), math.sin(ro)
        new_right = cos_r * right + sin_r * up
        new_up = -sin_r * right + cos_r * up
        right, up = new_right, new_up

    # Build camera-to-world matrix (OpenGL convention: -Z forward)
    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = up
    pose[:3, 2] = -forward
    pose[:3, 3] = eye

    return pose
