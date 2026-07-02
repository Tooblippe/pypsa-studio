from pathlib import Path

import pypsa
import pytest

from pypsa_studio.network_model.pypsa_components import build_network_model
from pypsa_studio.network_model.pypsa_network_exporter import (
    _is_empty_export_value,
    diagram_to_pypsa_network,
    layout_sidecar_path,
    normalize_network_export_format,
)
from pypsa_studio.network_model.pypsa_network_loader import (
    _find_csv_network_dir,
    _safe_relative_path,
    save_upload,
)


def test_normalize_network_export_format_aliases_and_suffixes() -> None:
    """Normalize explicit export names and infer formats from paths."""
    assert normalize_network_export_format("csv-folder", "network") == "csv"
    assert normalize_network_export_format("nc", "network.zip") == "netcdf"
    assert normalize_network_export_format("", "network.nc") == "netcdf"
    assert normalize_network_export_format("", "network.h5") == "hdf5"
    assert normalize_network_export_format("", "network") == "csv"


def test_layout_sidecar_path_for_folder_and_file() -> None:
    """Place layout sidecars inside folders and next to network files."""
    folder_path = Path("exports/demo")
    file_path = Path("exports/demo.nc")

    assert (
        layout_sidecar_path(folder_path)
        == folder_path / "pypsa_network_builder_layout.json"
    )
    assert layout_sidecar_path(file_path) == Path(
        "exports/demo.nc.pypsa_network_builder_layout.json"
    )


def test_empty_export_value_detection() -> None:
    """Detect only values that should be omitted from static PyPSA params."""
    assert _is_empty_export_value(None)
    assert _is_empty_export_value("")
    assert _is_empty_export_value([])
    assert not _is_empty_export_value(0)
    assert not _is_empty_export_value(False)


def test_safe_relative_path_strips_parent_parts() -> None:
    """Sanitize uploaded relative paths without preserving traversal parts."""
    assert _safe_relative_path("../nested/buses.csv") == Path("nested/buses.csv")
    assert _safe_relative_path("..") == Path("uploaded-file")


def test_find_csv_network_dir_finds_nested_folder_and_errors(tmp_path: Path) -> None:
    """Find nested CSV-folder exports and reject unrelated folders."""
    nested = tmp_path / "archive" / "network"
    nested.mkdir(parents=True)
    (nested / "buses.csv").write_text("name\nbus_a\n", encoding="utf-8")

    assert _find_csv_network_dir(tmp_path) == nested

    with pytest.raises(ValueError, match="recognizable PyPSA CSV folder"):
        _find_csv_network_dir(tmp_path / "missing")


def test_save_upload_sanitizes_filename(tmp_path: Path) -> None:
    """Save uploads by basename so client paths cannot choose destinations."""
    saved_path = save_upload("../network.nc", b"network-bytes", tmp_path)

    assert saved_path == tmp_path / "network.nc"
    assert saved_path.read_bytes() == b"network-bytes"


def test_build_network_model_resolves_aliases() -> None:
    """Build component metadata and resolve common component aliases."""
    model = build_network_model(component_refs=["buses", "loads", "generators"])

    assert model.component("bus").component == "buses"
    assert model.component("Bus").component == "buses"
    assert model.component("Load").component == "loads"
    assert "bus" in model.component("loads").attrs


def test_diagram_to_pypsa_network_exports_static_components() -> None:
    """Create a PyPSA network from a small diagram with static values."""
    model = build_network_model(component_refs=["buses", "generators"])
    diagram_model = {
        "components": [
            {"id": "bus_1", "component": "buses", "attrs": {"name": "bus_a"}},
            {
                "id": "generator_1",
                "component": "generators",
                "attrs": {"name": "gen_a", "bus": "bus_a", "p_nom": 10.0},
            },
        ]
    }

    network = diagram_to_pypsa_network(diagram_model, model, "demo")

    assert network.name == "demo"
    assert list(network.buses.index) == ["bus_a"]
    assert list(network.generators.index) == ["gen_a"]
    assert float(network.generators.at["gen_a", "p_nom"]) == 10.0


def test_build_canvas_nodes_from_network_imports_core_components() -> None:
    """Import a small PyPSA network into canvas diagram nodes."""
    from pypsa_studio.state import build_canvas_nodes_from_network

    network = pypsa.Network()
    network.add("Bus", "bus_a")
    network.add("Load", "load_a", bus="bus_a")
    network.add("Generator", "gen_a", bus="bus_a")

    nodes, counters = build_canvas_nodes_from_network(network)
    nodes_by_component = {node["component"]: node for node in nodes}

    assert counters["buses"] == 1
    assert counters["loads"] == 1
    assert counters["generators"] == 1
    assert nodes_by_component["buses"]["attrs"]["name"] == "bus_a"
    assert nodes_by_component["loads"]["attrs"]["bus"] == "bus_a"
    assert nodes_by_component["generators"]["layout"]["bus_side"] == "left"


def test_apply_layout_positions_preserves_saved_layout() -> None:
    """Apply saved builder coordinates and visibility metadata in place."""
    from pypsa_studio.state import apply_layout_positions

    nodes = [
        {
            "id": "bus_1",
            "component": "buses",
            "pypsa_name": "Bus",
            "icon_src": "",
            "icon_svg": "",
            "position": {"x": 0.0, "y": 0.0},
            "layout": {},
            "attrs": {"name": "bus_a"},
            "attr_rows": [],
            "hidden": False,
        }
    ]

    apply_layout_positions(
        nodes,
        {
            ("buses", "bus_a"): {
                "x": 12,
                "y": 34,
                "bus_orientation": "horizontal",
                "locked": True,
                "visible": False,
            }
        },
    )

    assert nodes[0]["position"] == {"x": 12.0, "y": 34.0}
    assert nodes[0]["layout"] == {
        "bus_orientation": "horizontal",
        "locked": True,
        "visible": False,
    }
