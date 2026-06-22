"""Export diagram-model data to PyPSA network files."""

import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pypsa

from pypsa_studio.network_model.pypsa_components import PypsaNetworkModel

LAYOUT_FILE_NAME = "pypsa_network_builder_layout.json"


def export_diagram_to_csv_folder(
    diagram_model: dict[str, Any],
    network_model: PypsaNetworkModel,
    base_folder: str | Path,
    subfolder_name: str = "",
    network_name: str | None = None,
    preserve_source_folder: str | Path | None = None,
    extra_csv_tables: dict[str, dict[str, Any]] | None = None,
) -> Path:
    """Build a PyPSA network from diagram data and export it as a CSV folder."""
    target_folder = _export_target_folder(base_folder, subfolder_name)
    network = diagram_to_pypsa_network(diagram_model, network_model, network_name)

    if preserve_source_folder:
        _copy_preserved_folder(preserve_source_folder, target_folder)
        _overlay_network_csv_export(network, target_folder)
    else:
        _prepare_export_folder(target_folder)
        network.export_to_csv_folder(target_folder)
    _write_extra_csv_tables(target_folder, extra_csv_tables or {})
    _write_layout_sidecar(layout_sidecar_path(target_folder), diagram_model)
    return target_folder


def export_diagram_to_network_path(
    diagram_model: dict[str, Any],
    network_model: PypsaNetworkModel,
    target_path: str | Path,
    export_format: str,
    network_name: str | None = None,
    preserve_source_folder: str | Path | None = None,
    extra_csv_tables: dict[str, dict[str, Any]] | None = None,
) -> Path:
    """Build a PyPSA network from diagram data and export it to the requested path."""
    normalized_format = normalize_network_export_format(export_format, target_path)
    path = Path(target_path).expanduser()

    if normalized_format == "csv":
        return export_diagram_to_csv_folder(
            diagram_model,
            network_model,
            path,
            "",
            network_name,
            preserve_source_folder,
            extra_csv_tables,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    network = diagram_to_pypsa_network(diagram_model, network_model, network_name)
    network = _network_with_extra_csv_tables(network, extra_csv_tables or {})
    if normalized_format == "netcdf":
        network.export_to_netcdf(path)
    elif normalized_format == "hdf5":
        network.export_to_hdf5(path)
    else:
        raise ValueError(f"Unsupported export format: {export_format}")
    _write_layout_sidecar(layout_sidecar_path(path), diagram_model)
    return path


def normalize_network_export_format(
    export_format: str,
    target_path: str | Path,
) -> str:
    """Return the canonical PyPSA export format for a target path."""
    format_text = str(export_format or "").strip().lower()
    if format_text in {"csv", "folder", "csv_folder", "csv-folder"}:
        return "csv"
    if format_text in {"netcdf", "nc"}:
        return "netcdf"
    if format_text in {"hdf5", "h5", "hdf"}:
        return "hdf5"

    suffix = Path(target_path).suffix.lower()
    if suffix == ".nc":
        return "netcdf"
    if suffix in {".h5", ".hdf5"}:
        return "hdf5"
    if not suffix:
        return "csv"
    raise ValueError(f"Unsupported export format for {target_path}.")


def layout_sidecar_path(network_path: str | Path) -> Path:
    """Return the builder layout sidecar path for a folder or network file."""
    path = Path(network_path).expanduser()
    if path.is_dir() or not path.suffix:
        return path / LAYOUT_FILE_NAME
    return path.with_name(f"{path.name}.{LAYOUT_FILE_NAME}")


def diagram_to_pypsa_network(
    diagram_model: dict[str, Any],
    network_model: PypsaNetworkModel,
    network_name: str | None = None,
) -> pypsa.Network:
    """Create a PyPSA network from the app's diagram model."""
    network = pypsa.Network()
    if network_name and network_name.strip():
        network.name = network_name.strip()
    components = list(diagram_model.get("components", []))

    ordered_components = [
        *[
            component
            for component in components
            if component.get("component") == "buses"
        ],
        *[
            component
            for component in components
            if component.get("component") != "buses"
        ],
    ]

    for component_entry in ordered_components:
        component_name = str(component_entry.get("component", ""))
        if component_name not in network_model.all_components:
            continue

        component_type = network_model.component(component_name)
        attrs = component_entry.get("attrs", {})
        if not isinstance(attrs, dict):
            attrs = {}

        component_id = str(component_entry.get("id", ""))
        pypsa_name = str(attrs.get("name") or component_id)
        params = _static_component_params(component_name, attrs, network_model)

        try:
            network.add(component_type.pypsa_name, pypsa_name, **params)
        except Exception as exc:
            msg = (
                f"Could not add {component_type.pypsa_name} '{pypsa_name}' "
                f"from diagram node '{component_id}': {exc}"
            )
            raise ValueError(msg) from exc

    return network


def _static_component_params(
    component_name: str,
    attrs: dict[str, Any],
    network_model: PypsaNetworkModel,
) -> dict[str, Any]:
    """Return static PyPSA parameters suitable for ``Network.add``."""
    component_type = network_model.component(component_name)
    params: dict[str, Any] = {}

    for attr_name, attr_value in attrs.items():
        if attr_name == "name":
            continue
        attr = component_type.attrs.get(str(attr_name))
        if attr is not None and (attr.varying or attr.static is False):
            continue
        if _is_empty_export_value(attr_value):
            continue
        params[str(attr_name)] = attr_value

    return params


def _export_target_folder(base_folder: str | Path, subfolder_name: str) -> Path:
    """Resolve and validate the requested export folder."""
    clean_subfolder = str(subfolder_name).strip()
    if not clean_subfolder:
        return Path(base_folder).expanduser()

    subfolder_path = Path(clean_subfolder)
    if subfolder_path.is_absolute() or ".." in subfolder_path.parts:
        raise ValueError("Use a relative subfolder name without '..'.")

    return Path(base_folder).expanduser() / subfolder_path


def _prepare_export_folder(target_folder: Path) -> None:
    """Create an export folder and remove old PyPSA CSV files from it."""
    target_folder.mkdir(parents=True, exist_ok=True)
    for csv_file in target_folder.glob("*.csv"):
        if csv_file.is_file():
            csv_file.unlink()


def _copy_preserved_folder(source_folder: str | Path, target_folder: Path) -> None:
    """Copy an existing CSV folder into the target before overlaying regenerated files."""
    source = Path(source_folder).expanduser().resolve()
    target = target_folder.expanduser().resolve()
    if not source.exists() or not source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        return
    if source == target:
        target.mkdir(parents=True, exist_ok=True)
        return
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _overlay_network_csv_export(network: pypsa.Network, target_folder: Path) -> None:
    """Write PyPSA-generated CSV files over a preserved folder without deleting extras."""
    target_folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        export_dir = Path(tmp_dir) / "network"
        network.export_to_csv_folder(export_dir)
        for source_file in export_dir.glob("*.csv"):
            shutil.copy2(source_file, target_folder / source_file.name)


def _write_extra_csv_tables(
    target_folder: Path,
    extra_csv_tables: dict[str, dict[str, Any]],
) -> None:
    """Write edited supplemental CSV tables such as carriers, shapes, and sub_networks."""
    if not extra_csv_tables:
        return
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is required to write supplemental CSV tables."
        ) from exc

    target_folder.mkdir(parents=True, exist_ok=True)
    for file_name, table in extra_csv_tables.items():
        columns = [str(column) for column in table.get("columns", [])]
        rows = table.get("rows", [])
        index_values: list[str] = []
        row_values: list[list[Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            index_values.append(str(row.get("id", "")))
            values = row.get("values", [])
            row_values.append(list(values if isinstance(values, list) else []))
        data_frame = pd.DataFrame(row_values, index=index_values, columns=columns)
        index_name = table.get("index_name", "name")
        data_frame.index.name = str(index_name) if index_name else None
        data_frame.to_csv(target_folder / file_name)


def _network_with_extra_csv_tables(
    network: pypsa.Network,
    extra_csv_tables: dict[str, dict[str, Any]],
) -> pypsa.Network:
    """Overlay editable CSV side tables onto a network before file export."""
    if not extra_csv_tables:
        return network
    with tempfile.TemporaryDirectory() as tmp_dir:
        export_dir = Path(tmp_dir) / "network"
        network.export_to_csv_folder(export_dir)
        _write_extra_csv_tables(export_dir, extra_csv_tables)
        enriched_network = pypsa.Network()
        enriched_network.import_from_csv_folder(export_dir)
        return enriched_network


def _write_layout_sidecar(target_folder: Path, diagram_model: dict[str, Any]) -> None:
    """Write builder-only canvas positions next to the PyPSA network export."""
    positions: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    for component in diagram_model.get("components", []):
        if not isinstance(component, dict):
            continue
        attrs = component.get("attrs", {})
        if not isinstance(attrs, dict):
            attrs = {}
        position = component.get("position", {})
        if not isinstance(position, dict):
            continue
        try:
            x = float(position.get("x", 0))
            y = float(position.get("y", 0))
        except TypeError, ValueError:
            continue
        position_entry = {
            "component": str(component.get("component", "")),
            "id": str(component.get("id", "")),
            "name": str(attrs.get("name") or component.get("id", "")),
            "x": x,
            "y": y,
        }
        layout = component.get("layout", {})
        if isinstance(layout, dict):
            bus_side = str(layout.get("bus_side", "")).strip().lower()
            if bus_side in {"left", "right"}:
                position_entry["bus_side"] = bus_side
            if bool(layout.get("locked")):
                position_entry["locked"] = True
            if layout.get("visible") is False:
                position_entry["visible"] = False
        positions.append(position_entry)

    for region in diagram_model.get("regions", []):
        if not isinstance(region, dict):
            continue
        try:
            x = float(region.get("x", 0))
            y = float(region.get("y", 0))
            width = float(region.get("width", 0))
            height = float(region.get("height", 0))
        except TypeError, ValueError:
            continue
        if width <= 0 or height <= 0:
            continue
        regions.append(
            {
                "id": str(region.get("id", "")),
                "name": str(region.get("name", "")),
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "color": str(region.get("color", "") or ""),
                "summary": bool(region.get("summary", False)),
                "summary_node_ids": [
                    str(node_id)
                    for node_id in region.get("summary_node_ids", [])
                    if str(node_id).strip()
                ],
            }
        )

    target_folder.parent.mkdir(parents=True, exist_ok=True)
    target_folder.write_text(
        json.dumps(
            {"version": 3, "positions": positions, "regions": regions},
            indent=2,
        ),
        encoding="utf-8",
    )


def _is_empty_export_value(value: Any) -> bool:
    """Return whether a value should be omitted from PyPSA export params."""
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, list | tuple | dict | set) and len(value) == 0:
        return True
    return False
