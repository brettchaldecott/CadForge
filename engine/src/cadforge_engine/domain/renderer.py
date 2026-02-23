"""Headless STL→PNG renderer using PyVista off-screen.

Generates multiple camera angle views of a 3D model for visual QA.
"""

from __future__ import annotations

from pathlib import Path


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
        camera_angles: List of (azimuth, elevation, roll) tuples.
            Defaults to isometric, front, and right side views.
        window_size: Render resolution (width, height).

    Returns:
        List of paths to generated PNG files.
    """
    import pyvista as pv

    # Start virtual framebuffer for headless environments
    try:
        pv.start_xvfb()
    except Exception:
        pass  # Not needed on macOS / systems with display

    if camera_angles is None:
        camera_angles = [
            (45, 30, 0),    # isometric
            (0, 0, 0),      # front
            (90, 0, 0),     # right side
        ]

    view_names = ["isometric", "front", "right"]

    mesh = pv.read(str(stl_path))
    output_paths: list[Path] = []

    for i, (azimuth, elevation, roll) in enumerate(camera_angles):
        view_name = view_names[i] if i < len(view_names) else f"view{i}"
        stem = png_path.stem
        out = png_path.parent / f"{stem}_{view_name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)

        plotter = pv.Plotter(off_screen=True, window_size=window_size)
        plotter.set_background("white")
        plotter.add_mesh(
            mesh,
            color="lightblue",
            show_edges=False,
            smooth_shading=True,
            specular=0.5,
        )
        plotter.add_axes()

        plotter.camera.azimuth = azimuth
        plotter.camera.elevation = elevation
        plotter.camera.roll = roll
        plotter.reset_camera()

        plotter.screenshot(str(out))
        plotter.close()
        output_paths.append(out)

    return output_paths
