"""Export diagram-model data to PyPSA network files."""

from pathlib import Path
from typing import Any

import pypsa

from pypsa_network_builder_v2.network_model.pypsa_components import PypsaNetworkModel


def export_diagram_to_csv_folder(
    diagram_model: dict[str, Any],
    network_model: PypsaNetworkModel,
    base_folder: str | Path,
    subfolder_name: str = "",
    network_name: str | None = None,
) -> Path:
    """Build a PyPSA network from diagram data and export it as a CSV folder."""
    target_folder = _export_target_folder(base_folder, subfolder_name)
    network = diagram_to_pypsa_network(diagram_model, network_model, network_name)

    _prepare_export_folder(target_folder)
    network.export_to_csv_folder(target_folder)
    return target_folder


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
        *[component for component in components if component.get("component") == "buses"],
        *[component for component in components if component.get("component") != "buses"],
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


def _is_empty_export_value(value: Any) -> bool:
    """Return whether a value should be omitted from PyPSA export params."""
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, list | tuple | dict | set) and len(value) == 0:
        return True
    return False
