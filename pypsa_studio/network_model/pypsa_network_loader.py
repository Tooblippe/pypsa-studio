"""Load PyPSA networks into the app's Pydantic network model."""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import pypsa
from pydantic import BaseModel, ConfigDict, Field

from pypsa_studio.network_model.pypsa_components import (
    PypsaNetworkModel,
    build_network_model,
)


class PypsaLoadedNetwork(BaseModel):
    """Loaded PyPSA network state kept separate from the component definition model."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    network: pypsa.Network = Field(exclude=True)
    source: str | None = None
    current_values: dict[str, dict[str, Any]] = Field(default_factory=dict)
    component_counts: dict[str, int] = Field(default_factory=dict)


def load_pypsa_network(path: str | Path) -> pypsa.Network:
    """Load a PyPSA network from a supported file or CSV folder."""
    network_path = Path(path)
    network = pypsa.Network()

    if network_path.is_dir():
        network.import_from_csv_folder(network_path)
        return network

    suffix = network_path.suffix.lower()
    if suffix == ".nc":
        network.import_from_netcdf(network_path)
        return network
    if suffix in {".h5", ".hdf5"}:
        network.import_from_hdf5(network_path)
        return network
    if suffix == ".zip":
        with tempfile.TemporaryDirectory() as tmp_dir:
            extract_dir = Path(tmp_dir)
            with zipfile.ZipFile(network_path) as archive:
                archive.extractall(extract_dir)
            csv_dir = _find_csv_network_dir(extract_dir)
            network.import_from_csv_folder(csv_dir)
        return network

    msg = (
        "Unsupported PyPSA network format. Use .nc, .h5, .hdf5, a CSV folder, "
        "or a .zip containing a CSV folder export."
    )
    raise ValueError(msg)


def load_pypsa_network_model(path: str | Path) -> PypsaNetworkModel:
    """Return the static PyPSA component definition model.

    Loaded network values are kept in ``PypsaLoadedNetwork`` via
    ``load_pypsa_loaded_network``.
    """
    return build_network_model(network=load_pypsa_network(path))


def load_pypsa_loaded_network(path: str | Path) -> PypsaLoadedNetwork:
    """Load a PyPSA network into a separate loaded-network object."""
    network_path = Path(path)
    return pypsa_network_to_loaded_network(
        load_pypsa_network(network_path),
        source=str(network_path),
    )


def pypsa_network_to_loaded_network(
    network: pypsa.Network,
    source: str | None = None,
) -> PypsaLoadedNetwork:
    """Extract loaded current values without mutating ``PypsaNetworkModel``."""
    definition = build_network_model(network=network)
    current_values: dict[str, dict[str, Any]] = {}
    component_counts: dict[str, int] = {}

    for component_name, component in definition.all_components.items():
        pypsa_component = network.components[component_name]
        static = pypsa_component.static
        component_counts[component_name] = len(static.index)
        current_values[component_name] = {}

        for attr_name, attr in component.attrs.items():
            current_values[component_name][attr_name] = _current_attr_value(
                static,
                attr_name,
                attr.default,
            )

    return PypsaLoadedNetwork(
        network=network,
        source=source,
        current_values=current_values,
        component_counts=component_counts,
    )


def save_upload(file_name: str, data: bytes, upload_dir: str | Path) -> Path:
    """Persist an uploaded network file and return the saved path."""
    upload_path = Path(upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file_name).name
    destination = upload_path / safe_name
    destination.write_bytes(data)
    return destination


def save_uploads_as_csv_folder(
    files: list[tuple[str, bytes]],
    upload_dir: str | Path,
) -> Path:
    """Persist uploaded CSV-folder files and return the reconstructed folder path."""
    upload_path = Path(upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    folder_path = Path(tempfile.mkdtemp(prefix="pypsa-csv-folder-", dir=upload_path))

    for file_name, data in files:
        relative_path = _safe_relative_path(file_name)
        destination = folder_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    return _find_csv_network_dir(folder_path)


def _find_csv_network_dir(root: Path) -> Path:
    """Find the directory that looks like a PyPSA CSV-folder export."""
    if (root / "buses.csv").exists() or (root / "network.csv").exists():
        return root

    candidates = [
        path
        for path in root.rglob("*")
        if path.is_dir()
        and ((path / "buses.csv").exists() or (path / "network.csv").exists())
    ]
    if candidates:
        return candidates[0]

    msg = "Zip file does not contain a recognizable PyPSA CSV folder export."
    raise ValueError(msg)


def _safe_relative_path(file_name: str) -> Path:
    """Return a sanitized relative upload path."""
    path = Path(file_name)
    parts = [
        part
        for part in path.parts
        if part not in {"", ".", ".."} and not Path(part).is_absolute()
    ]
    if not parts:
        return Path("uploaded-file")
    return Path(*parts)


def _current_attr_value(
    static: pd.DataFrame,
    attr_name: str,
    default: Any,
) -> Any:
    """Extract a representative loaded value for a component attribute."""
    if static.empty:
        return default
    if attr_name == "name":
        return _clean_loaded_value(static.index.tolist())
    if attr_name not in static.columns:
        return default

    values = static[attr_name].dropna()
    if values.empty:
        return default

    unique_values = values.drop_duplicates().tolist()
    if len(unique_values) == 1:
        return _clean_loaded_value(unique_values[0])
    return _clean_loaded_value(unique_values)


def _clean_loaded_value(value: Any) -> Any:
    """Convert pandas/numpy loaded values into Pydantic-friendly values."""
    if value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, list):
        return [_clean_loaded_value(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_loaded_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def copy_csv_folder_to_temp(source_dir: str | Path) -> Path:
    """Copy a CSV-folder network to a temporary directory for isolated loading."""
    temp_dir = Path(tempfile.mkdtemp(prefix="pypsa-network-"))
    destination = temp_dir / Path(source_dir).name
    shutil.copytree(source_dir, destination)
    return destination
