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

    # Add axes
    plotter.add_axes()

    # Add bounding box info
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


def show_multiple_stl(
    paths: list[Path],
    colors: list[str] | None = None,
) -> None:
    """Show multiple STL files in one viewer.

    Args:
        paths: List of STL file paths
        colors: Optional list of colors per file
    """
    import pyvista as pv

    default_colors = ["lightblue", "salmon", "lightgreen", "gold", "plum"]
    if colors is None:
        colors = default_colors

    plotter = pv.Plotter()
    plotter.set_background("white")

    for i, path in enumerate(paths):
        mesh = pv.read(str(path))
        color = colors[i % len(colors)]
        plotter.add_mesh(mesh, color=color, smooth_shading=True, label=path.stem)

    plotter.add_axes()
    plotter.add_legend()
    plotter.show()
