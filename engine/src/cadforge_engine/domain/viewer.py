"""PyVista-based 3D viewer for STL files."""

from __future__ import annotations

from pathlib import Path


def show_stl(
    path: Path,
    color: str = "lightblue",
    background: str = "white",
    window_size: tuple[int, int] = (1024, 768),
) -> None:
    """Open an interactive 3D viewer for an STL file.

    Args:
        path: Path to the STL file
        color: Mesh color
        background: Background color
        window_size: Window dimensions (width, height)
    """
    import pyvista as pv

    mesh = pv.read(str(path))

    plotter = pv.Plotter(window_size=window_size)
    plotter.set_background(background)
    plotter.add_mesh(
        mesh,
        color=color,
        show_edges=False,
        smooth_shading=True,
        specular=0.5,
    )

    plotter.add_axes()

    bounds = mesh.bounds
    size_x = bounds[1] - bounds[0]
    size_y = bounds[3] - bounds[2]
    size_z = bounds[5] - bounds[4]
    plotter.add_text(
        f"{path.name}\n{size_x:.1f} x {size_y:.1f} x {size_z:.1f} mm",
        position="upper_left",
        font_size=10,
    )

    plotter.show()
