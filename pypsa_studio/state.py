import asyncio
import copy
import io
import json
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from collections.abc import AsyncGenerator
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import pandas as pd
import pypsa
import reflex as rx
import plotly.graph_objects as go

from pypsa_studio.constants import (
    APP_SETTINGS_FILE,
    APP_STATE_DIR,
    BUILDER_LOAD_FOLDER_UPLOAD_ID,
    BUILDER_LOAD_UPLOAD_ID,
    CANVAS_HISTORY_LIMIT,
    CSV_TABLE_COMPONENTS,
    EDITABLE_CSV_UPLOAD_ID,
    EXPORTS_DIR,
    FOLDER_UPLOAD_ID,
    JS_ELK_ROUTER_NAME,
    JUPYTER_EXECUTION_TIMEOUT_SECONDS,
    JUPYTER_NOTEBOOKS_DIR,
    JUPYTER_ROOT_DIR,
    JUPYTER_RUNTIME_DIR,
    JUPYTER_START_TIMEOUT_SECONDS,
    NETWORK_MODEL,
    NETWORK_OBJECT_DISPLAY_LIMIT,
    OTHER_TABLE_COMPONENTS,
    PROJECT_ROOT,
    PYTHON_ROUTERS,
    REFERENCE_ATTR_TABLES,
    ROUTER_OPTIONS,
    SETTINGS_DIR,
    SETTINGS_FILE,
    SNAPSHOT_TABLE_COLUMNS,
    SNAPSHOT_TABLE_COMPONENTS,
    SNAPSHOT_TABLE_INDEX_NAMES,
    SUPPORTED_NETWORK_FILE_SUFFIXES,
    TEST_NETWORKS_DIR,
    UPLOAD_ID,
)
from pypsa_studio.network_model import (
    ComponentType,
    PypsaLoadedNetwork,
    PypsaNetworkModel,
    export_diagram_to_network_path,
    layout_sidecar_path,
    load_pypsa_network,
    normalize_network_export_format,
    pypsa_network_to_loaded_network,
    save_upload,
    save_uploads_as_csv_folder,
)
from pypsa_studio.routers import (
    RouterNetwork,
)
from pypsa_studio.types import (
    AttrRow,
    CanvasRegion,
    CanvasSnapshot,
    CarrierVisibilityRow,
    ComponentRow,
    DiagramAttr,
    DiagramEdge,
    DiagramModel,
    DiagramNode,
    ExampleNetworkGroup,
    FilePickerEntry,
    NetworkDataCell,
    NetworkDataColumn,
    NetworkDataComponentSetting,
    NetworkDataRow,
    NetworkDataTab,
    NetworkLoadArtifacts,
    NetworkObjectComponentRow,
    NetworkObjectConnectionRow,
    OtherCsvTable,
    OtherTableCell,
    OtherTableRow,
    RouterOption,
    SettingField,
    SettingsTab,
    StandardTypeRow,
)

BUS_COMPONENT_HORIZONTAL_OFFSET = 75.0
BUS_COMPONENT_DROP_OFFSET = 60.0
DEFAULT_CANVAS_REGION_COLOR = "#2563eb"
CANVAS_REGION_COLORS = {
    "#2563eb",
    "#16a34a",
    "#d97706",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
    "#4b5563",
}
CANVAS_REGION_NODE_SIZES = {
    "buses": (24.0, 92.0),
    "bus": (24.0, 92.0),
    "generators": (44.0, 64.0),
    "generator": (44.0, 64.0),
    "loads": (42.0, 68.0),
    "load": (42.0, 68.0),
    "storage_units": (44.0, 72.0),
    "storage_unit": (44.0, 72.0),
    "stores": (50.0, 72.0),
    "store": (50.0, 72.0),
}
FILE_PICKER_MAX_ENTRIES = 500
FILE_PICKER_SAVE_FORMATS = {"csv", "netcdf", "hdf5"}
FILE_PICKER_SUPPORTED_SUFFIXES = {".nc", ".h5", ".hdf5"}
NETWORK_DATA_SETTINGS_SECTION = "network_data"
NETWORK_DATA_SETTINGS_COMPONENTS_KEY = "components"
NETWORK_DATA_EXTRA_COMPONENT_LABELS = {
    "snapshots": "Snapshots",
    "investment_periods": "Investment Periods",
}


def clean_upload_staging_dir(upload_dir: str | Path) -> None:
    """Remove staged upload files from the Reflex upload directory."""
    upload_path = Path(upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    for child in upload_path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


_JUPYTER_PROCESS: subprocess.Popen[str] | None = None
_JUPYTER_BASE_URL = ""


def _notebook_source_for_network(network_path: Path) -> str:
    """Return notebook code that loads and prints a PyPSA network."""
    return f"""from pathlib import Path
import tempfile
import zipfile

import pypsa


NETWORK_PATH = Path(r"{network_path}").expanduser()


def load_network(path: Path) -> pypsa.Network:
    n = pypsa.Network()
    if path.is_dir():
        n.import_from_csv_folder(path)
        return n

    suffix = path.suffix.lower()
    if suffix == ".nc":
        n.import_from_netcdf(path)
        return n
    if suffix in {{".h5", ".hdf5"}}:
        n.import_from_hdf5(path)
        return n
    if suffix == ".zip":
        with tempfile.TemporaryDirectory() as tmp_dir:
            extract_dir = Path(tmp_dir)
            with zipfile.ZipFile(path) as archive:
                archive.extractall(extract_dir)
            candidates = [
                candidate
                for candidate in [extract_dir, *extract_dir.rglob("*")]
                if candidate.is_dir()
                and ((candidate / "buses.csv").exists() or (candidate / "network.csv").exists())
            ]
            if not candidates:
                raise ValueError("Zip file does not contain a recognizable PyPSA CSV folder export.")
            n.import_from_csv_folder(candidates[0])
            return n

    raise ValueError(f"Unsupported PyPSA network path: {{path}}")


n = load_network(NETWORK_PATH)
print(n)
n
"""


def create_jupyter_network_notebook(network_path: Path) -> Path:
    """Create a notebook under .jupyter that loads the given network."""
    JUPYTER_NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", network_path.stem or "network").strip(
        "-"
    )
    notebook_path = JUPYTER_NOTEBOOKS_DIR / f"open-{safe_stem}-{int(time.time())}.ipynb"
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": _notebook_source_for_network(network_path),
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path.write_text(json.dumps(notebook, indent=2), encoding="utf-8")
    return notebook_path


def execute_jupyter_network_notebook(notebook_path: Path) -> None:
    """Run the generated notebook's first cell and persist its output."""
    import nbformat
    from nbclient import NotebookClient

    notebook = nbformat.read(notebook_path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=JUPYTER_EXECUTION_TIMEOUT_SECONDS,
        kernel_name="python3",
        resources={"metadata": {"path": str(PROJECT_ROOT)}},
    )
    client.execute()
    nbformat.write(notebook, notebook_path)


def _extract_jupyter_url(output_line: str) -> str:
    """Extract the first local Jupyter URL from server output."""
    match = re.search(r"https?://(?:localhost|127\.0\.0\.1):\d+/\S*", output_line)
    return match.group(0).rstrip() if match else ""


def _ensure_jupyter_lab_server() -> str:
    """Start or reuse a JupyterLab server and return its base URL."""
    global _JUPYTER_BASE_URL, _JUPYTER_PROCESS

    if (
        _JUPYTER_PROCESS is not None
        and _JUPYTER_PROCESS.poll() is None
        and _JUPYTER_BASE_URL
    ):
        return _JUPYTER_BASE_URL

    JUPYTER_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    JUPYTER_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "jupyter",
        "lab",
        "--no-browser",
        "--ServerApp.open_browser=False",
        f"--ServerApp.root_dir={JUPYTER_ROOT_DIR}",
        f"--ServerApp.runtime_dir={JUPYTER_RUNTIME_DIR}",
    ]
    _JUPYTER_PROCESS = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=PROJECT_ROOT,
    )

    output: list[str] = []
    output_queue: queue.Queue[str] = queue.Queue()

    def read_output() -> None:
        if _JUPYTER_PROCESS.stdout is None:
            return
        try:
            for line in _JUPYTER_PROCESS.stdout:
                output_queue.put(line)
        except Exception:
            return

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + JUPYTER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            line = output_queue.get(timeout=0.2)
        except queue.Empty:
            line = ""
        if line:
            output.append(line)
            url = _extract_jupyter_url(line)
            if url:
                _JUPYTER_BASE_URL = url
                return _JUPYTER_BASE_URL
            continue
        if _JUPYTER_PROCESS.poll() is not None:
            break
        time.sleep(0.1)

    exit_code = _JUPYTER_PROCESS.poll()
    detail = "".join(output[-8:]).strip()
    if exit_code is not None:
        raise RuntimeError(f"JupyterLab exited before it published a URL. {detail}")
    raise RuntimeError(f"Timed out waiting for JupyterLab to start. {detail}")


def _start_jupyter_output_drain(process: subprocess.Popen[str]) -> None:
    """Drain Jupyter output after startup so the server cannot block on a full pipe."""
    if process.stdout is None:
        return

    def drain() -> None:
        try:
            for _ in process.stdout:
                pass
        except Exception:
            return

    threading.Thread(target=drain, daemon=True).start()


def jupyter_lab_notebook_url(notebook_path: Path) -> str:
    """Return a JupyterLab URL that opens the generated notebook."""
    base_url = _ensure_jupyter_lab_server()
    split_url = urlsplit(base_url)
    query_items = dict(parse_qsl(split_url.query, keep_blank_values=True))
    relative_path = notebook_path.relative_to(JUPYTER_ROOT_DIR).as_posix()
    path = "/lab/tree/" + quote(relative_path, safe="/")
    return urlunsplit(
        (
            split_url.scheme,
            split_url.netloc,
            path,
            urlencode(query_items),
            "",
        )
    )


def _pretty_example_label(label: str) -> str:
    """Format example labels for display in the network menu."""
    parts = []
    for part in Path(label).as_posix().split("/"):
        stem, dot, suffix = part.rpartition(".")
        if dot:
            part = f"{stem.replace('_', ' ').title()}{dot}{suffix}"
        else:
            part = part.replace("_", " ").title()
        parts.append(part)
    return "/".join(parts)


def discover_pypsa_example_networks() -> list[ExampleNetworkGroup]:
    """Return test networks grouped by top-level directory."""
    if not TEST_NETWORKS_DIR.exists():
        return []
    groups: list[ExampleNetworkGroup] = []
    for directory in sorted(TEST_NETWORKS_DIR.iterdir()):
        if not directory.is_dir():
            continue
        network_paths = [
            path
            for path in sorted([directory, *directory.rglob("*")])
            if (
                path.is_file()
                and path.suffix.lower() in SUPPORTED_NETWORK_FILE_SUFFIXES
            )
            or (
                path.is_dir()
                and ((path / "buses.csv").exists() or (path / "network.csv").exists())
            )
        ]
        networks = [
            {
                "label": _pretty_example_label(path.relative_to(directory).as_posix()),
                "path": str(path),
            }
            for path in network_paths
        ]
        if networks:
            groups.append(
                {"label": _pretty_example_label(directory.name), "networks": networks}
            )
    return groups


PYPSA_EXAMPLE_NETWORKS = discover_pypsa_example_networks()


def load_csv_folder_network(
    csv_folder: Path,
) -> tuple[pypsa.Network, PypsaLoadedNetwork]:
    """Load a PyPSA CSV folder and derived metadata off the Reflex event loop."""
    network = pypsa.Network()
    try:
        network.import_from_csv_folder(csv_folder)
    except Exception:
        network = pypsa.Network()
        static_csv_folder = copy_static_csv_folder_for_pypsa_import(csv_folder)
        network.import_from_csv_folder(static_csv_folder)
    loaded_network = pypsa_network_to_loaded_network(
        network,
        source=str(csv_folder),
    )
    return network, loaded_network


def load_network_file(network_path: Path) -> tuple[pypsa.Network, PypsaLoadedNetwork]:
    """Load a PyPSA network file and derived metadata off the Reflex event loop."""
    path = Path(network_path).expanduser()
    network = load_pypsa_network(path)
    loaded_network = pypsa_network_to_loaded_network(network, source=str(path))
    return network, loaded_network


def is_pypsa_csv_folder(path: Path) -> bool:
    """Return whether a path looks like a local PyPSA CSV folder."""
    folder = Path(path).expanduser()
    return folder.is_dir() and (
        (folder / "buses.csv").exists() or (folder / "network.csv").exists()
    )


def read_last_network_folder() -> Path | None:
    """Read the last successfully loaded local network folder from app settings."""
    try:
        payload = json.loads(APP_SETTINGS_FILE.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    folder = str(payload.get("last_network_folder", "")).strip()
    if not folder:
        return None
    return Path(folder).expanduser()


def write_last_network_folder(csv_folder: Path) -> None:
    """Persist the last successfully loaded local network folder."""
    APP_STATE_DIR.mkdir(parents=True, exist_ok=True)
    APP_SETTINGS_FILE.write_text(
        json.dumps(
            {"last_network_folder": str(Path(csv_folder).expanduser())}, indent=2
        ),
        encoding="utf-8",
    )


def network_save_format_for_path(network_path: str | Path) -> str:
    """Infer the save format represented by a PyPSA network path."""
    path = Path(network_path).expanduser()
    if path.is_dir() or not path.suffix:
        return "csv"
    if path.suffix.lower() == ".nc":
        return "netcdf"
    if path.suffix.lower() in {".h5", ".hdf5"}:
        return "hdf5"
    return ""


def file_picker_home_path() -> Path:
    """Return the platform home path used as the picker starting location."""
    try:
        return Path.home().expanduser()
    except RuntimeError:
        return Path.cwd()


def read_file_picker_last_path() -> Path:
    """Read the last file picker path from settings.toml."""
    try:
        with open(SETTINGS_FILE, "rb") as fh:
            data = tomllib.load(fh)
    except OSError:
        return file_picker_home_path()
    except tomllib.TOMLDecodeError:
        return file_picker_home_path()

    path_text = str(data.get("FilePicker", {}).get("Last_path", "")).strip()
    if not path_text:
        return file_picker_home_path()
    path = Path(path_text).expanduser()
    if path.exists():
        return path
    return file_picker_home_path()


def file_picker_start_dir() -> Path:
    """Return the directory where the picker should initially open."""
    last_path = read_file_picker_last_path()
    if last_path.is_file():
        return last_path.parent
    if last_path.is_dir():
        return last_path
    return file_picker_home_path()


def file_picker_root_entries() -> list[FilePickerEntry]:
    """Return root locations available to the server-side file picker."""
    roots: list[Path] = []
    if sys.platform.startswith("win"):
        for drive_code in range(ord("A"), ord("Z") + 1):
            drive = Path(f"{chr(drive_code)}:/")
            if drive.exists():
                roots.append(drive)
    else:
        roots.append(Path("/"))

    home = file_picker_home_path()
    entries = [
        {
            "name": "Home",
            "path": str(home),
            "kind": "folder",
            "icon": "home",
            "selectable": False,
            "modified": "",
            "size": "",
        }
    ]
    for root in roots:
        entries.append(
            {
                "name": str(root),
                "path": str(root),
                "kind": "folder",
                "icon": "hard-drive",
                "selectable": False,
                "modified": "",
                "size": "",
            }
        )
    return entries


def format_file_picker_size(path: Path) -> str:
    """Return a compact file size label for a picker row."""
    if path.is_dir():
        return ""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return ""


def format_file_picker_modified(path: Path) -> str:
    """Return a compact modified timestamp label for a picker row."""
    try:
        modified = path.stat().st_mtime
    except OSError:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(modified))


def file_picker_entry_for_path(
    path: Path, mode: str, save_format: str
) -> FilePickerEntry:
    """Build one file picker row for a filesystem path."""
    is_directory = path.is_dir()
    suffix = path.suffix.lower()
    supported_file = suffix in FILE_PICKER_SUPPORTED_SUFFIXES
    if is_directory:
        selectable = mode == "load" or (
            mode in {"save", "save_as"} and save_format == "csv"
        )
        kind = "folder"
        icon = "folder"
    else:
        selectable = supported_file and (
            mode == "load"
            or (save_format == "netcdf" and suffix == ".nc")
            or (save_format == "hdf5" and suffix in {".h5", ".hdf5"})
        )
        kind = "file"
        icon = "file"

    return {
        "name": path.name or str(path),
        "path": str(path),
        "kind": kind,
        "icon": icon,
        "selectable": selectable,
        "modified": format_file_picker_modified(path),
        "size": format_file_picker_size(path),
    }


def scan_file_picker_directory(
    directory: str | Path,
    mode: str,
    save_format: str,
    show_hidden: bool = False,
) -> tuple[list[FilePickerEntry], str, str]:
    """Return visible picker entries, warning text, and error text for a directory."""
    current_dir = Path(directory).expanduser()
    try:
        children = list(current_dir.iterdir())
    except OSError as exc:
        return [], "", f"Could not read {current_dir}: {exc}"

    visible: list[Path] = []
    for child in children:
        if not show_hidden and child.name.startswith("."):
            continue
        if child.is_dir() or child.suffix.lower() in FILE_PICKER_SUPPORTED_SUFFIXES:
            visible.append(child)

    visible.sort(key=lambda path: (not path.is_dir(), path.name.lower()))
    warning = ""
    if len(visible) > FILE_PICKER_MAX_ENTRIES:
        warning = f"Showing first {FILE_PICKER_MAX_ENTRIES} entries in this folder."
        visible = visible[:FILE_PICKER_MAX_ENTRIES]

    return (
        [file_picker_entry_for_path(path, mode, save_format) for path in visible],
        warning,
        "",
    )


def default_save_file_name(network_name: str, save_format: str) -> str:
    """Return a safe default file name for a network file save."""
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", network_name or "network").strip("-.")
    if not safe_stem:
        safe_stem = "network"
    if save_format == "netcdf":
        return f"{safe_stem}.nc"
    if save_format == "hdf5":
        return f"{safe_stem}.h5"
    return safe_stem


def apply_save_format_extension(target_path: Path, save_format: str) -> Path:
    """Ensure a file save path has the extension required by its selected format."""
    if save_format == "netcdf" and target_path.suffix.lower() != ".nc":
        return target_path.with_suffix(".nc")
    if save_format == "hdf5" and target_path.suffix.lower() not in {".h5", ".hdf5"}:
        return target_path.with_suffix(".h5")
    return target_path


def write_file_picker_last_path(path: str | Path) -> None:
    """Persist the last file picker path to settings.toml."""
    if not SETTINGS_FILE.exists():
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        data: dict[str, dict[str, object]] = {}
    else:
        try:
            with open(SETTINGS_FILE, "rb") as fh:
                raw_data = tomllib.load(fh)
        except OSError:
            raw_data = {}
        except tomllib.TOMLDecodeError:
            raw_data = {}
        data = {
            str(section): {
                str(key): value
                for key, value in pairs.items()
                if isinstance(pairs, dict)
            }
            for section, pairs in raw_data.items()
            if isinstance(pairs, dict)
        }

    data.setdefault("FilePicker", {})["Last_path"] = str(Path(path).expanduser())
    _write_toml_file(data)


def _default_network_data_settings_toml() -> str:
    """Return the default ordered Network Data component settings TOML."""
    data = {
        NETWORK_DATA_SETTINGS_SECTION: {
            NETWORK_DATA_SETTINGS_COMPONENTS_KEY: [
                {
                    "component": component_name,
                    "show_in_editor": True,
                    "show_on_sld": True,
                }
                for component_name in NETWORK_MODEL.all_components
            ]
            + [
                {
                    "component": component_name,
                    "show_in_editor": True,
                    "show_on_sld": True,
                }
                for component_name in NETWORK_DATA_EXTRA_COMPONENT_LABELS
            ]
        }
    }
    lines: list[str] = []
    for row in data[NETWORK_DATA_SETTINGS_SECTION][
        NETWORK_DATA_SETTINGS_COMPONENTS_KEY
    ]:
        lines.append(f"[[{NETWORK_DATA_SETTINGS_SECTION}.components]]")
        lines.append(f'component = "{row["component"]}"')
        lines.append("show_in_editor = true")
        lines.append("show_on_sld = true")
        lines.append("")
    return "\n" + "\n".join(lines).rstrip("\n") + "\n"


def network_data_component_label(component_name: str) -> str:
    """Return the display label for a Network Data settings component."""
    component = NETWORK_MODEL.all_components.get(component_name)
    if component is not None:
        return component.pypsa_name
    return NETWORK_DATA_EXTRA_COMPONENT_LABELS.get(component_name, component_name)


def is_network_data_settings_component(component_name: str) -> bool:
    """Return whether a component name can be configured for Network Data."""
    return (
        component_name in NETWORK_MODEL.all_components
        or component_name in NETWORK_DATA_EXTRA_COMPONENT_LABELS
    )


def network_data_settings_component_names() -> list[str]:
    """Return all component names managed by Network Data settings."""
    return [
        *NETWORK_MODEL.all_components.keys(),
        *NETWORK_DATA_EXTRA_COMPONENT_LABELS.keys(),
    ]


def _format_toml_scalar(value: object) -> str:
    """Return one scalar value formatted for TOML output."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_toml_list(lines: list[str], key: str, values: list[object]) -> None:
    """Append a TOML list value to a list of output lines."""
    lines.append(f"{key} = [")
    for index, value in enumerate(values):
        suffix = "," if index < len(values) - 1 else ""
        lines.append(f"  {_format_toml_scalar(value)}{suffix}")
    lines.append("]")


def _write_toml_file(data: dict[str, dict[str, object]]) -> None:
    """Write a nested dict as a TOML file to SETTINGS_FILE."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, pairs in data.items():
        array_tables: dict[str, list[dict[str, object]]] = {}
        scalar_pairs: dict[str, object] = {}
        for key, value in pairs.items():
            if isinstance(value, list) and all(isinstance(v, dict) for v in value):
                array_tables[key] = [
                    {str(item_key): item_value for item_key, item_value in item.items()}
                    for item in value
                ]
            else:
                scalar_pairs[key] = value

        if scalar_pairs:
            lines.append(f"[{section}]")
            for key, value in scalar_pairs.items():
                if isinstance(value, list):
                    _write_toml_list(lines, key, value)
                else:
                    lines.append(f"{key} = {_format_toml_scalar(value)}")
            lines.append("")

        for key, rows in array_tables.items():
            for row in rows:
                lines.append(f"[[{section}.{key}]]")
                for row_key, row_value in row.items():
                    if isinstance(row_value, list):
                        _write_toml_list(lines, row_key, row_value)
                    else:
                        lines.append(f"{row_key} = {_format_toml_scalar(row_value)}")
                lines.append("")
    SETTINGS_FILE.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def copy_static_csv_folder_for_pypsa_import(csv_folder: Path) -> Path:
    """Copy static CSV files to a temp folder for PyPSA imports that reject time indexes."""
    source = Path(csv_folder).expanduser()
    target = Path(tempfile.mkdtemp(prefix="pypsa-static-import-"))
    excluded = {"snapshots.csv", "investment_periods.csv"}
    for csv_file in source.glob("*.csv"):
        file_name = csv_file.name
        if file_name in excluded or "-" in csv_file.stem:
            continue
        shutil.copy2(csv_file, target / file_name)
    return target


def is_valid_pypsa_csv_folder(csv_folder: Path) -> bool:
    """Return whether a folder looks like a PyPSA CSV export folder."""
    if not csv_folder.exists() or not csv_folder.is_dir():
        return False
    component_files = {
        "buses.csv",
        "generators.csv",
        "loads.csv",
        "lines.csv",
        "links.csv",
        "stores.csv",
        "storage_units.csv",
        "transformers.csv",
    }
    return (csv_folder / "network.csv").is_file() and any(
        (csv_folder / file_name).is_file() for file_name in component_files
    )


def format_current_value(value: object) -> str:
    """Format an attribute value for compact display in select labels."""
    if value is None:
        return "None"
    if value == "":
        return "empty"
    if isinstance(value, list):
        if not value:
            return ""
        preview = ", ".join(str(item) for item in value[:3])
        suffix = ", ..." if len(value) > 3 else ""
        return f"{preview}{suffix}"
    return str(value)


def attr_label(attr: dict[str, object], current_value: object) -> str:
    """Build the displayed label for a PyPSA attribute option."""
    return (
        f"{attr['name']} ({attr['type'] or 'any'}) "
        f"[{format_current_value(current_value)}]"
    )


def component_to_row(
    component: ComponentType,
    loaded_network: PypsaLoadedNetwork | None = None,
) -> ComponentRow:
    """Convert component metadata into a UI row structure."""
    icon_src = (
        f"data:{component.icon.media_type};utf8,{quote(component.icon.svg)}"
        if component.icon.svg
        else ""
    )
    attrs: list[AttrRow] = []
    for attr in component.formatted_attrs():
        is_time_series = attr["varying"] or "series" in str(attr["type"]).lower()
        current_value = (
            loaded_network.current_values.get(component.component, {}).get(
                attr["name"],
                attr["default"],
            )
            if loaded_network is not None
            else attr["default"]
        )
        attrs.append(
            {
                "name": attr["name"],
                "label": attr_label(attr, current_value),
                "is_time_series": is_time_series,
            }
        )

    return {
        "component": component.component,
        "pypsa_name": component.pypsa_name,
        "icon_src": icon_src,
        "icon_svg": component.icon.svg or "",
        "attrs": attrs,
        "default_attr": attrs[0]["name"] if attrs else "",
    }


def icon_row(component_name: str, pypsa_name: str) -> ComponentRow:
    """Build a palette row for a non-PyPSA-component icon."""
    icon_path = (
        Path(__file__).parent / "network_model" / "icons" / f"{component_name}.svg"
    )
    icon_svg = (
        icon_path.read_text(encoding="utf-8").strip() if icon_path.exists() else ""
    )
    icon_src = f"data:image/svg+xml;utf8,{quote(icon_svg)}" if icon_svg else ""
    return {
        "component": component_name,
        "pypsa_name": pypsa_name,
        "icon_src": icon_src,
        "icon_svg": icon_svg,
        "attrs": [],
        "default_attr": "",
    }


def palette_groups() -> dict[str, list[ComponentRow]]:
    """Return the component groups shown in the builder palette."""
    return filter_palette_groups_for_sld(
        model_sections(NETWORK_MODEL),
        network_data_settings_lookup_from_file(),
    )


def network_data_settings_lookup_from_file() -> dict[str, NetworkDataComponentSetting]:
    """Return Network Data settings from settings.toml keyed by component name."""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "rb") as fh:
            raw = tomllib.load(fh)
    except OSError, tomllib.TOMLDecodeError:
        return {}

    section = raw.get(NETWORK_DATA_SETTINGS_SECTION, {})
    if not isinstance(section, dict):
        return {}
    raw_rows = section.get(NETWORK_DATA_SETTINGS_COMPONENTS_KEY, [])
    if not isinstance(raw_rows, list):
        return {}

    rows: dict[str, NetworkDataComponentSetting] = {}
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        component_name = str(raw_row.get("component", "")).strip()
        if not is_network_data_settings_component(component_name):
            continue
        rows[component_name] = {
            "component": component_name,
            "label": network_data_component_label(component_name),
            "show_in_editor": bool(raw_row.get("show_in_editor", True)),
            "show_on_sld": bool(raw_row.get("show_on_sld", True)),
        }
    return rows


def filter_component_rows_for_sld(
    rows: list[ComponentRow],
    settings_by_component: dict[str, NetworkDataComponentSetting],
) -> list[ComponentRow]:
    """Return only component rows configured as visible on the SLD palette."""
    return [
        row
        for row in rows
        if settings_by_component.get(
            row["component"],
            {
                "component": row["component"],
                "label": row["pypsa_name"],
                "show_in_editor": True,
                "show_on_sld": True,
            },
        )["show_on_sld"]
    ]


def filter_palette_groups_for_sld(
    groups: dict[str, list[ComponentRow]],
    settings_by_component: dict[str, NetworkDataComponentSetting],
) -> dict[str, list[ComponentRow]]:
    """Return palette groups filtered by configured SLD visibility."""
    return {
        section: filter_component_rows_for_sld(rows, settings_by_component)
        for section, rows in groups.items()
    }


def component_defaults(component: ComponentType) -> dict[str, object]:
    """Return default static attribute values for a component type."""
    return {attr_name: attr.default for attr_name, attr in component.attrs.items()}


def attr_input_type(pypsa_type: str | None, python_type: str | None) -> str:
    """Map PyPSA/Python type metadata to a simple editor input type."""
    type_text = f"{pypsa_type or ''} {python_type or ''}".lower()
    if "bool" in type_text:
        return "boolean"
    if "float" in type_text or "int" in type_text:
        return "number"
    return "text"


def clean_numeric_text(value: object) -> object:
    """Return numeric text without thousands separators."""
    if isinstance(value, str):
        return value.replace(",", "").strip()
    return value


def format_numeric_display_value(value: object) -> str:
    """Format a numeric editor value with thousands separators."""
    text = str(value if value is not None else "").strip()
    if text == "":
        return ""
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return text
    if not number.is_finite():
        return text
    if number == number.to_integral_value():
        return f"{int(number):,}"
    return f"{number:,.12f}".rstrip("0").rstrip(".")


def network_data_display_value(value: object, input_type: str) -> str:
    """Return the formatted Network Data editor value."""
    if input_type == "number":
        return format_numeric_display_value(value)
    return str(value if value is not None else "")


def is_bus_reference_attr(attr_name: str) -> bool:
    """Return whether an attribute name refers to a bus endpoint."""
    return attr_name == "bus" or (
        attr_name.startswith("bus") and attr_name[3:].isdigit()
    )


def standard_type_names(component_name: str) -> list[str]:
    """Return available standard type names for PyPSA type-backed components."""
    if component_name == "lines":
        return [str(name) for name in pypsa.Network().line_types.index]
    if component_name == "transformers":
        return [str(name) for name in pypsa.Network().transformer_types.index]
    return []


def standard_type_rows(component_name: str) -> list[StandardTypeRow]:
    """Return display rows for PyPSA standard line or transformer type tables."""
    if component_name == "line_types":
        data_frame = pypsa.Network().line_types
    elif component_name == "transformer_types":
        data_frame = pypsa.Network().transformer_types
    else:
        return []

    rows: list[StandardTypeRow] = []
    for name, row in data_frame.iterrows():
        rows.append(
            {
                "name": str(name),
                "values": [
                    format_current_value(clean_imported_value(value))
                    for column, value in row.items()
                    if str(column) != "references"
                ],
            }
        )
    return rows


def standard_type_columns(component_name: str) -> list[str]:
    """Return parameter column names for PyPSA standard type tables."""
    if component_name == "line_types":
        return [
            str(column)
            for column in pypsa.Network().line_types.columns
            if str(column) != "references"
        ]
    if component_name == "transformer_types":
        return [
            str(column)
            for column in pypsa.Network().transformer_types.columns
            if str(column) != "references"
        ]
    return []


def default_other_table_columns(component_name: str) -> list[str]:
    """Return PyPSA static columns for supplemental Other CSV tables."""
    if component_name in SNAPSHOT_TABLE_COLUMNS:
        return SNAPSHOT_TABLE_COLUMNS[component_name]
    if component_name not in OTHER_TABLE_COMPONENTS:
        return []
    return [
        str(column)
        for column in pypsa.Network().components[component_name].static.columns
    ]


def table_cell_value(value: object) -> str:
    """Convert a pandas table value into an editable string."""
    try:
        if pd.isna(value):
            return ""
    except TypeError, ValueError:
        pass
    return str(value)


def table_index_value(value: object) -> str:
    """Convert a pandas index value, including MultiIndex tuples, into a row id."""
    if isinstance(value, tuple):
        return ", ".join(table_cell_value(item) for item in value)
    return table_cell_value(value)


def plot_numeric_value(value: object) -> float | None:
    """Return a numeric Plotly value or None for blanks/non-numeric cells."""
    text = table_cell_value(value).strip()
    if not text:
        return None
    try:
        numeric_value = float(text)
    except ValueError:
        return None
    if pd.isna(numeric_value):
        return None
    return numeric_value


def dataframe_to_other_csv_table(
    component_name: str,
    data_frame: pd.DataFrame,
) -> OtherCsvTable:
    """Convert a loaded supplemental CSV DataFrame into editable UI table data."""
    columns = [str(column) for column in data_frame.columns]
    rows: list[OtherTableRow] = []
    for row_index, (index_value, row) in enumerate(data_frame.iterrows()):
        rows.append(
            {
                "row_index": row_index,
                "id": table_index_value(index_value),
                "cells": [
                    {
                        "row_index": row_index,
                        "column": column,
                        "value": table_cell_value(row[column]),
                    }
                    for column in columns
                ],
            }
        )
    return {
        "component": component_name,
        "file_name": CSV_TABLE_COMPONENTS.get(component_name, f"{component_name}.csv"),
        "columns": columns,
        "rows": rows,
        "index_name": SNAPSHOT_TABLE_INDEX_NAMES.get(component_name, "name"),
        "loaded": True,
        "dirty": False,
    }


def empty_other_csv_table(component_name: str) -> OtherCsvTable:
    """Return an empty editable supplemental CSV table."""
    columns = default_other_table_columns(component_name)
    return {
        "component": component_name,
        "file_name": CSV_TABLE_COMPONENTS[component_name],
        "columns": columns,
        "rows": [],
        "index_name": SNAPSHOT_TABLE_INDEX_NAMES.get(component_name, "name"),
        "loaded": False,
        "dirty": False,
    }


def load_other_csv_tables(csv_folder: Path) -> dict[str, OtherCsvTable]:
    """Load supplemental Other CSVs that the canvas does not model directly."""
    tables: dict[str, OtherCsvTable] = {}
    for component_name, file_name in CSV_TABLE_COMPONENTS.items():
        csv_path = csv_folder / file_name
        if csv_path.exists():
            data_frame = pd.read_csv(csv_path, index_col=0, dtype=str).fillna("")
            tables[component_name] = dataframe_to_other_csv_table(
                component_name,
                data_frame,
            )
        else:
            tables[component_name] = empty_other_csv_table(component_name)
    return tables


def dataframe_to_time_series_table(
    component_name: str,
    attr_name: str,
    data_frame: pd.DataFrame,
    dirty: bool = False,
) -> OtherCsvTable:
    """Convert a component time-series CSV into editable table data."""
    table = dataframe_to_other_csv_table(
        f"{component_name}:{attr_name}",
        data_frame,
    )
    table["file_name"] = f"{component_name}-{attr_name}.csv"
    table["index_name"] = "snapshot"
    table["dirty"] = dirty
    return table


def load_time_series_csv_tables(csv_folder: Path) -> dict[str, OtherCsvTable]:
    """Load component-attribute time-series CSVs from a PyPSA CSV folder."""
    tables: dict[str, OtherCsvTable] = {}
    for csv_path in csv_folder.glob("*.csv"):
        stem = csv_path.stem
        if "-" not in stem:
            continue
        component_name, attr_name = stem.split("-", 1)
        if component_name not in NETWORK_MODEL.all_components:
            continue
        component = NETWORK_MODEL.component(component_name)
        if attr_name not in component.attrs:
            continue
        try:
            data_frame = pd.read_csv(csv_path, index_col=0, dtype=str).fillna("")
        except Exception:
            continue
        tables[f"{component_name}:{attr_name}"] = dataframe_to_time_series_table(
            component_name,
            attr_name,
            data_frame,
        )
    return tables


def load_time_series_network_tables(
    network: pypsa.Network,
) -> dict[str, OtherCsvTable]:
    """Extract editable time-series tables from a loaded PyPSA network object."""
    tables: dict[str, OtherCsvTable] = {}
    network_components = getattr(network, "components", {})
    network_component_names = set(network_components.keys())
    for component_name, component in NETWORK_MODEL.all_components.items():
        if component_name not in network_component_names:
            continue
        pypsa_component = network_components[component_name]
        dynamic_tables = getattr(pypsa_component, "dynamic", {})
        if not hasattr(dynamic_tables, "items"):
            continue
        for attr_name, data_frame in dynamic_tables.items():
            attr_name = str(attr_name)
            if attr_name not in component.attrs:
                continue
            if isinstance(data_frame, pd.Series):
                data_frame = data_frame.to_frame()
            if not isinstance(data_frame, pd.DataFrame) or data_frame.empty:
                continue
            table = dataframe_to_time_series_table(
                component_name,
                attr_name,
                data_frame.copy().fillna(""),
            )
            tables[f"{component_name}:{attr_name}"] = table
    return tables


def load_network_artifacts(network_path: str | Path) -> NetworkLoadArtifacts:
    """Load a PyPSA network and all editable side tables used by the UI."""
    path = Path(network_path).expanduser()
    if path.is_dir():
        network, loaded_network = load_csv_folder_network(path)
        time_series_tables = load_time_series_csv_tables(path)
        if not time_series_tables:
            time_series_tables = load_time_series_network_tables(network)
        return {
            "network": network,
            "loaded_network": loaded_network,
            "other_csv_tables": load_other_csv_tables(path),
            "time_series_tables": time_series_tables,
        }

    network = load_pypsa_network(path)
    loaded_network = pypsa_network_to_loaded_network(network, source=str(path))
    return {
        "network": network,
        "loaded_network": loaded_network,
        "other_csv_tables": {},
        "time_series_tables": load_time_series_network_tables(network),
    }


def load_layout_positions(
    network_path: Path,
) -> dict[tuple[str, str], dict[str, object]]:
    """Load saved builder canvas layout keyed by component and PyPSA name."""
    layout_path = layout_sidecar_path(network_path)
    if not layout_path.exists():
        return {}
    try:
        payload = json.loads(layout_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}

    positions: dict[tuple[str, str], dict[str, object]] = {}
    entries = payload.get("positions", []) if isinstance(payload, dict) else []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        component_name = str(entry.get("component", "")).strip()
        pypsa_name = str(entry.get("name", "")).strip()
        if not component_name or not pypsa_name:
            continue
        try:
            layout_entry: dict[str, object] = {
                "x": float(entry.get("x", 0)),
                "y": float(entry.get("y", 0)),
            }
        except TypeError, ValueError:
            continue
        bus_side = normalize_bus_side(entry.get("bus_side"))
        if bus_side:
            layout_entry["bus_side"] = bus_side
        if bool(entry.get("locked")):
            layout_entry["locked"] = True
        if entry.get("visible") is False:
            layout_entry["visible"] = False
        positions[(component_name, pypsa_name)] = layout_entry
    return positions


def load_layout_regions(network_path: Path) -> list[CanvasRegion]:
    """Load saved builder canvas regions from the layout sidecar."""
    layout_path = layout_sidecar_path(network_path)
    if not layout_path.exists():
        return []
    try:
        payload = json.loads(layout_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return []

    regions: list[CanvasRegion] = []
    entries = payload.get("regions", []) if isinstance(payload, dict) else []
    for index, entry in enumerate(entries if isinstance(entries, list) else []):
        if not isinstance(entry, dict):
            continue
        try:
            x = float(entry.get("x", 0))
            y = float(entry.get("y", 0))
            width = float(entry.get("width", 0))
            height = float(entry.get("height", 0))
        except TypeError, ValueError:
            continue
        if width <= 0 or height <= 0:
            continue
        region_id = str(entry.get("id", "")).strip() or f"region-{index + 1}"
        name = str(entry.get("name", "")).strip() or f"Region {index + 1}"
        color = normalize_canvas_region_color(entry.get("color"))
        summary_node_ids = [
            str(node_id)
            for node_id in entry.get("summary_node_ids", [])
            if str(node_id).strip()
        ]
        regions.append(
            {
                "id": region_id,
                "name": name,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "color": color,
                "summary": bool(entry.get("summary", False)),
                "summary_node_ids": summary_node_ids,
            }
        )
    return regions


def normalize_canvas_region_color(value: object) -> str:
    """Return a supported canvas region color."""
    color = str(value or "").strip().lower()
    if color in CANVAS_REGION_COLORS:
        return color
    return DEFAULT_CANVAS_REGION_COLOR


def apply_layout_positions(
    diagram_nodes: list[DiagramNode],
    layout_positions: dict[tuple[str, str], dict[str, object]],
) -> None:
    """Apply saved builder layout metadata to imported diagram nodes in place."""
    if not layout_positions:
        return
    for node in diagram_nodes:
        attrs = node.get("attrs", {})
        pypsa_name = (
            str(attrs.get("name") or node["id"])
            if isinstance(attrs, dict)
            else node["id"]
        )
        position = layout_positions.get((node["component"], pypsa_name))
        if position is not None:
            node["position"] = {
                "x": float(position["x"]),
                "y": float(position["y"]),
            }
            bus_side = normalize_bus_side(position.get("bus_side"))
            if bus_side:
                layout = node.setdefault("layout", {})
                if isinstance(layout, dict):
                    layout["bus_side"] = bus_side
            if bool(position.get("locked")):
                layout = node.setdefault("layout", {})
                if isinstance(layout, dict):
                    layout["locked"] = True
            if position.get("visible") is False:
                layout = node.setdefault("layout", {})
                if isinstance(layout, dict):
                    layout["visible"] = False
    apply_bus_side_layout_from_positions(diagram_nodes)


def diagram_attr_rows(
    component: ComponentType, attrs: dict[str, object]
) -> list[DiagramAttr]:
    """Build editable attribute rows for a diagram component."""
    rows: list[DiagramAttr] = []
    for attr_name, attr in component.attrs.items():
        pypsa_type = attr.pypsa_type or "any"
        is_reference_attr = attr_name in REFERENCE_ATTR_TABLES
        options = (
            standard_type_names(component.component)
            if attr_name == "type" and component.component in {"lines", "transformers"}
            else []
        )
        rows.append(
            {
                "name": attr_name,
                "value": attrs.get(attr_name, attr.default),
                "type": pypsa_type,
                "input_type": (
                    "reference"
                    if is_reference_attr
                    else (
                        "select"
                        if options
                        else attr_input_type(attr.pypsa_type, attr.python_type)
                    )
                ),
                "is_time_series": bool(attr.varying)
                or "series" in str(attr.pypsa_type).lower(),
                "has_time_series_table": False,
                "has_time_series_value": False,
                "is_bus_reference": is_bus_reference_attr(attr_name),
                "options": options,
            }
        )
    return rows


def is_canvas_data_component(component_name: str) -> bool:
    """Return whether component rows are represented by diagram nodes."""
    if component_name == "buses":
        return True
    component = NETWORK_MODEL.all_components.get(component_name)
    if component is None:
        return False
    return any(is_bus_reference_attr(attr_name) for attr_name in component.attrs)


def editable_component_attr_names(component: ComponentType) -> list[str]:
    """Return editable PyPSA input attrs shown by the network data dialog."""
    attr_names: list[str] = []
    for attr_name, attr in component.attrs.items():
        if attr_name == "references":
            continue
        status = str(attr.status or "").lower()
        if not status.startswith("input"):
            continue
        if attr.static is not True:
            continue
        attr_names.append(attr_name)
    return attr_names


def network_data_column_for_attr(
    component_name: str,
    attr_name: str,
) -> NetworkDataColumn:
    """Build network data grid metadata for one editable attr."""
    component = NETWORK_MODEL.component(component_name)
    attr = component.attrs[attr_name]
    options = (
        standard_type_names(component.component)
        if attr_name == "type" and component.component in {"lines", "transformers"}
        else []
    )
    is_reference_attr = attr_name in REFERENCE_ATTR_TABLES
    return {
        "component": component_name,
        "name": attr_name,
        "type": attr.pypsa_type or "any",
        "input_type": (
            "reference"
            if is_reference_attr
            else (
                "select"
                if options
                else attr_input_type(attr.pypsa_type, attr.python_type)
            )
        ),
        "is_time_series": bool(attr.varying)
        or "series" in str(attr.pypsa_type).lower(),
        "is_bus_reference": is_bus_reference_attr(attr_name),
        "options": options,
    }


def network_data_columns(component_name: str) -> list[NetworkDataColumn]:
    """Return columns for the component network data grid, excluding name."""
    if component_name in SNAPSHOT_TABLE_COLUMNS:
        return [
            {
                "component": component_name,
                "name": column_name,
                "type": "string",
                "input_type": "text",
                "is_time_series": False,
                "is_bus_reference": False,
                "options": [],
            }
            for column_name in SNAPSHOT_TABLE_COLUMNS[component_name]
        ]
    component = NETWORK_MODEL.component(component_name)
    return [
        network_data_column_for_attr(component_name, attr_name)
        for attr_name in editable_component_attr_names(component)
        if attr_name != "name"
    ]


def network_data_file_name(component_name: str) -> str:
    """Return the CSV file name for a PyPSA component table."""
    return CSV_TABLE_COMPONENTS.get(component_name, f"{component_name}.csv")


def network_data_index_name(component_name: str) -> str:
    """Return the CSV index name for a PyPSA component table."""
    return SNAPSHOT_TABLE_INDEX_NAMES.get(component_name, "name")


def dataframe_to_network_data_table(
    component_name: str,
    data_frame: pd.DataFrame,
    dirty: bool = False,
    loaded: bool = True,
) -> OtherCsvTable:
    """Convert a static PyPSA component DataFrame into editable table state."""
    columns = [
        column["name"]
        for column in network_data_columns(component_name)
        if column["name"] in data_frame.columns
    ]
    rows: list[OtherTableRow] = []
    for row_index, (index_value, row) in enumerate(data_frame.iterrows()):
        rows.append(
            {
                "row_index": row_index,
                "id": "" if pd.isna(index_value) else str(index_value),
                "cells": [
                    {
                        "row_index": row_index,
                        "column": column,
                        "value": "" if pd.isna(row[column]) else str(row[column]),
                    }
                    for column in columns
                ],
            }
        )
    return {
        "component": component_name,
        "file_name": network_data_file_name(component_name),
        "columns": columns,
        "rows": rows,
        "index_name": network_data_index_name(component_name),
        "loaded": loaded,
        "dirty": dirty,
    }


def empty_network_data_table(component_name: str) -> OtherCsvTable:
    """Return an empty editable table for a non-canvas PyPSA component."""
    return {
        "component": component_name,
        "file_name": network_data_file_name(component_name),
        "columns": [column["name"] for column in network_data_columns(component_name)],
        "rows": [],
        "index_name": network_data_index_name(component_name),
        "loaded": False,
        "dirty": False,
    }


def make_diagram_node(
    component_name: str,
    node_id: str,
    x: float,
    y: float,
) -> DiagramNode:
    """Create a visible diagram node from component metadata."""
    component = NETWORK_MODEL.component(component_name)
    attrs = component_defaults(component)
    row = component_to_row(component)
    bus_side = default_bus_side_for_component(component_name)
    return {
        "id": node_id,
        "component": component.component,
        "pypsa_name": component.pypsa_name,
        "icon_src": row["icon_src"],
        "icon_svg": row["icon_svg"],
        "position": {"x": x, "y": y},
        "layout": {"bus_side": bus_side} if bus_side else {},
        "attrs": attrs,
        "attr_rows": diagram_attr_rows(component, attrs),
        "hidden": False,
    }


def network_import_order() -> list[str]:
    """Return component list names in bus, branch, component import order."""
    branch_components = [
        component_name
        for component_name in NETWORK_MODEL.branch_components
        if component_name in NETWORK_MODEL.all_components
    ]
    remaining_components = [
        component_name
        for component_name, component in NETWORK_MODEL.all_components.items()
        if component_name != "buses"
        and component_name not in branch_components
        and has_bus_attr(component)
    ]
    return ["buses", *branch_components, *remaining_components]


def clean_imported_value(value: object) -> object:
    """Convert pandas/numpy imported values into JSON-friendly objects."""
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except TypeError, ValueError:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except TypeError, ValueError:
            pass
    return value


def attrs_from_network_row(
    component_type: ComponentType,
    pypsa_name: object,
    row: object,
) -> dict[str, object]:
    """Convert a PyPSA static component row to diagram attributes."""
    attrs = component_defaults(component_type)
    attrs["name"] = str(pypsa_name)

    for attr_name in component_type.attrs:
        if attr_name == "name":
            continue
        if attr_name in row.index:
            attrs[attr_name] = clean_imported_value(row[attr_name])

    return attrs


def component_id_prefix(component_name: str) -> str:
    """Return the default node-id prefix for a PyPSA component list name."""
    singular_prefixes = {
        "processes": "process",
    }
    if component_name in singular_prefixes:
        return singular_prefixes[component_name]
    if component_name == "buses":
        return "bus"
    return component_name[:-1] if component_name.endswith("s") else component_name


def normalize_bus_side(value: object) -> str:
    """Return a valid bus side value or an empty string."""
    side = str(value or "").strip().lower()
    return side if side in {"left", "right"} else ""


def is_canvas_visible(node: DiagramNode | dict[str, object]) -> bool:
    """Return whether a diagram node should be visibly rendered on the canvas."""
    layout = node.get("layout", {})
    if not isinstance(layout, dict):
        return True
    return layout.get("visible") is not False


def default_bus_side_for_component(component_name: str) -> str:
    """Return the default visual bus side for a bus-attached component."""
    if component_name == "generators":
        return "left"
    if component_name in {"loads", "stores", "storage_units"}:
        return "right"
    return ""


def apply_bus_side_layout_from_positions(diagram_nodes: list[DiagramNode]) -> None:
    """Infer bus-side layout metadata from current node positions."""
    bus_nodes_by_name: dict[str, DiagramNode] = {
        str(node["attrs"].get("name") or node["id"]): node
        for node in diagram_nodes
        if node["component"] == "buses"
    }
    for node in diagram_nodes:
        attrs = node.get("attrs", {})
        if node["component"] == "buses" or not isinstance(attrs, dict):
            continue
        bus_node = bus_nodes_by_name.get(str(attrs.get("bus", "")))
        if bus_node is None:
            continue
        node_x = float(node["position"].get("x", 0))
        bus_x = float(bus_node["position"].get("x", 0))
        node.setdefault("layout", {})["bus_side"] = (
            "left" if node_x < bus_x else "right"
        )


def next_import_node_id(counters: dict[str, int], component_name: str) -> str:
    """Allocate the next stable imported node id for a component type."""
    next_count = counters.get(component_name, 0) + 1
    counters[component_name] = next_count
    return f"{component_id_prefix(component_name)}_{next_count}"


def import_position_for_component(
    component_name: str,
    row_index: int,
    x_positions: dict[str, int],
    attrs: dict[str, object],
    bus_positions: dict[str, dict[str, float]],
    bus_component_counts: dict[str, int],
) -> tuple[float, float]:
    """Choose an initial canvas position for an imported component."""
    lane = x_positions.get(component_name, 0)
    x_positions[component_name] = lane + 1
    if component_name == "buses":
        return 260 + lane * 180, 120
    if component_name in NETWORK_MODEL.branch_components:
        return 0, 0

    bus_name = str(attrs.get("bus", ""))
    bus_position = bus_positions.get(bus_name)
    if bus_position is not None:
        bus_count = bus_component_counts.get(bus_name, 0)
        bus_component_counts[bus_name] = bus_count + 1
        y_offset = (bus_count % 5) * 74 - 148
        if component_name == "generators":
            return (
                bus_position["x"] - BUS_COMPONENT_HORIZONTAL_OFFSET,
                bus_position["y"] + y_offset,
            )
        return (
            bus_position["x"] + BUS_COMPONENT_HORIZONTAL_OFFSET,
            bus_position["y"] + y_offset,
        )

    return 160 + (row_index % 6) * 120, 420 + (row_index // 6) * 100


def diagram_node_from_imported_attrs(
    component_type: ComponentType,
    attrs: dict[str, object],
    x: float,
    y: float,
    hidden: bool,
    counters: dict[str, int],
) -> DiagramNode:
    """Create a diagram node from imported PyPSA attributes."""
    node_id = next_import_node_id(counters, component_type.component)
    row_component = component_to_row(component_type)
    bus_side = default_bus_side_for_component(component_type.component)
    return {
        "id": node_id,
        "component": component_type.component,
        "pypsa_name": component_type.pypsa_name,
        "icon_src": row_component["icon_src"],
        "icon_svg": row_component["icon_svg"],
        "position": {"x": float(x), "y": float(y)},
        "layout": {"bus_side": bus_side} if bus_side else {},
        "attrs": attrs,
        "attr_rows": diagram_attr_rows(component_type, attrs),
        "hidden": hidden,
    }


def build_canvas_nodes_from_network(
    network: pypsa.Network,
) -> tuple[list[DiagramNode], dict[str, int]]:
    """Build canvas nodes from a loaded PyPSA network off the event loop."""
    imported_nodes: list[DiagramNode] = []
    bus_positions: dict[str, dict[str, float]] = {}
    bus_component_counts: dict[str, int] = {}
    component_counters: dict[str, int] = {}
    x_positions: dict[str, int] = {}

    for component_name in network_import_order():
        if component_name not in NETWORK_MODEL.all_components:
            continue
        if component_name not in network.components.keys():
            continue

        component_type = NETWORK_MODEL.component(component_name)
        static = network.components[component_name].static
        if static.empty:
            continue

        for row_index, (pypsa_name, row) in enumerate(static.iterrows()):
            attrs = attrs_from_network_row(component_type, pypsa_name, row)
            x, y = import_position_for_component(
                component_name,
                row_index,
                x_positions,
                attrs,
                bus_positions,
                bus_component_counts,
            )
            node = diagram_node_from_imported_attrs(
                component_type,
                attrs,
                x,
                y,
                hidden=component_name in NETWORK_MODEL.branch_components,
                counters=component_counters,
            )
            imported_nodes.append(node)
            if component_name == "buses":
                bus_positions[str(attrs["name"])] = node["position"]

    return imported_nodes, component_counters


def has_bus_attr(component: ComponentType) -> bool:
    """Return whether a component type has any bus reference attribute."""
    return any(
        attr_name == "bus" or (attr_name.startswith("bus") and attr_name[3:].isdigit())
        for attr_name in component.attrs
    )


def model_sections(
    network_model: PypsaNetworkModel,
    loaded_network: PypsaLoadedNetwork | None = None,
) -> dict[str, list[ComponentRow]]:
    """Group component metadata into builder and catalog sections."""
    components = list(network_model.all_components.values())
    fundamental_components = [network_model.buses]
    branch_components = [
        component
        for component in components
        if component.is_branch_component
        and has_bus_attr(component)
        and component.component != "buses"
    ]
    bus_components = [
        component
        for component in components
        if not component.is_branch_component
        and has_bus_attr(component)
        and component.component != "buses"
    ]
    other_components = [
        component
        for component in components
        if not has_bus_attr(component) and component.component != "buses"
    ]
    standard_type_components = [
        component
        for component in other_components
        if component.component in {"line_types", "transformer_types"}
    ]
    other_components = [
        component
        for component in other_components
        if component.component not in {"line_types", "transformer_types"}
    ]
    delayed_primary_components = {
        "global_constraints",
        "shunt_impedances",
        "processes",
    }
    delayed_other_components = {
        "global_constraints",
        "shunt_impedances",
        "processes",
    }
    other_components = [
        *[
            component
            for component in other_components
            if component.component not in delayed_other_components
        ],
        *[
            component
            for component in other_components
            if component.component in delayed_other_components
        ],
    ]

    return {
        "fundamental": [
            component_to_row(component, loaded_network)
            for component in fundamental_components
        ],
        "primary_components": [
            component_to_row(component, loaded_network)
            for component in bus_components
            if component.component not in delayed_primary_components
        ],
        "primary_branch_components": [
            component_to_row(component, loaded_network)
            for component in branch_components
            if component.component not in delayed_primary_components
        ],
        "delayed_components": [
            component_to_row(component, loaded_network)
            for component in bus_components
            if component.component in delayed_primary_components
        ],
        "delayed_branch_components": [
            component_to_row(component, loaded_network)
            for component in branch_components
            if component.component in delayed_primary_components
        ],
        "components": [
            component_to_row(component, loaded_network) for component in bus_components
        ],
        "branch_components": [
            component_to_row(component, loaded_network)
            for component in branch_components
        ],
        "other": [
            component_to_row(component, loaded_network)
            for component in other_components
        ],
        "standard_types": [
            component_to_row(component, loaded_network)
            for component in standard_type_components
        ],
        "snapshot_tables": [
            icon_row("snapshots", "Snapshots"),
            icon_row("investment_periods", "Investment Periods"),
        ],
    }


class State(rx.State):
    """Application state."""

    sections: dict[str, list[ComponentRow]] = model_sections(NETWORK_MODEL)
    palette: dict[str, list[ComponentRow]] = palette_groups()
    pypsa_example_networks: list[ExampleNetworkGroup] = PYPSA_EXAMPLE_NETWORKS
    diagram_nodes: list[DiagramNode] = []
    diagram_edges: list[DiagramEdge] = []
    canvas_regions: list[CanvasRegion] = []
    diagram_model: DiagramModel = {"components": [], "connections": [], "regions": []}
    network_component_rows: list[NetworkObjectComponentRow] = []
    network_connection_rows: list[NetworkObjectConnectionRow] = []
    canvas_bus_names: list[str] = []
    router_options: list[RouterOption] = ROUTER_OPTIONS
    selected_router_name: str = JS_ELK_ROUTER_NAME
    active_view: str = "canvas"
    show_left_sidebar: bool = True
    show_right_sidebar: bool = True
    route_version: int = 0
    fit_view_version: int = 0
    selected_node_id: str = ""
    selected_component_name: str = ""
    selected_attr_rows: list[DiagramAttr] = []
    component_counters: dict[str, int] = {}
    canvas_undo_stack: list[CanvasSnapshot] = []
    canvas_redo_stack: list[CanvasSnapshot] = []
    can_undo_canvas: bool = False
    can_redo_canvas: bool = False
    armed_component: str = ""
    armed_branch_component: str = ""
    rectangle_selection_armed: bool = False
    pending_branch_node_id: str = ""
    branch_bus0_node_id: str = ""
    is_mark_region_dialog_open: bool = False
    mark_region_name: str = ""
    pending_region_bounds: dict[str, float] = {}
    pending_region_node_ids: list[str] = []
    load_message: str = "Using empty PyPSA network defaults."
    load_error: str = ""
    loaded_source: str = ""
    network_has_unsaved_changes: bool = False
    is_loading_network: bool = False
    network_load_status: str = ""
    network_name: str = "Unnamed"
    network_file_path: str = ""
    save_network_folder: str = ""
    save_network_path: str = ""
    save_network_format: str = ""
    export_base_folder: str = str(EXPORTS_DIR)
    export_message: str = ""
    export_error: str = ""
    is_network_name_dialog_open: bool = False
    is_load_dialog_open: bool = False
    is_unsaved_changes_dialog_open: bool = False
    unsaved_network_action: str = ""
    unsaved_network_action_payload: str = ""
    is_export_dialog_open: bool = False
    is_export_dialog_for_save: bool = False
    is_file_picker_open: bool = False
    file_picker_mode: str = "load"
    file_picker_current_dir: str = str(file_picker_start_dir())
    file_picker_path_input: str = str(file_picker_start_dir())
    file_picker_entries: list[FilePickerEntry] = []
    file_picker_roots: list[FilePickerEntry] = file_picker_root_entries()
    file_picker_selected_path: str = ""
    file_picker_target_name: str = ""
    file_picker_save_format: str = "csv"
    file_picker_show_hidden: bool = False
    file_picker_error: str = ""
    file_picker_warning: str = ""
    file_picker_new_folder_name: str = ""
    is_file_picker_overwrite_dialog_open: bool = False
    pending_file_picker_target_path: str = ""
    pending_file_picker_target_format: str = ""
    is_operation_dialog_open: bool = False
    operation_title: str = ""
    operation_status: str = ""
    operation_kind: str = ""
    operation_is_error: bool = False
    operation_retry_load: bool = False
    is_clear_canvas_dialog_open: bool = False
    is_other_component_dialog_open: bool = False
    other_component_dialog_title: str = ""
    other_component_dialog_kind: str = ""
    standard_type_dialog_columns: list[str] = []
    standard_type_dialog_rows: list[StandardTypeRow] = []
    other_csv_tables: dict[str, OtherCsvTable] = {}
    time_series_tables: dict[str, OtherCsvTable] = {}
    other_table_dialog_component: str = ""
    other_table_dialog_columns: list[str] = []
    other_table_dialog_rows: list[OtherTableRow] = []
    other_table_error: str = ""
    time_series_dialog_key: str = ""
    time_series_dialog_column: str = ""
    time_series_dialog_columns: list[str] = []
    time_series_dialog_full_attr: bool = False
    is_time_series_plot_dialog_open: bool = False
    is_time_series_plot_loading: bool = False
    time_series_plot_kind: str = "line"
    time_series_plot_title: str = "Time series plot"
    time_series_plot_error: str = ""
    time_series_plot_figure: go.Figure = go.Figure()
    is_network_data_dialog_open: bool = False
    network_data_active_component: str = "buses"
    network_data_tabs: list[NetworkDataTab] = []
    is_carrier_visibility_dialog_open: bool = False
    carrier_visibility_rows: list[CarrierVisibilityRow] = []
    visible_canvas_carriers: list[str] = []
    carrier_visibility_initialized: bool = False
    is_settings_dialog_open: bool = False
    settings_tabs: list[SettingsTab] = []
    settings_active_tab: str = ""
    settings_network_data_components: list[NetworkDataComponentSetting] = []

    def load_default_model(self) -> None:
        """Reset catalog metadata to the empty PyPSA network defaults."""
        self.sections = model_sections(NETWORK_MODEL)
        self._refresh_palette_from_settings()
        self.loaded_source = ""
        self.network_has_unsaved_changes = False
        self.save_network_folder = ""
        self.save_network_path = ""
        self.save_network_format = ""
        self.other_csv_tables = {}
        self.time_series_tables = {}
        self.is_network_data_dialog_open = False
        self.network_data_tabs = []
        self.is_carrier_visibility_dialog_open = False
        self.carrier_visibility_rows = []
        self.visible_canvas_carriers = []
        self.carrier_visibility_initialized = False
        self.canvas_regions = []
        self.is_mark_region_dialog_open = False
        self.mark_region_name = ""
        self.pending_region_bounds = {}
        self.pending_region_node_ids = []

    def _load_settings_file(self) -> dict[str, dict[str, object]]:
        """Parse settings.toml, returning all sections and non-_options keys.

        If the file does not exist, create it with sensible defaults first.
        """
        if not SETTINGS_FILE.exists():
            self._create_default_settings_file()

        raw: dict[str, dict[str, object]] = {}
        try:
            with open(SETTINGS_FILE, "rb") as fh:
                raw = tomllib.load(fh)
        except OSError, tomllib.TOMLDecodeError:
            pass

        result: dict[str, dict[str, object]] = {}
        for section, pairs in raw.items():
            filtered: dict[str, object] = {}
            for key, value in pairs.items():
                if key.endswith("_options"):
                    continue
                filtered[key] = value
            if filtered:
                result[section] = filtered

        return result

    def _create_default_settings_file(self) -> None:
        """Create the settings.toml file with default sections."""
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        default = """[Theme]
mode = "light"
mode_options = [
  "light",
  "dark"
]

[Canvas]
Router_type = "Elk"
Router_type_options = [
  "Elk"
]

[FilePicker]
Last_path = "~"
"""
        SETTINGS_FILE.write_text(
            default.lstrip("\n") + _default_network_data_settings_toml(),
            encoding="utf-8",
        )

    def _network_data_setting_rows(self) -> list[NetworkDataComponentSetting]:
        """Return ordered Network Data component settings from settings.toml."""
        if not SETTINGS_FILE.exists():
            self._create_default_settings_file()

        try:
            with open(SETTINGS_FILE, "rb") as fh:
                raw = tomllib.load(fh)
        except OSError, tomllib.TOMLDecodeError:
            raw = {}

        configured_rows = []
        section = raw.get(NETWORK_DATA_SETTINGS_SECTION, {})
        if isinstance(section, dict):
            raw_rows = section.get(NETWORK_DATA_SETTINGS_COMPONENTS_KEY, [])
            if isinstance(raw_rows, list):
                configured_rows = raw_rows

        rows: list[NetworkDataComponentSetting] = []
        seen: set[str] = set()
        for raw_row in configured_rows:
            if not isinstance(raw_row, dict):
                continue
            component_name = str(raw_row.get("component", "")).strip()
            if component_name in seen:
                continue
            if not is_network_data_settings_component(component_name):
                continue
            rows.append(
                {
                    "component": component_name,
                    "label": network_data_component_label(component_name),
                    "show_in_editor": bool(raw_row.get("show_in_editor", True)),
                    "show_on_sld": bool(raw_row.get("show_on_sld", True)),
                }
            )
            seen.add(component_name)

        for component_name in network_data_settings_component_names():
            if component_name in seen:
                continue
            rows.append(
                {
                    "component": component_name,
                    "label": network_data_component_label(component_name),
                    "show_in_editor": True,
                    "show_on_sld": True,
                }
            )

        return rows

    def _network_data_settings_lookup(
        self,
    ) -> dict[str, NetworkDataComponentSetting]:
        """Return Network Data settings keyed by component name."""
        return {row["component"]: row for row in self._network_data_setting_rows()}

    def _refresh_palette_from_settings(
        self,
        loaded_network: PypsaLoadedNetwork | None = None,
    ) -> None:
        """Refresh the left palette from current model metadata and SLD settings."""
        groups = model_sections(NETWORK_MODEL, loaded_network)
        self.palette = filter_palette_groups_for_sld(
            groups,
            self._network_data_settings_lookup(),
        )

    def _load_settings_options(self) -> dict[str, list[str]]:
        """Read the {key}_options lists from the settings.toml file."""
        if not SETTINGS_FILE.exists():
            return {}
        try:
            with open(SETTINGS_FILE, "rb") as fh:
                data = tomllib.load(fh)
        except OSError, tomllib.TOMLDecodeError:
            return {}
        options: dict[str, list[str]] = {}
        for section, pairs in data.items():
            for key, value in pairs.items():
                if key.endswith("_options") and isinstance(value, list):
                    base_key = key[: -len("_options")]
                    options[f"{section}.{base_key}"] = [str(v) for v in value]
        return options

    def _save_settings_file(self) -> None:
        """Persist the current in-memory settings to settings.toml."""
        data: dict[str, dict[str, object]] = {}
        for tab in self.settings_tabs:
            if tab["label"] == NETWORK_DATA_SETTINGS_SECTION:
                continue
            for field in tab["fields"]:
                data.setdefault(field["section"], {})[field["key"]] = field["value"]

        data[NETWORK_DATA_SETTINGS_SECTION] = {
            NETWORK_DATA_SETTINGS_COMPONENTS_KEY: [
                {
                    "component": row["component"],
                    "show_in_editor": row["show_in_editor"],
                    "show_on_sld": row["show_on_sld"],
                }
                for row in self.settings_network_data_components
            ]
        }

        options = self._load_settings_options()
        for dotted, opts in options.items():
            section, key = dotted.split(".", 1)
            if section in data and key in data[section]:
                data[section][f"{key}_options"] = opts

        _write_toml_file(data)

    def _build_settings_tabs(self) -> list[SettingsTab]:
        """Build settings_tabs from the parsed TOML file."""
        data = self._load_settings_file()
        file_options = self._load_settings_options()
        tabs: list[SettingsTab] = []
        for section, pair in data.items():
            fields: list[SettingField] = []
            for key, value in pair.items():
                if (
                    section == NETWORK_DATA_SETTINGS_SECTION
                    and key == NETWORK_DATA_SETTINGS_COMPONENTS_KEY
                ):
                    continue
                dotted = f"{section}.{key}"
                opts = file_options.get(dotted, [])
                py_type = type(value).__name__
                fields.append(
                    {
                        "section": section,
                        "key": key,
                        "value": value,
                        "type": py_type,
                        "options": opts,
                    }
                )
            if fields or section == NETWORK_DATA_SETTINGS_SECTION:
                tabs.append({"label": section, "fields": fields})
        if NETWORK_DATA_SETTINGS_SECTION not in {tab["label"] for tab in tabs}:
            tabs.append({"label": NETWORK_DATA_SETTINGS_SECTION, "fields": []})
        return tabs

    def open_settings_dialog(self) -> None:
        """Build settings tabs and open the settings dialog."""
        self.settings_network_data_components = self._network_data_setting_rows()
        self.settings_tabs = self._build_settings_tabs()
        self._refresh_palette_from_settings()
        self._save_settings_file()
        if self.settings_tabs:
            self.settings_active_tab = self.settings_tabs[0]["label"]
        self.is_settings_dialog_open = True

    def set_settings_dialog_open(self, value: bool) -> None:
        """Update whether the settings dialog is open."""
        self.is_settings_dialog_open = value

    def set_settings_active_tab(self, value: str) -> None:
        """Update the active settings tab."""
        self.settings_active_tab = value

    def update_setting(self, section: str, key: str, value: object) -> None:
        """Update a single setting value and persist immediately."""
        tabs = list(self.settings_tabs)
        for tab in tabs:
            if tab["label"] == section:
                fields = list(tab["fields"])
                for i, field in enumerate(fields):
                    if field["key"] == key:
                        fields[i] = {
                            **field,
                            "value": value,
                            "type": type(value).__name__,
                        }
                        break
                tab["fields"] = fields
                break
        self.settings_tabs = tabs
        self._save_settings_file()

    async def update_network_data_component_setting(
        self, component_name: str, show_in_editor: bool
    ) -> AsyncGenerator[None, None]:
        """Update whether a Network Data component appears in the editor."""
        component_name = str(component_name)
        rows = list(self.settings_network_data_components)
        for index, row in enumerate(rows):
            if row["component"] == component_name:
                rows[index] = {**row, "show_in_editor": bool(show_in_editor)}
                break
        self.settings_network_data_components = rows
        self._save_settings_file()
        yield

        if self._should_sync_network_data_view():
            self._sync_network_data_dialog()
            yield

    async def update_network_data_component_sld_setting(
        self, component_name: str, show_on_sld: bool
    ) -> AsyncGenerator[None, None]:
        """Update whether a Network Data component appears in the SLD palette."""
        component_name = str(component_name)
        rows = list(self.settings_network_data_components)
        for index, row in enumerate(rows):
            if row["component"] == component_name:
                rows[index] = {**row, "show_on_sld": bool(show_on_sld)}
                break
        self.settings_network_data_components = rows
        self._save_settings_file()
        self._refresh_palette_from_settings()
        yield

    async def move_network_data_component_setting(
        self, component_name: str, direction: int
    ) -> AsyncGenerator[None, None]:
        """Move a Network Data component setting up or down in editor order."""
        component_name = str(component_name)
        direction = -1 if int(direction) < 0 else 1
        rows = list(self.settings_network_data_components)
        source_index = next(
            (
                index
                for index, row in enumerate(rows)
                if row["component"] == component_name
            ),
            -1,
        )
        target_index = source_index + direction
        if source_index < 0 or target_index < 0 or target_index >= len(rows):
            return
        rows[source_index], rows[target_index] = rows[target_index], rows[source_index]
        self.settings_network_data_components = rows
        self._save_settings_file()
        yield

        if self._should_sync_network_data_view():
            self._sync_network_data_dialog()
            yield

    def _mark_network_dirty(self) -> None:
        """Record that the in-memory network differs from the saved source."""
        self.network_has_unsaved_changes = True

    def _mark_network_saved(self) -> None:
        """Clear dirty flags after loading or saving the current network."""
        self.network_has_unsaved_changes = False
        for table in [
            *self.other_csv_tables.values(),
            *self.time_series_tables.values(),
        ]:
            table["dirty"] = False

    def _has_unsaved_network_changes(self) -> bool:
        """Return whether canvas or editable table state has unsaved changes."""
        return self.network_has_unsaved_changes or any(
            bool(table.get("dirty"))
            for table in [
                *self.other_csv_tables.values(),
                *self.time_series_tables.values(),
            ]
        )

    @rx.var
    def has_unsaved_network_changes(self) -> bool:
        """Expose network unsaved-state to the UI."""
        return self._has_unsaved_network_changes()

    def open_other_component_dialog(self, title: str) -> None:
        """Open the placeholder dialog for an unsupported component."""
        component_name = str(title)
        self.time_series_dialog_key = ""
        self.time_series_dialog_column = ""
        self.time_series_dialog_columns = []
        self.time_series_dialog_full_attr = False
        if component_name == "line_types":
            self.other_component_dialog_title = "Line Types"
            self.other_component_dialog_kind = "standard_type"
            self.standard_type_dialog_columns = standard_type_columns(component_name)
            self.standard_type_dialog_rows = standard_type_rows(component_name)
        elif component_name == "transformer_types":
            self.other_component_dialog_title = "Transformer Types"
            self.other_component_dialog_kind = "standard_type"
            self.standard_type_dialog_columns = standard_type_columns(component_name)
            self.standard_type_dialog_rows = standard_type_rows(component_name)
        elif component_name in CSV_TABLE_COMPONENTS:
            table = self.other_csv_tables.get(
                component_name,
                empty_other_csv_table(component_name),
            )
            self.other_csv_tables[component_name] = table
            self.other_component_dialog_title = (
                NETWORK_MODEL.component(component_name).pypsa_name
                if component_name in NETWORK_MODEL.all_components
                else (
                    "Investment Periods"
                    if component_name == "investment_periods"
                    else "Snapshots"
                )
            )
            self.other_component_dialog_kind = "csv_table"
            self.other_table_dialog_component = component_name
            self.other_table_dialog_columns = table["columns"]
            self.other_table_dialog_rows = table["rows"]
            self.other_table_error = ""
        else:
            self.other_component_dialog_title = component_name
            self.other_component_dialog_kind = ""
            self.standard_type_dialog_columns = []
            self.standard_type_dialog_rows = []
        self.is_other_component_dialog_open = True

    def close_other_component_dialog(self) -> None:
        """Close the placeholder dialog for unsupported components."""
        self.is_other_component_dialog_open = False
        self.other_component_dialog_kind = ""
        self.standard_type_dialog_columns = []
        self.standard_type_dialog_rows = []
        self.other_table_dialog_component = ""
        self.other_table_dialog_columns = []
        self.other_table_dialog_rows = []
        self.other_table_error = ""
        self.time_series_dialog_key = ""
        self.time_series_dialog_column = ""
        self.time_series_dialog_columns = []
        self.time_series_dialog_full_attr = False

    def set_other_component_dialog_open(self, value: bool) -> None:
        """Update whether the unsupported component dialog is open."""
        self.is_other_component_dialog_open = value
        if not value:
            self.other_component_dialog_kind = ""
            self.standard_type_dialog_columns = []
            self.standard_type_dialog_rows = []
            self.other_table_dialog_component = ""
            self.other_table_dialog_columns = []
            self.other_table_dialog_rows = []
            self.other_table_error = ""
            self.time_series_dialog_key = ""
            self.time_series_dialog_column = ""
            self.time_series_dialog_columns = []
            self.time_series_dialog_full_attr = False

    def _selected_time_series_columns(self, table: OtherCsvTable) -> list[str]:
        """Return the columns currently selected for the time-series dialog."""
        table_columns = [str(column) for column in table["columns"]]
        if self.time_series_dialog_full_attr and table_columns:
            return table_columns

        selected_columns = [
            str(column)
            for column in self.time_series_dialog_columns
            if str(column).strip()
        ]
        if selected_columns:
            return selected_columns
        if self.time_series_dialog_column:
            return [str(self.time_series_dialog_column)]
        return table_columns

    def _sync_other_table_dialog(self) -> None:
        """Refresh editable supplemental CSV table dialog rows from state."""
        if self.time_series_dialog_key:
            table = self.time_series_tables.get(self.time_series_dialog_key)
            if table is None:
                return
            columns = self._selected_time_series_columns(table)
            self.other_table_dialog_columns = columns
            rows: list[OtherTableRow] = []
            for row in table["rows"]:
                values_by_column = {
                    str(cell["column"]): str(cell["value"]) for cell in row["cells"]
                }
                rows.append(
                    {
                        "row_index": row["row_index"],
                        "id": row["id"],
                        "cells": [
                            {
                                "row_index": row["row_index"],
                                "column": column,
                                "value": values_by_column.get(column, ""),
                            }
                            for column in columns
                        ],
                    }
                )
            self.other_table_dialog_rows = rows
            self._refresh_selected_attr_rows()
            return
        if not self.other_table_dialog_component:
            return
        table = self.other_csv_tables.get(self.other_table_dialog_component)
        if table is None:
            return
        self.other_table_dialog_columns = table["columns"]
        self.other_table_dialog_rows = table["rows"]
        self._refresh_selected_attr_rows()

    def _load_network_data_table_from_source(
        self, component_name: str
    ) -> OtherCsvTable:
        """Load a non-canvas component table from the current folder or PyPSA defaults."""
        source_text = (
            self.save_network_path or self.save_network_folder or self.loaded_source
        )
        if source_text:
            source = Path(source_text).expanduser()
            csv_path = source / network_data_file_name(component_name)
            if source.is_dir() and csv_path.exists():
                data_frame = pd.read_csv(csv_path, index_col=0, dtype=str).fillna("")
                return dataframe_to_network_data_table(component_name, data_frame)

        try:
            data_frame = pypsa.Network().components[component_name].static
        except Exception:
            return empty_network_data_table(component_name)
        return dataframe_to_network_data_table(
            component_name,
            data_frame,
            dirty=False,
            loaded=False,
        )

    def _ensure_network_data_table(self, component_name: str) -> OtherCsvTable:
        """Return the editable backing table for a non-canvas Network Data tab."""
        table = self.other_csv_tables.get(component_name)
        if table is None:
            table = self._load_network_data_table_from_source(component_name)
            self.other_csv_tables[component_name] = table
        for column in network_data_columns(component_name):
            if column["name"] not in table["columns"]:
                table["columns"].append(column["name"])
        return table

    def _has_time_series_value(
        self,
        component_name: str,
        attr_name: str,
        pypsa_name: str,
    ) -> bool:
        """Return whether a component row has non-empty time-series values."""
        table = self.time_series_tables.get(f"{component_name}:{attr_name}")
        if table is None or pypsa_name not in table["columns"]:
            return False
        for row in table["rows"]:
            for cell in row["cells"]:
                if cell["column"] == pypsa_name and str(cell["value"]).strip() != "":
                    return True
        return False

    def _network_data_canvas_rows(self, component_name: str) -> list[NetworkDataRow]:
        """Build Network Data rows from diagram nodes."""
        columns = network_data_columns(component_name)
        rows: list[NetworkDataRow] = []
        component = NETWORK_MODEL.component(component_name)
        for row_index, node in enumerate(
            node for node in self.diagram_nodes if node["component"] == component_name
        ):
            attrs = node.get("attrs", {})
            row_name = str(attrs.get("name") or node["id"])
            cells: list[NetworkDataCell] = []
            for column in columns:
                attr_name = column["name"]
                attr = component.attrs[attr_name]
                value = attrs.get(attr_name, attr.default)
                cells.append(
                    {
                        "component": component_name,
                        "row_id": node["id"],
                        "row_index": row_index,
                        "attr_name": attr_name,
                        "value": value,
                        "display_value": network_data_display_value(
                            value,
                            column["input_type"],
                        ),
                        "type": column["type"],
                        "input_type": column["input_type"],
                        "is_time_series": column["is_time_series"],
                        "has_time_series_value": self._has_time_series_value(
                            component_name,
                            attr_name,
                            row_name,
                        ),
                        "is_bus_reference": column["is_bus_reference"],
                        "options": column["options"],
                    }
                )
            rows.append(
                {
                    "component": component_name,
                    "row_id": node["id"],
                    "row_index": row_index,
                    "name": row_name,
                    "cells": cells,
                }
            )
        return rows

    def _network_data_table_rows(self, component_name: str) -> list[NetworkDataRow]:
        """Build Network Data rows from a non-canvas editable table."""
        table = self._ensure_network_data_table(component_name)
        columns = network_data_columns(component_name)
        rows: list[NetworkDataRow] = []
        for row in table["rows"]:
            values_by_column = {
                str(cell["column"]): cell["value"] for cell in row["cells"]
            }
            cells: list[NetworkDataCell] = []
            for column in columns:
                attr_name = column["name"]
                value = values_by_column.get(attr_name, "")
                cells.append(
                    {
                        "component": component_name,
                        "row_id": str(row["id"]),
                        "row_index": int(row["row_index"]),
                        "attr_name": attr_name,
                        "value": value,
                        "display_value": network_data_display_value(
                            value,
                            column["input_type"],
                        ),
                        "type": column["type"],
                        "input_type": column["input_type"],
                        "is_time_series": column["is_time_series"],
                        "has_time_series_value": self._has_time_series_value(
                            component_name,
                            attr_name,
                            str(row["id"]),
                        ),
                        "is_bus_reference": column["is_bus_reference"],
                        "options": column["options"],
                    }
                )
            rows.append(
                {
                    "component": component_name,
                    "row_id": str(row["id"]),
                    "row_index": int(row["row_index"]),
                    "name": str(row["id"]),
                    "cells": cells,
                }
            )
        return rows

    def _network_data_rows_for_component(
        self, component_name: str
    ) -> list[NetworkDataRow]:
        """Build rows for one Network Data component tab."""
        if is_canvas_data_component(component_name):
            return self._network_data_canvas_rows(component_name)
        return self._network_data_table_rows(component_name)

    def _sync_network_data_dialog(self) -> None:
        """Refresh the whole-network data tables from current state."""
        tabs: list[NetworkDataTab] = []
        component_settings = self._network_data_setting_rows()
        self.settings_network_data_components = component_settings
        for component_setting in component_settings:
            if not component_setting["show_in_editor"]:
                continue
            component_name = component_setting["component"]
            columns = network_data_columns(component_name)
            rows = self._network_data_rows_for_component(component_name)
            tabs.append(
                {
                    "component": component_name,
                    "label": network_data_component_label(component_name),
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                }
            )
        self.network_data_tabs = tabs
        available_components = {tab["component"] for tab in tabs}
        if self.network_data_active_component not in available_components:
            self.network_data_active_component = tabs[0]["component"] if tabs else ""

    def open_network_data_dialog(self) -> None:
        """Open the editable whole-network data dialog."""
        self._sync_network_data_dialog()
        self.is_network_data_dialog_open = True

    def set_network_data_dialog_open(self, value: bool) -> None:
        """Set the Network Data dialog open state."""
        self.is_network_data_dialog_open = bool(value)
        if value:
            self._sync_network_data_dialog()

    def set_network_data_active_component(self, value: str) -> None:
        """Set the active component tab in the Network Data dialog."""
        component_name = str(value)
        if is_network_data_settings_component(component_name):
            self.network_data_active_component = component_name

    def _should_sync_network_data_view(self) -> bool:
        """Return whether Network Data tables are currently visible."""
        return self.is_network_data_dialog_open or self.active_view == "network-data"

    def _row_name_for_network_data(
        self,
        component_name: str,
        row_id: str,
        row_index: int,
    ) -> str:
        """Return the PyPSA row name for a Network Data row."""
        if is_canvas_data_component(component_name):
            for node in self.diagram_nodes:
                if node["id"] == row_id:
                    return str(node["attrs"].get("name") or node["id"])
            return row_id
        table = self._ensure_network_data_table(component_name)
        for row in table["rows"]:
            if row["row_index"] == int(row_index):
                return str(row["id"])
        return row_id

    def _cascade_reference_rename(
        self,
        component_name: str,
        old_name: str,
        new_name: str,
    ) -> None:
        """Cascade known row-name references after a Network Data rename."""
        if not old_name or old_name == new_name:
            return
        reference_attrs: list[str] = []
        target_components: set[str] | None = None
        if component_name == "buses":
            reference_attrs = ["bus", "bus0", "bus1", "bus2", "bus3", "bus4"]
        elif component_name == "carriers":
            reference_attrs = ["carrier"]
        elif component_name == "sub_networks":
            reference_attrs = ["sub_network"]
        elif component_name == "line_types":
            reference_attrs = ["type"]
            target_components = {"lines"}
        elif component_name == "transformer_types":
            reference_attrs = ["type"]
            target_components = {"transformers"}
        if not reference_attrs:
            return

        for node in self.diagram_nodes:
            if (
                target_components is not None
                and node["component"] not in target_components
            ):
                continue
            attrs = node.get("attrs", {})
            changed = False
            for attr_name in reference_attrs:
                if str(attrs.get(attr_name, "")) == old_name:
                    attrs[attr_name] = new_name
                    changed = True
            if changed:
                component = NETWORK_MODEL.component(node["component"])
                node["attr_rows"] = diagram_attr_rows(component, attrs)

    def update_network_data_row_name(
        self,
        component_name: str,
        row_id: str,
        row_index: int,
        value: str,
    ) -> None:
        """Update a row name from Network Data."""
        component_name = str(component_name)
        new_name = str(value)
        if not is_network_data_settings_component(component_name):
            return
        if is_canvas_data_component(component_name):
            for node in self.diagram_nodes:
                if node["id"] != str(row_id):
                    continue
                old_name = str(node["attrs"].get("name") or node["id"])
                if old_name == new_name:
                    return
                self._push_canvas_history()
                node["attrs"]["name"] = new_name
                self._cascade_reference_rename(component_name, old_name, new_name)
                component = NETWORK_MODEL.component(node["component"])
                node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
                self._sync_diagram_model()
                if self.selected_node_id == node["id"]:
                    self.selected_attr_rows = self._selected_attr_rows_for_node(node)
                if self._should_sync_network_data_view():
                    self._sync_network_data_dialog()
                return

        table = self._ensure_network_data_table(component_name)
        for row in table["rows"]:
            if row["row_index"] != int(row_index):
                continue
            old_name = str(row["id"])
            if old_name == new_name:
                return
            row["id"] = new_name
            table["dirty"] = True
            self._mark_network_dirty()
            self._cascade_reference_rename(component_name, old_name, new_name)
            self._sync_diagram_model()
            if self._should_sync_network_data_view():
                self._sync_network_data_dialog()
            return

    def _update_network_data_table_cell(
        self,
        component_name: str,
        row_index: int,
        attr_name: str,
        value: object,
    ) -> None:
        """Update a non-canvas Network Data backing table cell."""
        table = self._ensure_network_data_table(component_name)
        if attr_name not in table["columns"]:
            table["columns"].append(attr_name)
        for row in table["rows"]:
            if row["row_index"] != int(row_index):
                continue
            for cell in row["cells"]:
                if str(cell["column"]) == attr_name:
                    cell["value"] = str(value)
                    break
            else:
                row["cells"].append(
                    {
                        "row_index": int(row_index),
                        "column": attr_name,
                        "value": str(value),
                    }
                )
            table["dirty"] = True
            self._mark_network_dirty()
            if self._should_sync_network_data_view():
                self._sync_network_data_dialog()
            return

    def update_network_data_cell(
        self,
        component_name: str,
        row_id: str,
        row_index: int,
        attr_name: str,
        value: object,
    ) -> None:
        """Update a Network Data cell."""
        component_name = str(component_name)
        attr_name = str(attr_name)
        if component_name in SNAPSHOT_TABLE_COLUMNS:
            self._update_network_data_table_cell(
                component_name,
                row_index,
                attr_name,
                value,
            )
            return
        if component_name not in NETWORK_MODEL.all_components:
            return
        component = NETWORK_MODEL.component(component_name)
        attr = component.attrs.get(attr_name)
        if attr is None:
            return
        clean_value = (
            clean_numeric_text(value)
            if attr_input_type(
                attr.pypsa_type,
                attr.python_type,
            )
            == "number"
            else value
        )
        if is_canvas_data_component(component_name):
            for node in self.diagram_nodes:
                if node["id"] != str(row_id):
                    continue
                parsed_value = self._parse_attr_value(
                    clean_value, attr.pypsa_type, attr.python_type
                )
                if node["attrs"].get(attr_name) == parsed_value:
                    return
                self._push_canvas_history()
                node["attrs"][attr_name] = parsed_value
                if attr_name in REFERENCE_ATTR_TABLES:
                    self._ensure_reference_row(attr_name, parsed_value)
                node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
                self._sync_diagram_model()
                if self.selected_node_id == node["id"]:
                    self.selected_attr_rows = self._selected_attr_rows_for_node(node)
                if self._should_sync_network_data_view():
                    self._sync_network_data_dialog()
                return

        self._update_network_data_table_cell(
            component_name,
            row_index,
            attr_name,
            clean_value,
        )

    def commit_network_data_reference(
        self,
        component_name: str,
        attr_name: str,
        value: object,
    ) -> None:
        """Promote a Network Data reference value into its global CSV table."""
        del component_name
        if str(attr_name) in REFERENCE_ATTR_TABLES:
            self._ensure_reference_row(str(attr_name), value)
            if self._should_sync_network_data_view():
                self._sync_network_data_dialog()

    def _open_time_series_table(
        self,
        component_name: str,
        attr_name: str,
        pypsa_name: str,
    ) -> None:
        """Open the editable time-series table for one component attr and row."""
        self._open_time_series_table_columns(
            component_name,
            attr_name,
            [str(pypsa_name)],
            f"{component_name}.{attr_name} - {pypsa_name}",
            full_attr=False,
        )

    def _open_time_series_table_columns(
        self,
        component_name: str,
        attr_name: str,
        columns: list[str],
        title: str,
        *,
        full_attr: bool,
    ) -> None:
        """Open the time-series table for one or more series columns."""
        component_name = str(component_name)
        attr_name = str(attr_name)
        selected_columns = [str(column) for column in columns if str(column).strip()]
        key = f"{component_name}:{attr_name}"
        table = self.time_series_tables.get(key)
        if table is None:
            table = {
                "component": key,
                "file_name": f"{component_name}-{attr_name}.csv",
                "columns": selected_columns,
                "rows": [],
                "index_name": "snapshot",
                "loaded": False,
                "dirty": False,
            }
            self.time_series_tables[key] = table
        if full_attr and not selected_columns:
            selected_columns = [str(column) for column in table["columns"]]

        self.other_component_dialog_title = title
        self.other_component_dialog_kind = "csv_table"
        self.other_table_dialog_component = ""
        self.time_series_dialog_key = key
        self.time_series_dialog_column = selected_columns[0] if selected_columns else ""
        self.time_series_dialog_columns = selected_columns
        self.time_series_dialog_full_attr = full_attr
        self.time_series_plot_error = ""
        self.time_series_plot_figure = go.Figure()
        self.other_table_error = ""
        self._sync_other_table_dialog()
        self.is_other_component_dialog_open = True

    def _network_data_row_names(self, component_name: str) -> list[str]:
        """Return row names currently visible for a Network Data component."""
        return [
            str(row["name"])
            for row in self._network_data_rows_for_component(component_name)
            if str(row["name"]).strip()
        ]

    async def open_network_data_time_series_attr_table(
        self,
        component_name: str,
        attr_name: str,
    ):
        """Open the full time-series table for a Network Data attr header."""
        component_name = str(component_name)
        attr_name = str(attr_name)
        self.is_network_data_dialog_open = False
        self.is_operation_dialog_open = True
        self.operation_title = "Loading time series"
        self.operation_status = f"Opening {component_name}.{attr_name}..."
        self.operation_kind = "load"
        self.operation_is_error = False
        self.operation_retry_load = False
        yield

        key = f"{component_name}:{attr_name}"
        table = self.time_series_tables.get(key)
        columns = (
            [str(column) for column in table["columns"]]
            if table is not None and table["columns"]
            else self._network_data_row_names(component_name)
        )
        self._open_time_series_table_columns(
            component_name,
            attr_name,
            columns,
            f"{component_name}.{attr_name}",
            full_attr=True,
        )
        self.is_operation_dialog_open = False
        self.operation_title = ""
        self.operation_status = ""
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        yield

    async def open_network_data_time_series_attr(
        self,
        component_name: str,
        row_id: str,
        row_index: int,
        attr_name: str,
    ):
        """Open a time-series table from a Network Data cell."""
        self.is_network_data_dialog_open = False
        self.is_operation_dialog_open = True
        self.operation_title = "Loading time series"
        self.operation_status = f"Opening {component_name}.{attr_name}..."
        self.operation_kind = "load"
        self.operation_is_error = False
        self.operation_retry_load = False
        yield

        pypsa_name = self._row_name_for_network_data(
            str(component_name),
            str(row_id),
            int(row_index),
        )
        self._open_time_series_table(str(component_name), str(attr_name), pypsa_name)
        self.is_operation_dialog_open = False
        self.operation_title = ""
        self.operation_status = ""
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        yield

    def set_time_series_plot_kind(self, value: str | list[str]) -> None:
        """Set the graph type for time-series plotting."""
        selected_value = value[0] if isinstance(value, list) and value else value
        self.time_series_plot_kind = "bar" if str(selected_value) == "bar" else "line"

    def set_time_series_plot_dialog_open(self, value: bool) -> None:
        """Set the time-series plot dialog open state."""
        self.is_time_series_plot_dialog_open = bool(value)
        if not value:
            self.is_time_series_plot_loading = False

    def _build_time_series_plot_figure(self) -> tuple[go.Figure, str]:
        """Build a Plotly figure from the current time-series dialog table."""
        table = self.time_series_tables.get(self.time_series_dialog_key)
        if table is None:
            return go.Figure(), "No time-series table is open."

        columns = self._selected_time_series_columns(table)
        if not columns:
            return go.Figure(), "No series columns are available to plot."

        traces = []
        for column in columns:
            x_values: list[str] = []
            y_values: list[float] = []
            for row in table["rows"]:
                values_by_column = {
                    str(cell["column"]): cell["value"] for cell in row["cells"]
                }
                numeric_value = plot_numeric_value(values_by_column.get(column, ""))
                if numeric_value is None:
                    continue
                x_values.append(str(row["id"]))
                y_values.append(numeric_value)

            if not x_values:
                continue

            if self.time_series_plot_kind == "bar":
                traces.append(go.Bar(name=column, x=x_values, y=y_values))
            else:
                traces.append(
                    go.Scatter(
                        name=column,
                        x=x_values,
                        y=y_values,
                        mode="lines+markers",
                    )
                )

        if not traces:
            return (
                go.Figure(),
                "No numeric time-series values are available to plot.",
            )

        figure = go.Figure(data=traces)
        figure.update_layout(
            title=self.other_component_dialog_title or "Time series",
            xaxis_title=table.get("index_name", "snapshot") or "snapshot",
            yaxis_title="value",
            margin={"l": 56, "r": 24, "t": 56, "b": 64},
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "right",
                "x": 1,
            },
            height=560,
            barmode="group",
        )
        return figure, ""

    async def open_time_series_plot_dialog(self):
        """Open the time-series Plotly dialog without blocking the first update."""
        self.is_time_series_plot_dialog_open = True
        self.is_time_series_plot_loading = True
        self.time_series_plot_title = (
            f"{self.other_component_dialog_title} plot"
            if self.other_component_dialog_title
            else "Time series plot"
        )
        self.time_series_plot_error = ""
        self.time_series_plot_figure = go.Figure()
        yield

        figure, error = self._build_time_series_plot_figure()
        self.time_series_plot_figure = figure
        self.time_series_plot_error = error
        self.is_time_series_plot_loading = False
        yield

    def _canvas_snapshot(self) -> CanvasSnapshot:
        """Return a deep snapshot of undoable canvas state."""
        return {
            "diagram_nodes": copy.deepcopy(self.diagram_nodes),
            "canvas_regions": copy.deepcopy(self.canvas_regions),
            "component_counters": copy.deepcopy(self.component_counters),
            "route_version": self.route_version,
            "selected_node_id": self.selected_node_id,
            "armed_component": self.armed_component,
            "armed_branch_component": self.armed_branch_component,
            "rectangle_selection_armed": self.rectangle_selection_armed,
            "pending_branch_node_id": self.pending_branch_node_id,
            "branch_bus0_node_id": self.branch_bus0_node_id,
            "visible_canvas_carriers": copy.deepcopy(self.visible_canvas_carriers),
            "carrier_visibility_initialized": self.carrier_visibility_initialized,
        }

    def _set_canvas_history_availability(self) -> None:
        """Refresh undo/redo button enabled state."""
        self.can_undo_canvas = bool(self.canvas_undo_stack)
        self.can_redo_canvas = bool(self.canvas_redo_stack)

    def _clear_canvas_history(self) -> None:
        """Clear undo and redo stacks."""
        self.canvas_undo_stack = []
        self.canvas_redo_stack = []
        self._set_canvas_history_availability()

    def _push_canvas_history(self) -> None:
        """Record the current canvas state before a user-visible mutation."""
        self._mark_network_dirty()
        self.canvas_undo_stack.append(self._canvas_snapshot())
        if len(self.canvas_undo_stack) > CANVAS_HISTORY_LIMIT:
            self.canvas_undo_stack = self.canvas_undo_stack[-CANVAS_HISTORY_LIMIT:]
        self.canvas_redo_stack = []
        self._set_canvas_history_availability()

    def _restore_canvas_snapshot(self, snapshot: CanvasSnapshot) -> None:
        """Restore canvas state from a history snapshot."""
        self.diagram_nodes = copy.deepcopy(snapshot["diagram_nodes"])
        self.canvas_regions = copy.deepcopy(snapshot["canvas_regions"])
        self.component_counters = copy.deepcopy(snapshot["component_counters"])
        self.route_version = int(snapshot["route_version"])
        self.armed_component = str(snapshot["armed_component"])
        self.armed_branch_component = str(snapshot["armed_branch_component"])
        self.rectangle_selection_armed = bool(snapshot["rectangle_selection_armed"])
        self.pending_branch_node_id = str(snapshot["pending_branch_node_id"])
        self.branch_bus0_node_id = str(snapshot["branch_bus0_node_id"])
        self.visible_canvas_carriers = copy.deepcopy(
            snapshot["visible_canvas_carriers"]
        )
        self.carrier_visibility_initialized = bool(
            snapshot["carrier_visibility_initialized"]
        )
        self._sync_diagram_model()
        if self.is_carrier_visibility_dialog_open:
            self._sync_carrier_visibility_rows()
        self.select_node(str(snapshot["selected_node_id"]))

    def undo_canvas(self) -> None:
        """Restore the previous undoable canvas state."""
        if not self.canvas_undo_stack:
            return
        snapshot = self.canvas_undo_stack.pop()
        self.canvas_redo_stack.append(self._canvas_snapshot())
        if len(self.canvas_redo_stack) > CANVAS_HISTORY_LIMIT:
            self.canvas_redo_stack = self.canvas_redo_stack[-CANVAS_HISTORY_LIMIT:]
        self._restore_canvas_snapshot(snapshot)
        self._mark_network_dirty()
        self._set_canvas_history_availability()

    def redo_canvas(self) -> None:
        """Restore the next redoable canvas state."""
        if not self.canvas_redo_stack:
            return
        snapshot = self.canvas_redo_stack.pop()
        self.canvas_undo_stack.append(self._canvas_snapshot())
        if len(self.canvas_undo_stack) > CANVAS_HISTORY_LIMIT:
            self.canvas_undo_stack = self.canvas_undo_stack[-CANVAS_HISTORY_LIMIT:]
        self._restore_canvas_snapshot(snapshot)
        self._mark_network_dirty()
        self._set_canvas_history_availability()

    def update_other_table_row_id(self, row_index: int, value: str) -> None:
        """Update the row id for the open supplemental CSV table."""
        table = (
            self.time_series_tables.get(self.time_series_dialog_key)
            if self.time_series_dialog_key
            else self.other_csv_tables.get(self.other_table_dialog_component)
        )
        if table is None:
            return
        for row in table["rows"]:
            if row["row_index"] == int(row_index):
                row["id"] = str(value)
                break
        table["dirty"] = True
        self._mark_network_dirty()
        self.other_table_error = ""
        self._sync_other_table_dialog()

    def update_other_table_cell(self, row_index: int, column: str, value: str) -> None:
        """Update one cell in the open supplemental CSV table."""
        table = (
            self.time_series_tables.get(self.time_series_dialog_key)
            if self.time_series_dialog_key
            else self.other_csv_tables.get(self.other_table_dialog_component)
        )
        if table is None:
            return
        for row in table["rows"]:
            if row["row_index"] != int(row_index):
                continue
            for cell in row["cells"]:
                if cell["column"] == str(column):
                    cell["value"] = str(value)
                    table["dirty"] = True
                    self._mark_network_dirty()
                    self.other_table_error = ""
                    self._sync_other_table_dialog()
                    return
            row["cells"].append(
                {
                    "row_index": int(row_index),
                    "column": str(column),
                    "value": str(value),
                }
            )
            if str(column) not in table["columns"]:
                table["columns"].append(str(column))
            table["dirty"] = True
            self._mark_network_dirty()
            self.other_table_error = ""
            self._sync_other_table_dialog()
            return

    def add_other_table_row(self) -> None:
        """Add a blank row to the open supplemental CSV table."""
        table = (
            self.time_series_tables.get(self.time_series_dialog_key)
            if self.time_series_dialog_key
            else self.other_csv_tables.get(self.other_table_dialog_component)
        )
        if table is None:
            return
        columns = (
            [self.time_series_dialog_column]
            if self.time_series_dialog_key
            else table["columns"]
        )
        next_index = max((row["row_index"] for row in table["rows"]), default=-1) + 1
        table["rows"].append(
            {
                "row_index": next_index,
                "id": "",
                "cells": [
                    {"row_index": next_index, "column": column, "value": ""}
                    for column in columns
                ],
            }
        )
        table["loaded"] = True
        table["dirty"] = True
        self._mark_network_dirty()
        self.other_table_error = ""
        self._sync_other_table_dialog()

    def delete_other_table_row(self, row_index: int) -> None:
        """Delete a row from the open supplemental CSV table."""
        table = (
            self.time_series_tables.get(self.time_series_dialog_key)
            if self.time_series_dialog_key
            else self.other_csv_tables.get(self.other_table_dialog_component)
        )
        if table is None:
            return
        table["rows"] = [
            row for row in table["rows"] if row["row_index"] != int(row_index)
        ]
        table["dirty"] = True
        self._mark_network_dirty()
        self.other_table_error = ""
        self._sync_other_table_dialog()

    async def upload_editable_csv(self, files: list[rx.UploadFile]):
        """Replace the open editable CSV table with an uploaded CSV."""
        if not files:
            self.other_table_error = "Choose a CSV file to upload."
            yield
            return
        try:
            data = await files[0].read()
            data_frame = pd.read_csv(
                io.BytesIO(data),
                index_col=0,
                dtype=str,
            ).fillna("")
            if self.time_series_dialog_key:
                component_name, attr_name = self.time_series_dialog_key.split(":", 1)
                table = dataframe_to_time_series_table(
                    component_name,
                    attr_name,
                    data_frame,
                    dirty=True,
                )
                table["loaded"] = True
                if self.time_series_dialog_full_attr:
                    self.time_series_dialog_columns = [
                        str(column) for column in table["columns"]
                    ]
                    self.time_series_dialog_column = (
                        self.time_series_dialog_columns[0]
                        if self.time_series_dialog_columns
                        else ""
                    )
                else:
                    missing_columns = [
                        column
                        for column in self._selected_time_series_columns(table)
                        if column not in table["columns"]
                    ]
                    for column in missing_columns:
                        table["columns"].append(column)
                        for row in table["rows"]:
                            row["cells"].append(
                                {
                                    "row_index": row["row_index"],
                                    "column": column,
                                    "value": "",
                                }
                            )
                self.time_series_tables[self.time_series_dialog_key] = table
            elif self.other_table_dialog_component:
                table = dataframe_to_other_csv_table(
                    self.other_table_dialog_component,
                    data_frame,
                )
                table["dirty"] = True
                table["loaded"] = True
                self.other_csv_tables[self.other_table_dialog_component] = table
            else:
                self.other_table_error = "No editable table is open."
                yield
                return
            self._mark_network_dirty()
            self.other_table_error = ""
            self._sync_other_table_dialog()
            yield rx.clear_selected_files(EDITABLE_CSV_UPLOAD_ID)
        except Exception as exc:
            self.other_table_error = f"Could not load CSV: {exc}"
            yield

    def _extra_csv_tables_for_export(self) -> dict[str, dict[str, Any]]:
        """Validate and convert supplemental CSV tables for export."""
        self._ensure_diagram_reference_rows()
        extra_tables: dict[str, dict[str, Any]] = {}
        for table in [
            *self.other_csv_tables.values(),
            *self.time_series_tables.values(),
        ]:
            seen_ids: set[str] = set()
            export_rows: list[dict[str, object]] = []
            for row in table["rows"]:
                row_id = str(row["id"]).strip()
                if not row_id:
                    raise ValueError(
                        f"{table['file_name']} has a row with a blank name."
                    )
                if row_id in seen_ids:
                    raise ValueError(
                        f"{table['file_name']} has a duplicate row name: {row_id}."
                    )
                seen_ids.add(row_id)
                values_by_column = {
                    str(cell["column"]): str(cell["value"]) for cell in row["cells"]
                }
                export_rows.append(
                    {
                        "id": row_id,
                        "values": [
                            values_by_column.get(column, "")
                            for column in table["columns"]
                        ],
                    }
                )
            if table.get("dirty") or table.get("loaded"):
                extra_tables[table["file_name"]] = {
                    "columns": table["columns"],
                    "rows": export_rows,
                    "index_name": table.get("index_name", "name"),
                }
        return extra_tables

    def _apply_network_load_artifacts(
        self,
        artifacts: NetworkLoadArtifacts,
        *,
        loaded_source: str = "",
        save_network_folder: str = "",
        save_network_path: str = "",
        save_network_format: str = "",
    ) -> tuple[pypsa.Network, PypsaLoadedNetwork]:
        """Apply centrally loaded network data and editable side tables to state."""
        network = artifacts["network"]
        loaded_network = artifacts["loaded_network"]
        self.sections = model_sections(NETWORK_MODEL, loaded_network)
        self._refresh_palette_from_settings(loaded_network)
        self.loaded_source = loaded_source or loaded_network.source or ""
        self.save_network_folder = save_network_folder
        self.save_network_path = save_network_path
        self.save_network_format = save_network_format
        self.other_csv_tables = artifacts["other_csv_tables"]
        self.time_series_tables = artifacts["time_series_tables"]
        self.is_carrier_visibility_dialog_open = False
        self.carrier_visibility_rows = []
        self.visible_canvas_carriers = []
        self.carrier_visibility_initialized = False
        return network, loaded_network

    def _request_canvas_fit_view(self) -> None:
        """Request a fit-to-view action on the next canvas render."""
        self.fit_view_version += 1

    async def load_network(self, files: list[rx.UploadFile]):
        """Load a PyPSA file for catalog default-value inspection."""
        if not files:
            self.load_error = "Select a PyPSA network file first."
            return

        upload = files[0]
        file_name = upload.name or "pypsa-network"

        try:
            data = await upload.read()
            saved_path = save_upload(file_name, data, rx.get_upload_dir())
            artifacts = load_network_artifacts(saved_path)
            self._apply_network_load_artifacts(
                artifacts,
                loaded_source=artifacts["loaded_network"].source or file_name,
            )
            self._mark_network_saved()
            self.load_message = f"Loaded {file_name}."
            self.load_error = ""
        except Exception as exc:
            self.load_error = f"Could not load {file_name}: {exc}"

    async def load_network_folder(self, files: list[rx.UploadFile]):
        """Load an uploaded CSV folder for catalog default-value inspection."""
        if not files:
            self.load_error = "Select a PyPSA CSV export directory first."
            return

        try:
            payloads = []
            for upload in files:
                file_name = str(upload.path or upload.name or "uploaded-file")
                payloads.append((file_name, await upload.read()))

            csv_folder = save_uploads_as_csv_folder(payloads, rx.get_upload_dir())
            artifacts = load_network_artifacts(csv_folder)
            self._apply_network_load_artifacts(
                artifacts,
                loaded_source=artifacts["loaded_network"].source or str(csv_folder),
            )
            self._mark_network_saved()
            self.load_message = f"Loaded CSV directory with {len(files)} files."
            self.load_error = ""
        except Exception as exc:
            self.load_error = f"Could not load CSV directory: {exc}"

    async def load_network_to_canvas(self, files: list[rx.UploadFile]):
        """Load an uploaded PyPSA network file directly onto the canvas."""
        if not files:
            self.export_error = "Choose a PyPSA network file first."
            self.export_message = ""
            return

        upload = files[0]
        file_name = upload.name or "pypsa-network"

        try:
            data = await upload.read()
            saved_path = save_upload(file_name, data, rx.get_upload_dir())
            artifacts = load_network_artifacts(saved_path)
            network, _loaded_network = self._apply_network_load_artifacts(
                artifacts,
                loaded_source=str(saved_path),
            )
            self.network_name = str(network.name or file_name)
            print(network)
            self._populate_canvas_from_network(network, trigger_route=False)
            self._mark_network_saved()
            self.load_message = f"Loaded {file_name} onto canvas."
            self.export_message = f"Loaded {file_name} onto canvas."
            self.load_error = ""
            self.export_error = ""
        except Exception as exc:
            self.export_error = f"Could not load network onto canvas: {exc}"
            self.export_message = ""

    async def load_pypsa_example_network(self, network_path: str):
        """Load a bundled PyPSA example .nc network directly onto the canvas."""
        path = Path(str(network_path)).expanduser()
        file_name = path.name
        try:
            self.is_loading_network = True
            self.is_operation_dialog_open = True
            self.operation_title = "Loading network"
            self.operation_status = f"Loading PyPSA example {file_name}..."
            self.operation_kind = "load"
            self.operation_is_error = False
            self.operation_retry_load = False
            self.network_load_status = self.operation_status
            self.export_message = ""
            self.export_error = ""
            yield

            artifacts = await asyncio.to_thread(load_network_artifacts, path)
            save_format = network_save_format_for_path(path)
            save_network_folder = str(path) if save_format == "csv" else ""
            network, _loaded_network = self._apply_network_load_artifacts(
                artifacts,
                loaded_source=str(path),
                save_network_folder=save_network_folder,
                save_network_path=str(path),
                save_network_format=save_format,
            )
            self.network_name = str(network.name or path.stem or "Unnamed")
            self.operation_status = "Building canvas object..."
            self.network_load_status = self.operation_status
            yield

            diagram_nodes, component_counters = await asyncio.to_thread(
                build_canvas_nodes_from_network,
                network,
            )
            layout_positions = await asyncio.to_thread(load_layout_positions, path)
            layout_regions = await asyncio.to_thread(load_layout_regions, path)
            apply_layout_positions(diagram_nodes, layout_positions)
            self._apply_canvas_nodes(diagram_nodes, component_counters, layout_regions)
            self._mark_network_saved()
            self.load_message = f"Loaded {file_name} onto canvas."
            self.export_message = f"Loaded {file_name} onto canvas."
            self.load_error = ""
            self.export_error = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.is_operation_dialog_open = False
            self.operation_title = ""
            self.operation_status = ""
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            yield rx.toast.success(f"Loaded PyPSA example {file_name}.")
        except Exception as exc:
            self.export_error = f"Could not load PyPSA example {file_name}: {exc}"
            self.export_message = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error("Could not load network", self.export_error)
            yield

    async def load_network_folder_to_canvas(self, files: list[rx.UploadFile]):
        """Load an uploaded PyPSA CSV export folder directly onto the canvas."""
        if not files:
            self.export_error = "Choose a PyPSA CSV export directory first."
            self.export_message = ""
            return

        try:
            self.is_loading_network = True
            self.is_operation_dialog_open = True
            self.operation_title = "Loading network"
            self.operation_status = "Uploading CSV folder..."
            self.operation_kind = "load"
            self.operation_is_error = False
            self.operation_retry_load = False
            self.network_load_status = self.operation_status
            self.export_message = ""
            self.export_error = ""
            yield

            payloads = []
            for upload in files:
                file_name = str(upload.path or upload.name or "uploaded-file")
                payloads.append((file_name, await upload.read()))

            csv_folder = save_uploads_as_csv_folder(payloads, rx.get_upload_dir())
            async for _ in self._load_canvas_from_selected_network_directory(
                csv_folder,
                remember=False,
            ):
                yield
        except Exception as exc:
            self.export_error = f"Could not load uploaded network folder: {exc}"
            self.export_message = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error("Could not load network", self.export_error)
            yield

    async def load_network_directory_to_canvas(self, files: list[rx.UploadFile]):
        """Load the parent folder of a selected network CSV file onto the canvas."""
        try:
            selected_path_text = self.network_file_path.strip()
            if not selected_path_text and files:
                selected_file = files[0]
                selected_path_text = str(selected_file.path or "")

            if not selected_path_text:
                raise ValueError("Enter the path to a PyPSA CSV export folder.")

            async for _ in self._load_canvas_from_selected_network_directory(
                Path(selected_path_text)
            ):
                yield
        except Exception as exc:
            self.export_error = (
                f"Could not load selected network folder onto canvas: {exc}"
            )
            self.export_message = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error("Could not load network", self.export_error)
            yield

    async def _load_canvas_from_selected_network_directory(
        self,
        selected_directory: Path,
        remember: bool = True,
    ):
        """Load a selected CSV folder using Reflex yield updates."""
        async for _ in self._load_canvas_from_selected_network_path(
            selected_directory,
            remember=remember,
        ):
            yield

    async def _load_canvas_from_selected_network_path(
        self,
        selected_path: Path,
        remember: bool = True,
    ):
        """Load a selected PyPSA network path using Reflex yield updates."""
        network_path = selected_path.expanduser()
        self.is_loading_network = True
        self.is_load_dialog_open = False
        self.is_file_picker_open = False
        self.is_operation_dialog_open = True
        self.operation_title = "Loading network"
        self.operation_status = "Importing selected network..."
        self.operation_kind = "load"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.network_load_status = self.operation_status
        self.export_message = ""
        self.export_error = ""
        yield

        self.operation_status = f"Importing PyPSA network {network_path}..."
        self.network_load_status = self.operation_status
        yield

        try:
            artifacts = await asyncio.to_thread(load_network_artifacts, network_path)
        except Exception as exc:
            message = f"Could not import PyPSA network {network_path}: {exc}"
            self.load_error = message
            self.export_error = message
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error(
                "Could not load network folder",
                message,
                retry_load=True,
            )
            yield
            return

        save_format = network_save_format_for_path(network_path)
        save_folder = str(network_path) if save_format == "csv" else ""
        network, _loaded_network = self._apply_network_load_artifacts(
            artifacts,
            loaded_source=str(network_path),
            save_network_folder=save_folder,
            save_network_path=str(network_path),
            save_network_format=save_format,
        )
        self.network_name = str(network.name or network_path.stem or network_path.name)
        print(network)
        self.operation_status = "Building canvas object..."
        self.network_load_status = self.operation_status
        yield

        diagram_nodes, component_counters = await asyncio.to_thread(
            build_canvas_nodes_from_network,
            network,
        )
        layout_positions = await asyncio.to_thread(load_layout_positions, network_path)
        layout_regions = await asyncio.to_thread(load_layout_regions, network_path)
        apply_layout_positions(diagram_nodes, layout_positions)
        self._apply_canvas_nodes(diagram_nodes, component_counters, layout_regions)
        if remember and is_pypsa_csv_folder(network_path):
            await asyncio.to_thread(write_last_network_folder, network_path)
        yield

        if not any(
            not node["hidden"] and is_canvas_visible(node)
            for node in self.diagram_nodes
        ):
            self.operation_status = "Network loaded with no visible canvas components."
            self.load_message = f"Loaded {network_path} onto canvas."
            self.export_message = f"Loaded network {network_path} onto canvas."
            self.load_error = ""
            self.export_error = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.is_operation_dialog_open = False
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            yield
            return

        self.load_message = f"Loaded {network_path} onto canvas."
        self.export_message = f"Loaded network {network_path} onto canvas."
        self.load_error = ""
        self.export_error = ""
        self.is_loading_network = False
        self.network_load_status = ""
        self.is_operation_dialog_open = False
        self.operation_title = ""
        self.operation_status = ""
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        yield

    async def initialize_builder_on_load(self):
        """Reset the builder and reload the last local network folder if available."""
        await asyncio.to_thread(clean_upload_staging_dir, rx.get_upload_dir())
        self.reset_builder_on_load()
        yield

        last_network_folder = await asyncio.to_thread(read_last_network_folder)
        if last_network_folder is None:
            return

        if not await asyncio.to_thread(is_pypsa_csv_folder, last_network_folder):
            self.load_message = (
                f"Last network folder {last_network_folder} is no longer available. "
                "Using empty PyPSA network defaults."
            )
            self.load_error = ""
            yield
            return

        async for _ in self._load_canvas_from_selected_network_directory(
            last_network_folder,
            remember=False,
        ):
            yield

    def add_diagram_node(self, payload: dict[str, object]) -> None:
        """Add a dropped palette component to the diagram."""
        component_name = str(payload.get("component", ""))
        bus_node_id = str(payload.get("bus_node_id", ""))
        self._push_canvas_history()
        self._add_diagram_node_at(
            component_name,
            float(payload.get("x", 80)),
            float(payload.get("y", 80)),
            bus_node_id=bus_node_id,
        )

    def add_component_to_canvas(self, component_name: str) -> None:
        """Add a component to the canvas at an automatic position."""
        index = len(self.diagram_nodes)
        x = 80 + (index % 5) * 120
        y = 80 + (index // 5) * 90
        self._push_canvas_history()
        self._add_diagram_node_at(str(component_name), float(x), float(y))

    def _populate_canvas_from_network(
        self,
        network: object,
        trigger_route: bool = False,
    ) -> None:
        """Build diagram nodes and edges from a loaded PyPSA network."""
        diagram_nodes, component_counters = build_canvas_nodes_from_network(network)
        self._apply_canvas_nodes(diagram_nodes, component_counters)
        if trigger_route:
            self.route_version += 1

    def _apply_canvas_nodes(
        self,
        diagram_nodes: list[DiagramNode],
        component_counters: dict[str, int],
        canvas_regions: list[CanvasRegion] | None = None,
    ) -> None:
        """Assign prepared canvas nodes to state and rebuild derived data."""
        self.diagram_nodes = []
        self.diagram_edges = []
        self.canvas_regions = []
        self.diagram_model = {"components": [], "connections": [], "regions": []}
        self.network_component_rows = []
        self.network_connection_rows = []
        self.canvas_bus_names = []
        self.selected_node_id = ""
        self.selected_component_name = ""
        self.selected_attr_rows = []
        self.component_counters = {}
        self.armed_component = ""
        self.armed_branch_component = ""
        self.rectangle_selection_armed = False
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""
        self.is_mark_region_dialog_open = False
        self.mark_region_name = ""
        self.pending_region_bounds = {}
        self.pending_region_node_ids = []
        self.carrier_visibility_rows = []
        self.visible_canvas_carriers = []
        self.carrier_visibility_initialized = False
        if self._should_sync_network_data_view():
            self._sync_network_data_dialog()
        self._clear_canvas_history()

        self.diagram_nodes = diagram_nodes
        self.component_counters = component_counters
        self.canvas_regions = copy.deepcopy(canvas_regions or [])
        self._sync_diagram_model()
        self._mark_network_saved()
        self._request_canvas_fit_view()

    def _network_import_order(self) -> list[str]:
        """Return component list names in bus, branch, component import order."""
        return network_import_order()

    def _attrs_from_network_row(
        self,
        component_type: ComponentType,
        pypsa_name: object,
        row: object,
    ) -> dict[str, object]:
        """Convert a PyPSA static component row to diagram attributes."""
        return attrs_from_network_row(component_type, pypsa_name, row)

    def _diagram_node_from_imported_attrs(
        self,
        component_type: ComponentType,
        attrs: dict[str, object],
        x: float,
        y: float,
        hidden: bool,
    ) -> DiagramNode:
        """Create a diagram node from imported PyPSA attributes."""
        return diagram_node_from_imported_attrs(
            component_type,
            attrs,
            x,
            y,
            hidden,
            self.component_counters,
        )

    def _next_node_id(self, component_name: str) -> str:
        """Allocate the next stable diagram node id for a component type."""
        next_count = self.component_counters.get(component_name, 0) + 1
        self.component_counters[component_name] = next_count
        return f"{component_id_prefix(component_name)}_{next_count}"

    def _import_position_for_component(
        self,
        component_name: str,
        row_index: int,
        x_positions: dict[str, int],
        attrs: dict[str, object],
        bus_positions: dict[str, dict[str, float]],
        bus_component_counts: dict[str, int],
    ) -> tuple[float, float]:
        """Choose an initial canvas position for an imported component."""
        return import_position_for_component(
            component_name,
            row_index,
            x_positions,
            attrs,
            bus_positions,
            bus_component_counts,
        )

    def clear_canvas(self) -> None:
        """Clear all canvas state and selection state."""
        if self.diagram_nodes or self.canvas_regions:
            self._push_canvas_history()
        self.diagram_nodes = []
        self.diagram_edges = []
        self.canvas_regions = []
        self.diagram_model = {"components": [], "connections": [], "regions": []}
        self.network_component_rows = []
        self.network_connection_rows = []
        self.canvas_bus_names = []
        self.selected_node_id = ""
        self.selected_component_name = ""
        self.selected_attr_rows = []
        self.component_counters = {}
        self.armed_component = ""
        self.armed_branch_component = ""
        self.rectangle_selection_armed = False
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""
        self.is_mark_region_dialog_open = False
        self.mark_region_name = ""
        self.pending_region_bounds = {}
        self.pending_region_node_ids = []
        self.carrier_visibility_rows = []
        self.visible_canvas_carriers = []
        self.carrier_visibility_initialized = False

    def set_clear_canvas_dialog_open(self, value: bool) -> None:
        """Update whether the clear canvas confirmation is open."""
        self.is_clear_canvas_dialog_open = value

    def open_clear_canvas_dialog(self) -> None:
        """Open the clear canvas confirmation."""
        self.is_clear_canvas_dialog_open = True

    def confirm_clear_canvas(self) -> None:
        """Clear the canvas and close the confirmation."""
        self.clear_canvas()
        self.is_clear_canvas_dialog_open = False

    def new_network(self) -> None:
        """Start a new unnamed network from an empty canvas."""
        self.clear_canvas()
        self._clear_canvas_history()
        self.network_name = "Unnamed"
        self.loaded_source = ""
        self.save_network_folder = ""
        self.save_network_path = ""
        self.save_network_format = ""
        self.other_csv_tables = {}
        self.time_series_tables = {}
        self.is_carrier_visibility_dialog_open = False
        self.carrier_visibility_rows = []
        self.visible_canvas_carriers = []
        self.carrier_visibility_initialized = False
        self.load_message = "Using empty PyPSA network defaults."
        self.load_error = ""
        self.export_message = ""
        self.export_error = ""
        self.is_file_picker_open = False
        self.is_file_picker_overwrite_dialog_open = False
        self.file_picker_selected_path = ""
        self.network_has_unsaved_changes = False
        if self._should_sync_network_data_view():
            self._sync_network_data_dialog()

    def reset_builder_on_load(self) -> None:
        """Reset transient builder state when the app page is loaded."""
        self.active_view = "canvas"
        self.clear_canvas()
        self._clear_canvas_history()
        self.load_message = "Using empty PyPSA network defaults."
        self.load_error = ""
        self.loaded_source = ""
        self.network_has_unsaved_changes = False
        self.save_network_folder = ""
        self.save_network_path = ""
        self.save_network_format = ""
        self.other_csv_tables = {}
        self.time_series_tables = {}
        self.is_carrier_visibility_dialog_open = False
        self.carrier_visibility_rows = []
        self.visible_canvas_carriers = []
        self.carrier_visibility_initialized = False
        self.is_loading_network = False
        self.network_load_status = ""
        self.export_message = ""
        self.export_error = ""
        self.is_network_name_dialog_open = False
        self.is_load_dialog_open = False
        self.is_export_dialog_open = False
        self.is_file_picker_open = False
        self.is_file_picker_overwrite_dialog_open = False
        self.file_picker_selected_path = ""
        self.is_operation_dialog_open = False
        self.operation_title = ""
        self.operation_status = ""
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        self.is_clear_canvas_dialog_open = False
        self.is_network_data_dialog_open = False
        self.network_data_tabs = []
        self.is_export_dialog_for_save = False
        self.unsaved_network_action = ""
        self.unsaved_network_action_payload = ""
        self.is_unsaved_changes_dialog_open = False

    async def close_operation_dialog(self):
        """Close the current operation dialog."""
        should_retry_load = self.operation_retry_load
        self.is_operation_dialog_open = False
        self.operation_title = ""
        self.operation_status = ""
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        yield

        if should_retry_load:
            self.is_load_dialog_open = True
            yield

    def show_operation_error(
        self,
        title: str,
        message: str,
        retry_load: bool = False,
    ) -> None:
        """Show a closeable operation error dialog."""
        self.is_operation_dialog_open = True
        self.operation_title = title
        self.operation_status = message
        self.operation_kind = "error"
        self.operation_is_error = True
        self.operation_retry_load = retry_load

    def _current_saved_network_path(self) -> Path | None:
        """Return the current on-disk network source, if one exists."""
        source_text = (
            self.save_network_path or self.save_network_folder or self.loaded_source
        ).strip()
        if not source_text:
            return None
        return Path(source_text).expanduser()

    async def open_network_in_jupyter(self):
        """Create and open a JupyterLab notebook for the current saved network."""
        network_path = self._current_saved_network_path()
        if network_path is None:
            self.export_error = (
                "Save, export, or load a network before opening Jupyter."
            )
            self.export_message = ""
            self.show_operation_error("Could not open Jupyter", self.export_error)
            yield
            return
        if self._has_unsaved_network_changes():
            self.export_error = (
                "Save or export the current network before opening it in Jupyter."
            )
            self.export_message = ""
            self.show_operation_error("Could not open Jupyter", self.export_error)
            yield
            return
        if not await asyncio.to_thread(network_path.exists):
            self.export_error = f"Network path no longer exists: {network_path}"
            self.export_message = ""
            self.show_operation_error("Could not open Jupyter", self.export_error)
            yield
            return

        self.is_operation_dialog_open = True
        self.operation_title = "Opening Jupyter"
        self.operation_status = "Creating notebook and starting JupyterLab..."
        self.operation_kind = "jupyter"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.export_message = ""
        self.export_error = ""
        yield

        try:
            notebook_path = await asyncio.to_thread(
                create_jupyter_network_notebook,
                network_path,
            )
            self.operation_status = "Running notebook first cell..."
            yield
            await asyncio.to_thread(
                execute_jupyter_network_notebook,
                notebook_path,
            )
            self.operation_status = "Starting JupyterLab..."
            yield
            url = await asyncio.to_thread(jupyter_lab_notebook_url, notebook_path)
            self.is_operation_dialog_open = False
            self.operation_title = ""
            self.operation_status = ""
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            self.export_message = f"Opened Jupyter notebook {notebook_path}."
            self.export_error = ""
            yield rx.redirect(url, is_external=True)
        except Exception as exc:
            self.export_error = f"Could not open Jupyter: {exc}"
            self.export_message = ""
            self.show_operation_error("Could not open Jupyter", self.export_error)
            yield

    def set_selected_router_name(self, value: str) -> None:
        """Select the router used by the Auto route button."""
        router_name = str(value)
        available_names = {option["name"] for option in self.router_options}
        if router_name in available_names:
            self.selected_router_name = router_name

    def set_show_left_sidebar(self, value: bool) -> None:
        """Update whether the left palette sidebar is visible."""
        self.show_left_sidebar = bool(value)

    def set_show_right_sidebar(self, value: bool) -> None:
        """Update whether the right selection sidebar is visible."""
        self.show_right_sidebar = bool(value)

    def show_canvas_view(self) -> None:
        """Show the schematic canvas view."""
        self.active_view = "canvas"

    def show_network_data_view(self) -> None:
        """Show the editable whole-network data view."""
        self._sync_network_data_dialog()
        self.active_view = "network-data"

    def show_builder_view(self) -> None:
        """Show the schematic builder view."""
        self.show_canvas_view()

    def show_debug_network_view(self) -> None:
        """Show the debug network object view."""
        self.active_view = "debug-network"

    def show_catalog_view(self) -> None:
        """Show the component catalog view."""
        self.active_view = "catalog"

    def _router_label(self, router_name: str) -> str:
        """Return the display label for a router name."""
        for option in self.router_options:
            if option["name"] == router_name:
                return option["label"]
        return router_name

    def _router_network(self) -> RouterNetwork:
        """Return the current canvas state in the Python router contract shape."""
        return {
            "nodes": copy.deepcopy(self.diagram_nodes),
            "edges": copy.deepcopy(self.diagram_edges),
            "diagram_model": copy.deepcopy(self.diagram_model),
            "metadata": {
                "selected_node_id": self.selected_node_id,
                "bus_names": copy.deepcopy(self.canvas_bus_names),
                "spacing": {
                    "bus_x": 220,
                    "component_x": BUS_COMPONENT_HORIZONTAL_OFFSET,
                    "component_y": 80,
                },
            },
        }

    def _run_python_router(
        self,
        router_name: str,
        router_network: RouterNetwork,
    ) -> RouterNetwork:
        """Run a Python router by name and return its routed network object."""
        router = PYTHON_ROUTERS.get(router_name)
        if router is None:
            raise ValueError(f"Unknown Python router: {router_name}.")
        routed_network = router.route(router_network)
        if not isinstance(routed_network, dict):
            raise ValueError(f"Router {router_name} did not return a network object.")
        return routed_network

    def _apply_routed_network(self, routed_network: RouterNetwork) -> None:
        """Validate and apply a full routed network returned by a Python router."""
        routed_nodes = routed_network.get("nodes", [])
        if not isinstance(routed_nodes, list):
            raise ValueError("Router result must contain a nodes list.")

        current_by_id = {str(node["id"]): node for node in self.diagram_nodes}
        routed_by_id: dict[str, dict[str, object]] = {}
        for routed_node in routed_nodes:
            if not isinstance(routed_node, dict):
                raise ValueError("Router result contains a non-object node.")
            node_id = str(routed_node.get("id", ""))
            if not node_id:
                raise ValueError("Router result contains a node without an id.")
            if node_id in routed_by_id:
                raise ValueError(
                    f"Router result contains duplicate node id: {node_id}."
                )
            routed_by_id[node_id] = routed_node

        missing_ids = set(current_by_id) - set(routed_by_id)
        unknown_ids = set(routed_by_id) - set(current_by_id)
        if missing_ids:
            raise ValueError(
                f"Router result is missing nodes: {', '.join(sorted(missing_ids))}."
            )
        if unknown_ids:
            raise ValueError(
                f"Router result contains unknown nodes: {', '.join(sorted(unknown_ids))}."
            )

        routed_order = [str(node.get("id", "")) for node in routed_nodes]
        updated_nodes: list[DiagramNode] = []
        for node_id in routed_order:
            current_node = copy.deepcopy(current_by_id[node_id])
            routed_node = routed_by_id[node_id]
            if (
                str(routed_node.get("component", current_node["component"]))
                != current_node["component"]
            ):
                raise ValueError(f"Router cannot change component type for {node_id}.")

            position = routed_node.get("position", current_node["position"])
            if not isinstance(position, dict):
                raise ValueError(f"Router result node {node_id} has invalid position.")
            current_node["position"] = {
                "x": float(position.get("x", current_node["position"]["x"])),
                "y": float(position.get("y", current_node["position"]["y"])),
            }

            routed_attrs = routed_node.get("attrs")
            if isinstance(routed_attrs, dict):
                current_node["attrs"] = copy.deepcopy(routed_attrs)
            routed_layout = routed_node.get("layout")
            if isinstance(routed_layout, dict):
                next_layout = copy.deepcopy(routed_layout)
                current_layout = current_node.get("layout", {})
                if (
                    isinstance(current_layout, dict)
                    and current_layout.get("locked")
                    and "locked" not in next_layout
                ):
                    next_layout["locked"] = True
                current_node["layout"] = next_layout
            if isinstance(routed_node.get("hidden"), bool):
                current_node["hidden"] = bool(routed_node["hidden"])

            component = NETWORK_MODEL.component(current_node["component"])
            current_node["attr_rows"] = diagram_attr_rows(
                component, current_node["attrs"]
            )
            updated_nodes.append(current_node)

        self.diagram_nodes = updated_nodes
        self._sync_diagram_model()
        if self.selected_node_id:
            self.select_node(self.selected_node_id)

    def _locked_node_positions(self) -> dict[str, dict[str, float]]:
        """Return exact current positions for locked visible diagram nodes."""
        locked_positions: dict[str, dict[str, float]] = {}
        for node in self.diagram_nodes:
            if node.get("hidden"):
                continue
            if not self.is_node_layout_locked(node):
                continue
            position = node.get("position", {})
            if not isinstance(position, dict):
                continue
            try:
                locked_positions[str(node["id"])] = {
                    "x": float(position.get("x", 0)),
                    "y": float(position.get("y", 0)),
                }
            except TypeError, ValueError:
                continue
        return locked_positions

    def _restore_locked_router_positions(
        self,
        routed_network: RouterNetwork,
        locked_positions: dict[str, dict[str, float]],
    ) -> None:
        """Restore exact locked node positions in a routed network result."""
        routed_nodes = routed_network.get("nodes", [])
        if not isinstance(routed_nodes, list):
            return
        for node in routed_nodes:
            if not isinstance(node, dict):
                continue
            locked_position = locked_positions.get(str(node.get("id", "")))
            if locked_position is None:
                continue
            node["position"] = {
                "x": locked_position["x"],
                "y": locked_position["y"],
            }
            layout = node.setdefault("layout", {})
            if isinstance(layout, dict):
                layout["locked"] = True
            else:
                node["layout"] = {"locked": True}

    async def auto_route_canvas(self):
        """Route the canvas with the selected JavaScript or Python router."""
        if not any(
            not node["hidden"] and is_canvas_visible(node)
            for node in self.diagram_nodes
        ):
            self.export_error = "Add at least one component before routing."
            self.export_message = ""
            yield
            return

        selected_router_name = self.selected_router_name or JS_ELK_ROUTER_NAME
        router_label = self._router_label(selected_router_name)
        self.is_operation_dialog_open = True
        self.operation_title = "Auto routing network"
        self.operation_status = f"Running {router_label}..."
        self.operation_kind = "route"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.export_message = ""
        self.export_error = ""
        yield

        self._refresh_bus_side_layout()
        locked_positions = self._locked_node_positions()
        if selected_router_name == JS_ELK_ROUTER_NAME:
            self.route_version += 1
            yield
            return

        try:
            router_network = self._router_network()
            routed_network = await asyncio.to_thread(
                self._run_python_router,
                selected_router_name,
                router_network,
            )
            self._apply_bus_side_constraints_to_router_network(routed_network)
            self._restore_locked_router_positions(routed_network, locked_positions)
            self._push_canvas_history()
            self._apply_routed_network(routed_network)
            self._refresh_bus_side_layout()
            self._request_canvas_fit_view()
            self.operation_status = f"{router_label} completed."
            self.is_operation_dialog_open = False
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            self.export_message = f"{router_label} completed."
            self.export_error = ""
            yield
        except Exception as exc:
            self.export_error = f"Could not route network: {exc}"
            self.export_message = ""
            self.show_operation_error("Could not route network", self.export_error)
            yield

    def finish_auto_route(self) -> None:
        """Close route-related progress dialogs after React Flow finishes."""
        if self.operation_kind != "route":
            return
        self.operation_status = "Auto routing completed."
        self._request_canvas_fit_view()
        self.is_operation_dialog_open = False
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        self.export_message = "Auto routing completed."
        self.export_error = ""

    def set_network_name(self, value: str) -> None:
        """Update the PyPSA network name used for export."""
        self.network_name = str(value).strip() or "Unnamed"

    def set_network_name_dialog_open(self, value: bool) -> None:
        """Update whether the network name dialog is open."""
        self.is_network_name_dialog_open = value

    def open_network_name_dialog(self) -> None:
        """Open the network name dialog."""
        self.is_network_name_dialog_open = True

    def close_network_name_dialog(self) -> None:
        """Close the network name dialog."""
        self.is_network_name_dialog_open = False

    def set_network_file_path(self, value: str) -> None:
        """Store a user-entered network CSV folder path."""
        self.network_file_path = value

    def set_load_dialog_open(self, value: bool) -> None:
        """Update whether the load dialog is open."""
        self.is_load_dialog_open = value

    def set_unsaved_changes_dialog_open(self, value: bool) -> None:
        """Update whether the unsaved-changes dialog is open."""
        self.is_unsaved_changes_dialog_open = value
        if not value and self.unsaved_network_action:
            self.unsaved_network_action = ""
            self.unsaved_network_action_payload = ""

    def _set_unsaved_network_action(
        self,
        action: str,
        payload: str = "",
    ) -> None:
        """Store a pending network action blocked by unsaved changes."""
        self.unsaved_network_action = action
        self.unsaved_network_action_payload = payload
        self.is_unsaved_changes_dialog_open = True

    async def _run_pending_network_action(self):
        """Run the pending network action after unsaved changes are handled."""
        action = self.unsaved_network_action
        payload = self.unsaved_network_action_payload
        self.unsaved_network_action = ""
        self.unsaved_network_action_payload = ""
        if action == "new_network":
            self.new_network()
            self.open_network_name_dialog()
        elif action == "load_network_directory":
            self.open_file_picker("load")
        elif action == "load_pypsa_example_network":
            async for _ in self.load_pypsa_example_network(payload):
                yield

    def request_new_network(self) -> None:
        """Start a new network or ask to handle unsaved changes first."""
        if self._has_unsaved_network_changes():
            self._set_unsaved_network_action("new_network")
            return
        self.new_network()
        self.open_network_name_dialog()

    def request_load_network_directory_to_canvas(self) -> None:
        """Open the local network picker or ask to handle unsaved changes first."""
        if self._has_unsaved_network_changes():
            self._set_unsaved_network_action("load_network_directory")
            return
        self.open_file_picker("load")

    async def request_load_pypsa_example_network(self, network_path: str):
        """Load a bundled example network or ask to handle unsaved changes first."""
        network_path_text = str(network_path)
        if self._has_unsaved_network_changes():
            self._set_unsaved_network_action(
                "load_pypsa_example_network",
                network_path_text,
            )
            return
        async for _ in self.load_pypsa_example_network(network_path_text):
            yield

    async def ignore_unsaved_network_changes_and_open(self):
        """Ignore unsaved changes and continue with the blocked network action."""
        self.is_unsaved_changes_dialog_open = False
        async for _ in self._run_pending_network_action():
            yield

    async def save_unsaved_network_changes_and_open(self):
        """Save unsaved changes and continue with the blocked network action."""
        self.is_unsaved_changes_dialog_open = False
        async for _ in self.save_canvas_network_to_loaded_folder():
            yield
        if self._has_unsaved_network_changes():
            return
        async for _ in self._run_pending_network_action():
            yield

    async def choose_network_directory_and_load(self):
        """Open the web dialog for loading a local CSV folder path."""
        self.open_file_picker("load")
        yield

    def open_file_picker(self, mode: str) -> None:
        """Open the server-side network file picker in the requested mode."""
        normalized_mode = str(mode or "load")
        if normalized_mode not in {"load", "save", "save_as"}:
            normalized_mode = "load"
        self.file_picker_mode = normalized_mode
        self.file_picker_save_format = (
            self.save_network_format
            if normalized_mode == "save" and self.save_network_format
            else "csv"
        )
        if self.file_picker_save_format not in FILE_PICKER_SAVE_FORMATS:
            self.file_picker_save_format = "csv"
        start_dir = Path(self.file_picker_current_dir or file_picker_start_dir())
        if normalized_mode in {"save", "save_as"}:
            current_target = (
                Path(self.save_network_path).expanduser()
                if self.save_network_path
                else None
            )
            if current_target is not None and current_target.parent.exists():
                start_dir = (
                    current_target if current_target.is_dir() else current_target.parent
                )
        if not start_dir.exists() or not start_dir.is_dir():
            start_dir = file_picker_start_dir()
            if not start_dir.exists() or not start_dir.is_dir():
                start_dir = file_picker_home_path()
        self.file_picker_current_dir = str(start_dir)
        self.file_picker_path_input = str(start_dir)
        self.file_picker_selected_path = ""
        self.file_picker_target_name = default_save_file_name(
            self.network_name,
            self.file_picker_save_format,
        )
        self.file_picker_new_folder_name = ""
        self.file_picker_error = ""
        self.file_picker_warning = ""
        self.is_file_picker_overwrite_dialog_open = False
        self.pending_file_picker_target_path = ""
        self.pending_file_picker_target_format = ""
        self.refresh_file_picker_entries()
        self.is_file_picker_open = True

    def refresh_file_picker_entries(self) -> None:
        """Reload entries for the current file picker directory."""
        entries, warning, error = scan_file_picker_directory(
            self.file_picker_current_dir,
            self.file_picker_mode,
            self.file_picker_save_format,
            self.file_picker_show_hidden,
        )
        self.file_picker_entries = entries
        self.file_picker_warning = warning
        self.file_picker_error = error
        self.file_picker_roots = file_picker_root_entries()

    def _persist_file_picker_path(self, path: str | Path) -> None:
        """Persist the file picker path without interrupting picker navigation."""
        try:
            write_file_picker_last_path(path)
        except OSError as exc:
            self.file_picker_warning = f"Could not persist picker path: {exc}"

    def set_file_picker_open(self, value: bool) -> None:
        """Update whether the file picker dialog is open."""
        self.is_file_picker_open = value
        if not value:
            self.file_picker_error = ""
            self.file_picker_warning = ""
            self.file_picker_selected_path = ""

    def set_file_picker_path_input(self, value: str) -> None:
        """Update the editable picker path bar."""
        self.file_picker_path_input = value

    def set_file_picker_target_name(self, value: str) -> None:
        """Update the save target file or folder name."""
        self.file_picker_target_name = value

    def set_file_picker_new_folder_name(self, value: str) -> None:
        """Update the new folder name field."""
        self.file_picker_new_folder_name = value

    def set_file_picker_show_hidden(self, value: bool) -> None:
        """Toggle hidden file visibility in the picker."""
        self.file_picker_show_hidden = bool(value)
        self.refresh_file_picker_entries()

    def set_file_picker_save_format(self, value: str) -> None:
        """Update the picker save format and default target name."""
        next_format = str(value or "csv").strip().lower()
        if next_format not in FILE_PICKER_SAVE_FORMATS:
            next_format = "csv"
        self.file_picker_save_format = next_format
        self.file_picker_selected_path = ""
        self.file_picker_target_name = default_save_file_name(
            self.network_name,
            next_format,
        )
        self.refresh_file_picker_entries()

    def navigate_file_picker_to_path(self, path_text: str) -> None:
        """Navigate the picker to a directory path."""
        target = Path(str(path_text or "")).expanduser()
        if not target.exists():
            self.file_picker_error = f"Path does not exist: {target}"
            return
        if target.is_file():
            target = target.parent
        if not target.is_dir():
            self.file_picker_error = f"Path is not a directory: {target}"
            return
        self.file_picker_current_dir = str(target)
        self.file_picker_path_input = str(target)
        self.file_picker_selected_path = ""
        self.file_picker_error = ""
        self.refresh_file_picker_entries()
        self._persist_file_picker_path(target)

    def navigate_file_picker_from_input(self) -> None:
        """Navigate the picker using the path bar value."""
        self.navigate_file_picker_to_path(self.file_picker_path_input)

    def navigate_file_picker_parent(self) -> None:
        """Navigate the picker to the current directory's parent."""
        current = Path(self.file_picker_current_dir).expanduser()
        parent = current.parent
        if parent == current:
            return
        self.navigate_file_picker_to_path(str(parent))

    def select_file_picker_path(self, path_text: str) -> None:
        """Select a file or folder as the pending picker target."""
        target = Path(str(path_text)).expanduser()
        self.file_picker_selected_path = str(target)
        if self.file_picker_mode in {"save", "save_as"} and target.is_file():
            self.file_picker_current_dir = str(target.parent)
            self.file_picker_path_input = str(target.parent)
            self.file_picker_target_name = target.name
        self.file_picker_error = ""
        self._persist_file_picker_path(target)

    def create_file_picker_folder(self) -> None:
        """Create a child folder in the current picker directory."""
        if self.file_picker_mode not in {"save", "save_as"}:
            return
        folder_name = self.file_picker_new_folder_name.strip()
        if not folder_name:
            self.file_picker_error = "Enter a folder name first."
            return
        folder_path = Path(folder_name)
        if folder_path.is_absolute() or ".." in folder_path.parts:
            self.file_picker_error = "Use a simple folder name without '..'."
            return
        target = Path(self.file_picker_current_dir).expanduser() / folder_path
        try:
            target.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            self.file_picker_error = f"Could not create folder: {exc}"
            return
        self.file_picker_new_folder_name = ""
        self.file_picker_error = ""
        self.refresh_file_picker_entries()

    def _selected_file_picker_save_target(self) -> tuple[Path, str]:
        """Return the picker save target path and format."""
        save_format = self.file_picker_save_format
        if save_format not in FILE_PICKER_SAVE_FORMATS:
            save_format = "csv"
        if save_format == "csv":
            selected = self.file_picker_selected_path.strip()
            target = (
                Path(selected).expanduser()
                if selected
                else Path(self.file_picker_current_dir).expanduser()
            )
            return target, save_format

        target_name = self.file_picker_target_name.strip()
        if not target_name:
            raise ValueError("Enter a file name before saving.")
        target_path = Path(target_name).expanduser()
        if not target_path.is_absolute():
            target_path = Path(self.file_picker_current_dir).expanduser() / target_path
        return apply_save_format_extension(target_path, save_format), save_format

    def _selected_file_picker_load_target(self) -> Path:
        """Return the picker load target path."""
        selected = self.file_picker_selected_path.strip()
        if selected:
            return Path(selected).expanduser()
        path_input = Path(self.file_picker_path_input).expanduser()
        if path_input.exists():
            return path_input
        raise ValueError("Select a PyPSA network folder or supported file.")

    def _save_target_requires_confirmation(
        self, target_path: Path, save_format: str
    ) -> bool:
        """Return whether saving to the target should ask for overwrite confirmation."""
        if save_format == "csv":
            if not target_path.exists():
                return False
            if not target_path.is_dir():
                return True
            return any(target_path.iterdir())
        return target_path.exists()

    async def confirm_file_picker(self):
        """Run the load or save action selected in the file picker."""
        try:
            if self.file_picker_mode == "load":
                target_path = self._selected_file_picker_load_target()
                self._persist_file_picker_path(target_path)
                self.is_file_picker_open = False
                async for _ in self._load_canvas_from_selected_network_path(
                    target_path
                ):
                    yield
                return

            target_path, save_format = self._selected_file_picker_save_target()
            if self._save_target_requires_confirmation(target_path, save_format):
                self.pending_file_picker_target_path = str(target_path)
                self.pending_file_picker_target_format = save_format
                self.is_file_picker_overwrite_dialog_open = True
                yield
                return
            self._persist_file_picker_path(target_path)
            async for _ in self._save_canvas_network_to_path(target_path, save_format):
                yield
        except Exception as exc:
            self.file_picker_error = str(exc)
            yield

    def set_file_picker_overwrite_dialog_open(self, value: bool) -> None:
        """Update whether the picker overwrite confirmation is open."""
        self.is_file_picker_overwrite_dialog_open = value
        if not value:
            self.pending_file_picker_target_path = ""
            self.pending_file_picker_target_format = ""

    async def confirm_file_picker_overwrite(self):
        """Save to the pending picker target after overwrite confirmation."""
        target_path = Path(self.pending_file_picker_target_path).expanduser()
        save_format = self.pending_file_picker_target_format
        self.is_file_picker_overwrite_dialog_open = False
        self.pending_file_picker_target_path = ""
        self.pending_file_picker_target_format = ""
        self._persist_file_picker_path(target_path)
        async for _ in self._save_canvas_network_to_path(target_path, save_format):
            yield

    def arm_branch_component(self, component_name: str) -> None:
        """Arm or disarm a branch component type for bus-to-bus creation."""
        component_name = str(component_name)
        if component_name not in NETWORK_MODEL.branch_components:
            return
        self.armed_component = ""
        self.rectangle_selection_armed = False
        if self.armed_branch_component == component_name:
            self.armed_branch_component = ""
            self.pending_branch_node_id = ""
            self.branch_bus0_node_id = ""
            return
        self.armed_branch_component = component_name
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""

    def arm_canvas_component(self, component_name: str) -> None:
        """Arm or disarm a non-branch component for click-to-place creation."""
        component_name = str(component_name)
        if component_name not in NETWORK_MODEL.all_components:
            return
        if component_name in NETWORK_MODEL.branch_components:
            self.arm_branch_component(component_name)
            return
        component = NETWORK_MODEL.component(component_name)
        if component_name != "buses" and not has_bus_attr(component):
            return
        self.armed_branch_component = ""
        self.rectangle_selection_armed = False
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""
        self.armed_component = (
            "" if self.armed_component == component_name else component_name
        )

    def toggle_rectangle_selection_armed(self) -> None:
        """Toggle the one-shot rectangle selection tool."""
        next_armed = not self.rectangle_selection_armed
        self.rectangle_selection_armed = next_armed
        if next_armed:
            self.armed_component = ""
            self.armed_branch_component = ""
            self.pending_branch_node_id = ""
            self.branch_bus0_node_id = ""

    def set_rectangle_selection_armed(self, armed: bool) -> None:
        """Set whether rectangle selection mode is armed."""
        self.rectangle_selection_armed = bool(armed)

    def handle_branch_bus_click(self, node_id: str) -> None:
        """Advance the two-click branch creation workflow for a bus node."""
        if not self.armed_branch_component:
            self.select_node(node_id)
            return

        bus_name = self._bus_name_for_node_id(str(node_id))
        if not bus_name:
            return

        if not self.pending_branch_node_id:
            self._push_canvas_history()
            branch_node = self._create_hidden_branch_node(
                self.armed_branch_component,
                bus_name,
            )
            self.diagram_nodes.append(branch_node)
            self.pending_branch_node_id = branch_node["id"]
            self.branch_bus0_node_id = str(node_id)
            self._sync_diagram_model()
            self.select_node(branch_node["id"])
            return

        if str(node_id) == self.branch_bus0_node_id:
            self.diagram_nodes = [
                node
                for node in self.diagram_nodes
                if node["id"] != self.pending_branch_node_id
            ]
            self.pending_branch_node_id = ""
            self.branch_bus0_node_id = ""
            self._sync_diagram_model()
            self.select_node(str(node_id))
            return

        for node in self.diagram_nodes:
            if node["id"] != self.pending_branch_node_id:
                continue
            node["attrs"]["bus1"] = bus_name
            component = NETWORK_MODEL.component(node["component"])
            node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
            completed_branch_id = node["id"]
            self.pending_branch_node_id = ""
            self.branch_bus0_node_id = ""
            self._sync_diagram_model()
            self.select_node(completed_branch_id)
            return

    def set_export_base_folder(self, value: str) -> None:
        """Update the export destination base folder."""
        self.export_base_folder = value

    def set_export_dialog_open(self, value: bool) -> None:
        """Update whether the export dialog is open."""
        self.is_export_dialog_open = value
        if not value:
            self.is_export_dialog_for_save = False

    async def choose_export_folder(self):
        """Open the network Save As picker."""
        self.open_file_picker("save_as")
        yield

    async def choose_export_folder_and_export(self):
        """Export using the configured destination path."""
        async for _ in self.export_canvas_network():
            yield

    async def load_network_directory_path_to_canvas(self):
        """Load the server-local CSV folder path entered in the load dialog."""
        selected_path_text = self.network_file_path.strip()
        if not selected_path_text:
            self.export_error = "Enter the path to a PyPSA CSV export folder."
            self.export_message = ""
            self.show_operation_error("Could not load network", self.export_error)
            yield
            return

        try:
            async for _ in self._load_canvas_from_selected_network_directory(
                Path(selected_path_text)
            ):
                yield
        except Exception as exc:
            self.export_error = (
                f"Could not load selected network folder onto canvas: {exc}"
            )
            self.export_message = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error("Could not load network", self.export_error)
            yield

    async def save_canvas_network_to_loaded_folder(self):
        """Save the current diagram model back to the current network target."""
        if not self.diagram_nodes:
            self.export_error = "Add at least one component before saving."
            self.export_message = ""
            yield
            return
        if not self.save_network_path:
            self.open_file_picker("save")
            yield
            return

        save_format = self.save_network_format or network_save_format_for_path(
            self.save_network_path
        )
        async for _ in self._save_canvas_network_to_path(
            Path(self.save_network_path),
            save_format,
        ):
            yield

    async def _save_canvas_network_to_path(
        self,
        target_path: Path,
        save_format: str,
    ):
        """Save the current diagram model to a PyPSA network path."""
        if not self.diagram_nodes:
            self.export_error = "Add at least one component before saving."
            self.export_message = ""
            yield
            return

        normalized_format = normalize_network_export_format(save_format, target_path)
        if (
            normalized_format == "csv"
            and target_path.exists()
            and not target_path.is_dir()
        ):
            self.export_error = "CSV folder exports require a directory target."
            self.export_message = ""
            self.show_operation_error("Could not save network", self.export_error)
            yield
            return

        self.is_operation_dialog_open = True
        self.is_export_dialog_open = False
        self.is_file_picker_open = False
        self.operation_title = "Saving network"
        self.operation_status = f"Writing PyPSA network to {target_path}..."
        self.operation_kind = "save"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.export_message = ""
        self.export_error = ""
        yield

        try:
            extra_csv_tables = self._extra_csv_tables_for_export()
            export_path = await asyncio.to_thread(
                export_diagram_to_network_path,
                self.diagram_model,
                NETWORK_MODEL,
                target_path,
                normalized_format,
                self.network_name,
                str(target_path) if normalized_format == "csv" else None,
                extra_csv_tables,
            )
            self.loaded_source = str(export_path)
            self.save_network_path = str(export_path)
            self.save_network_format = normalized_format
            self.save_network_folder = (
                str(export_path) if normalized_format == "csv" else ""
            )
            self._mark_network_saved()
            self.export_message = f"Saved network to {export_path}."
            self.export_error = ""
            self.is_operation_dialog_open = False
            self.operation_title = ""
            self.operation_status = ""
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            yield rx.toast.success(f"Saved PyPSA network to {export_path}.")
        except Exception as exc:
            self.export_error = f"Could not save network: {exc}"
            self.export_message = ""
            self.show_operation_error("Could not save network", self.export_error)
            yield

    async def confirm_export_dialog(self):
        """Run export or save based on the current export dialog mode."""
        if self.is_export_dialog_for_save:
            self.is_export_dialog_for_save = False
            self.is_export_dialog_open = False
            selected_folder = str(self.export_base_folder).strip()
            if not selected_folder:
                self.export_error = (
                    "Enter a destination folder path before saving this network."
                )
                self.export_message = ""
                return
            self.save_network_folder = selected_folder
            self.save_network_path = selected_folder
            self.save_network_format = "csv"
            async for _ in self.save_canvas_network_to_loaded_folder():
                yield
            return

        async for _ in self.export_canvas_network():
            yield

    async def export_canvas_network(self):
        """Export the current diagram model as a PyPSA CSV folder."""
        if not self.diagram_nodes:
            self.export_error = "Add at least one component before exporting."
            self.export_message = ""
            yield
            return

        self.is_operation_dialog_open = True
        self.operation_title = "Saving network"
        self.operation_status = "Creating PyPSA network and writing CSV files..."
        self.operation_kind = "export"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.export_message = ""
        self.export_error = ""
        yield

        try:
            extra_csv_tables = self._extra_csv_tables_for_export()
            export_path = await asyncio.to_thread(
                export_diagram_to_network_path,
                self.diagram_model,
                NETWORK_MODEL,
                self.export_base_folder,
                "csv",
                self.network_name,
                self.save_network_folder or None,
                extra_csv_tables,
            )
            self.loaded_source = str(export_path)
            self.save_network_folder = str(export_path)
            self.save_network_path = str(export_path)
            self.save_network_format = "csv"
            self._mark_network_saved()
            self.operation_status = "Network saved."
            self.export_message = ""
            self.export_error = ""
            self.is_export_dialog_open = False
            self.is_operation_dialog_open = False
            self.operation_title = ""
            self.operation_status = ""
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            yield rx.toast.success(f"Exported PyPSA CSV folder to {export_path}.")
        except Exception as exc:
            self.export_error = f"Could not export network: {exc}"
            self.export_message = ""
            self.show_operation_error("Could not save network", self.export_error)
            yield

    def _add_diagram_node_at(
        self,
        component_name: str,
        x: float,
        y: float,
        bus_node_id: str = "",
    ) -> None:
        """Add a component node at a position, optionally attached to a bus."""
        if component_name not in NETWORK_MODEL.all_components:
            return
        component = NETWORK_MODEL.component(component_name)
        if (
            component_name != "buses"
            and not component.is_branch_component
            and not has_bus_attr(component)
        ):
            return
        if component_name in NETWORK_MODEL.branch_components:
            self.arm_branch_component(component_name)
            return

        next_count = self.component_counters.get(component_name, 0) + 1
        self.component_counters[component_name] = next_count
        node_id = f"{component_id_prefix(component_name)}_{next_count}"
        node = make_diagram_node(
            component_name=component_name,
            node_id=node_id,
            x=x,
            y=y,
        )
        if "name" in node["attrs"] and not node["attrs"].get("name"):
            node["attrs"]["name"] = node_id
            component = NETWORK_MODEL.component(component_name)
            node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
        if bus_node_id and "bus" in node["attrs"]:
            bus_name = self._bus_name_for_node_id(bus_node_id)
            if bus_name:
                node["attrs"]["bus"] = bus_name
                bus_position = self._node_position(bus_node_id)
                if bus_position:
                    if component_name == "generators":
                        node["position"] = {
                            "x": bus_position["x"] - BUS_COMPONENT_DROP_OFFSET,
                            "y": bus_position["y"] + 8,
                        }
                        node.setdefault("layout", {})["bus_side"] = "left"
                    else:
                        node["position"] = {
                            "x": bus_position["x"] + BUS_COMPONENT_DROP_OFFSET,
                            "y": bus_position["y"] + 8,
                        }
                        node.setdefault("layout", {})["bus_side"] = "right"
                component = NETWORK_MODEL.component(component_name)
                node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
        self.diagram_nodes.append(node)
        self._sync_diagram_model()
        self.select_node(node_id)

    def _create_hidden_branch_node(
        self,
        component_name: str,
        bus0_name: str,
    ) -> DiagramNode:
        """Create a hidden branch node after the first bus endpoint is chosen."""
        next_count = self.component_counters.get(component_name, 0) + 1
        self.component_counters[component_name] = next_count
        node_id = f"{component_id_prefix(component_name)}_{next_count}"
        node = make_diagram_node(
            component_name=component_name,
            node_id=node_id,
            x=0,
            y=0,
        )
        if "name" in node["attrs"] and not node["attrs"].get("name"):
            node["attrs"]["name"] = node_id
        node["attrs"]["bus0"] = bus0_name
        component = NETWORK_MODEL.component(component_name)
        node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
        node["hidden"] = True
        return node

    def _bus_name_for_node_id(self, node_id: str) -> str:
        """Return the PyPSA bus name represented by a bus node id."""
        for node in self.diagram_nodes:
            if node["id"] == node_id and node["component"] == "buses":
                return str(node["attrs"].get("name") or node["id"])
        return ""

    def _node_position(self, node_id: str) -> dict[str, float] | None:
        """Return the current canvas position for a node id."""
        for node in self.diagram_nodes:
            if node["id"] == node_id:
                return node["position"]
        return None

    def _bus_nodes_by_name(
        self,
        nodes: list[dict[str, object]] | None = None,
    ) -> dict[str, dict[str, object]]:
        """Return bus nodes keyed by their displayed PyPSA bus name."""
        source_nodes = nodes if nodes is not None else self.diagram_nodes
        bus_nodes: dict[str, dict[str, object]] = {}
        for node in source_nodes:
            if str(node.get("component", "")) != "buses":
                continue
            attrs = node.get("attrs", {})
            bus_name = (
                str(attrs.get("name") or node.get("id", ""))
                if isinstance(attrs, dict)
                else str(node.get("id", ""))
            )
            if bus_name:
                bus_nodes[bus_name] = node
        return bus_nodes

    def _bus_side_for_node_position(
        self,
        node: dict[str, object],
        bus_node: dict[str, object],
    ) -> str:
        """Return the side of a bus occupied by a component node."""
        node_position = node.get("position", {})
        bus_position = bus_node.get("position", {})
        if not isinstance(node_position, dict) or not isinstance(bus_position, dict):
            return ""
        try:
            return (
                "left"
                if float(node_position.get("x", 0)) < float(bus_position.get("x", 0))
                else "right"
            )
        except TypeError, ValueError:
            return ""

    def _refresh_bus_side_layout(self) -> None:
        """Refresh bus-side layout metadata from current component positions."""
        bus_nodes_by_name = self._bus_nodes_by_name()
        changed = False
        for node in self.diagram_nodes:
            attrs = node.get("attrs", {})
            if node["component"] == "buses" or not isinstance(attrs, dict):
                continue
            bus_name = str(attrs.get("bus", ""))
            bus_node = bus_nodes_by_name.get(bus_name)
            if bus_node is None:
                continue
            bus_side = self._bus_side_for_node_position(node, bus_node)
            if not bus_side:
                continue
            layout = node.setdefault("layout", {})
            if layout.get("bus_side") != bus_side:
                layout["bus_side"] = bus_side
                changed = True
        if changed:
            self._sync_diagram_model()

    def _apply_bus_side_constraints_to_router_network(
        self,
        routed_network: RouterNetwork,
    ) -> None:
        """Keep bus-attached components on their saved side after routing."""
        routed_nodes = routed_network.get("nodes", [])
        if not isinstance(routed_nodes, list):
            return

        current_by_id = {str(node["id"]): node for node in self.diagram_nodes}
        routed_by_id = {
            str(node.get("id", "")): node
            for node in routed_nodes
            if isinstance(node, dict) and node.get("id")
        }
        routed_bus_nodes_by_name = self._bus_nodes_by_name(routed_nodes)

        for node_id, routed_node in routed_by_id.items():
            current_node = current_by_id.get(node_id)
            if current_node is None:
                continue
            attrs = routed_node.get("attrs")
            if not isinstance(attrs, dict):
                attrs = current_node.get("attrs", {})
            if not isinstance(attrs, dict):
                continue

            bus_name = str(attrs.get("bus", ""))
            bus_node = routed_bus_nodes_by_name.get(bus_name)
            if bus_node is None:
                continue

            layout = current_node.get("layout", {})
            bus_side = (
                normalize_bus_side(layout.get("bus_side"))
                if isinstance(layout, dict)
                else ""
            )
            if not bus_side:
                current_bus_node = self._bus_nodes_by_name().get(bus_name)
                if current_bus_node is not None:
                    bus_side = self._bus_side_for_node_position(
                        current_node,
                        current_bus_node,
                    )
            if not bus_side:
                continue

            position = routed_node.get("position", {})
            bus_position = bus_node.get("position", {})
            if not isinstance(position, dict) or not isinstance(bus_position, dict):
                continue
            try:
                x = float(position.get("x", 0))
                bus_x = float(bus_position.get("x", 0))
            except TypeError, ValueError:
                continue

            if bus_side == "left" and x >= bus_x:
                position["x"] = bus_x - BUS_COMPONENT_HORIZONTAL_OFFSET
            elif bus_side == "right" and x <= bus_x:
                position["x"] = bus_x + BUS_COMPONENT_HORIZONTAL_OFFSET

    def _reference_options_for_attr(self, attr_name: str) -> list[str]:
        """Return available row names for a global reference attribute."""
        table_component = REFERENCE_ATTR_TABLES.get(str(attr_name))
        if not table_component:
            return []
        table = self.other_csv_tables.get(table_component)
        if table is None:
            return []
        return [str(row["id"]) for row in table["rows"] if str(row["id"]).strip()]

    def _ensure_reference_table(self, attr_name: str) -> OtherCsvTable | None:
        """Return the backing supplemental CSV table for a reference attr."""
        table_component = REFERENCE_ATTR_TABLES.get(str(attr_name))
        if not table_component:
            return None
        table = self.other_csv_tables.get(table_component)
        if table is None:
            table = empty_other_csv_table(table_component)
            self.other_csv_tables[table_component] = table
        return table

    def _ensure_reference_row(self, attr_name: str, value: object) -> bool:
        """Create a global reference row if it does not already exist."""
        row_id = str(value or "").strip()
        if not row_id:
            return False
        table = self._ensure_reference_table(attr_name)
        if table is None:
            return False
        if any(str(row["id"]).strip() == row_id for row in table["rows"]):
            return False
        next_index = max((row["row_index"] for row in table["rows"]), default=-1) + 1
        table["rows"].append(
            {
                "row_index": next_index,
                "id": row_id,
                "cells": [
                    {"row_index": next_index, "column": column, "value": ""}
                    for column in table["columns"]
                ],
            }
        )
        table["loaded"] = True
        table["dirty"] = True
        self._mark_network_dirty()
        self.other_table_error = ""
        self._sync_other_table_dialog()
        return True

    def _refresh_selected_attr_rows(self) -> None:
        """Refresh selected attr rows after reference option changes."""
        if not self.selected_node_id:
            return
        for node in self.diagram_nodes:
            if node["id"] == self.selected_node_id:
                self.selected_attr_rows = self._selected_attr_rows_for_node(node)
                return

    def commit_selected_attr_reference(
        self,
        attr_name: str,
        value: object = "",
    ) -> None:
        """Promote a selected reference attr value into its global CSV table."""
        attr_name = str(attr_name)
        candidate = value
        if str(candidate or "").strip() == "":
            for node in self.diagram_nodes:
                if node["id"] == self.selected_node_id:
                    candidate = node["attrs"].get(attr_name, "")
                    break
        if self._ensure_reference_row(attr_name, candidate):
            self._refresh_selected_attr_rows()

    def _ensure_diagram_reference_rows(self) -> None:
        """Ensure used reference attr values exist in their global CSV tables."""
        changed = False
        for node in self.diagram_nodes:
            attrs = node.get("attrs", {})
            if not isinstance(attrs, dict):
                continue
            for attr_name in REFERENCE_ATTR_TABLES:
                if self._ensure_reference_row(attr_name, attrs.get(attr_name, "")):
                    changed = True
        if changed:
            self._refresh_selected_attr_rows()

    def _selected_attr_rows_for_node(self, node: DiagramNode) -> list[DiagramAttr]:
        """Return selected-node attr rows with time-series affordance flags."""
        component_name = str(node["component"])
        attrs = node.get("attrs", {})
        pypsa_name = (
            str(attrs.get("name") or node["id"])
            if isinstance(attrs, dict)
            else node["id"]
        )
        time_series_components = {
            "buses",
            "loads",
            "generators",
            "stores",
            "storage_units",
        }
        return [
            {
                **row,
                "options": (
                    self._reference_options_for_attr(str(row["name"]))
                    if str(row["name"]) in REFERENCE_ATTR_TABLES
                    else row["options"]
                ),
                "has_time_series_table": bool(
                    row["is_time_series"] and component_name in time_series_components
                ),
                "has_time_series_value": self._has_time_series_value(
                    component_name,
                    str(row["name"]),
                    pypsa_name,
                ),
            }
            for row in node["attr_rows"]
        ]

    def select_node(self, node_id: str) -> None:
        """Select a visible or hidden diagram node for editing."""
        self.selected_node_id = node_id
        for node in self.diagram_nodes:
            if node["id"] == node_id:
                self.show_right_sidebar = True
                self.selected_component_name = str(node["pypsa_name"])
                self.selected_attr_rows = self._selected_attr_rows_for_node(node)
                return
        self.selected_component_name = ""
        self.selected_attr_rows = []

    def is_node_layout_locked(self, node: DiagramNode) -> bool:
        """Return whether a diagram node is locked to its current position."""
        layout = node.get("layout", {})
        return bool(isinstance(layout, dict) and layout.get("locked"))

    def set_node_layout_locked(self, node_id: str, locked: bool) -> None:
        """Set whether a diagram node is locked to its current position."""
        target_node_id = str(node_id)
        for node in self.diagram_nodes:
            if node["id"] != target_node_id:
                continue
            if node.get("hidden"):
                return
            is_locked = self.is_node_layout_locked(node)
            next_locked = bool(locked)
            if is_locked == next_locked:
                return

            self._push_canvas_history()
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            if next_locked:
                layout["locked"] = True
            else:
                layout.pop("locked", None)
            self._sync_diagram_model()
            if self.selected_node_id == target_node_id:
                self.select_node(target_node_id)
            return

    def toggle_node_layout_locked(self, node_id: str) -> None:
        """Toggle whether a diagram node is locked to its current position."""
        target_node_id = str(node_id)
        for node in self.diagram_nodes:
            if node["id"] == target_node_id:
                self.set_node_layout_locked(
                    target_node_id,
                    not self.is_node_layout_locked(node),
                )
                return

    def lock_all_canvas_components(self) -> None:
        """Lock every visible canvas component at its current position."""
        lockable_nodes = [
            node
            for node in self.diagram_nodes
            if not node.get("hidden") and is_canvas_visible(node)
        ]
        if not any(not self.is_node_layout_locked(node) for node in lockable_nodes):
            return

        self._push_canvas_history()
        for node in lockable_nodes:
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            layout["locked"] = True
        self._sync_diagram_model()
        if self.selected_node_id:
            self.select_node(self.selected_node_id)

    def unlock_all_canvas_components(self) -> None:
        """Unlock every visible canvas component with a locked position."""
        locked_nodes = [
            node
            for node in self.diagram_nodes
            if not node.get("hidden")
            and is_canvas_visible(node)
            and self.is_node_layout_locked(node)
        ]
        if not locked_nodes:
            return

        self._push_canvas_history()
        for node in locked_nodes:
            layout = node.get("layout", {})
            if isinstance(layout, dict):
                layout.pop("locked", None)
        self._sync_diagram_model()
        if self.selected_node_id:
            self.select_node(self.selected_node_id)

    def set_node_canvas_visible(self, node_id: str, visible: bool) -> None:
        """Set whether a diagram node should be visibly rendered on the canvas."""
        target_node_id = str(node_id)
        for node in self.diagram_nodes:
            if node["id"] != target_node_id:
                continue
            next_visible = bool(visible)
            if is_canvas_visible(node) == next_visible:
                return

            self._push_canvas_history()
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            if next_visible:
                layout.pop("visible", None)
            else:
                layout["visible"] = False
            if self.selected_node_id == target_node_id and not next_visible:
                self.selected_node_id = ""
                self.selected_component_name = ""
                self.selected_attr_rows = []
            self._sync_diagram_model()
            return

    def hide_canvas_selection(self, node_ids: list[object]) -> None:
        """Hide all selected canvas diagram nodes in one undoable operation."""
        selected_node_ids = {
            str(node_id) for node_id in node_ids if str(node_id).strip()
        }
        if not selected_node_ids:
            self.rectangle_selection_armed = False
            return
        matching_nodes = [
            node for node in self.diagram_nodes if node["id"] in selected_node_ids
        ]
        if not matching_nodes:
            self.rectangle_selection_armed = False
            return
        if not any(is_canvas_visible(node) for node in matching_nodes):
            self.rectangle_selection_armed = False
            return

        self._push_canvas_history()
        for node in matching_nodes:
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            layout["visible"] = False
        if self.selected_node_id in selected_node_ids:
            self.selected_node_id = ""
            self.selected_component_name = ""
            self.selected_attr_rows = []
        self.rectangle_selection_armed = False
        self._sync_diagram_model()

    def lock_canvas_selection(self, node_ids: list[object]) -> None:
        """Lock visible selected canvas nodes in one undoable operation."""
        selected_node_ids = {
            str(node_id) for node_id in node_ids if str(node_id).strip()
        }
        if not selected_node_ids:
            self.rectangle_selection_armed = False
            return
        lockable_nodes = [
            node
            for node in self.diagram_nodes
            if node["id"] in selected_node_ids
            and not node.get("hidden")
            and is_canvas_visible(node)
        ]
        if not any(not self.is_node_layout_locked(node) for node in lockable_nodes):
            self.rectangle_selection_armed = False
            return

        self._push_canvas_history()
        for node in lockable_nodes:
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            layout["locked"] = True
        self.rectangle_selection_armed = False
        self._sync_diagram_model()
        if self.selected_node_id:
            self.select_node(self.selected_node_id)

    def set_mark_region_name(self, value: str) -> None:
        """Set the pending marked region display name."""
        self.mark_region_name = str(value)

    def set_mark_region_dialog_open(self, value: bool) -> None:
        """Set whether the mark region naming dialog is open."""
        self.is_mark_region_dialog_open = bool(value)
        if not value:
            self.mark_region_name = ""
            self.pending_region_bounds = {}
            self.pending_region_node_ids = []

    def _coerce_region_bounds(
        self, bounds: dict[str, object]
    ) -> dict[str, float] | None:
        """Return normalized positive region bounds, or None when invalid."""
        try:
            x = float(bounds.get("x", 0))
            y = float(bounds.get("y", 0))
            width = float(bounds.get("width", 0))
            height = float(bounds.get("height", 0))
        except TypeError, ValueError:
            return None
        if width <= 0 or height <= 0:
            return None
        return {"x": x, "y": y, "width": width, "height": height}

    def open_mark_region_dialog(
        self, node_ids: list[object], bounds: dict[str, object]
    ) -> None:
        """Open the mark region dialog for a rectangle selection."""
        region_bounds = self._coerce_region_bounds(bounds)
        if region_bounds is None:
            self.rectangle_selection_armed = False
            return
        self.pending_region_node_ids = [
            str(node_id) for node_id in node_ids if str(node_id).strip()
        ]
        self.pending_region_bounds = region_bounds
        self.mark_region_name = ""
        self.is_mark_region_dialog_open = True
        self.rectangle_selection_armed = False

    def _next_canvas_region_id(self) -> str:
        """Return the next unique marked region id."""
        existing_ids = {str(region.get("id", "")) for region in self.canvas_regions}
        index = len(existing_ids) + 1
        region_id = f"region-{index}"
        while region_id in existing_ids:
            index += 1
            region_id = f"region-{index}"
        return region_id

    def confirm_mark_region(self) -> None:
        """Lock the pending selected nodes and add a saved marked region."""
        bounds = self._coerce_region_bounds(self.pending_region_bounds)
        if bounds is None:
            self.set_mark_region_dialog_open(False)
            return

        selected_node_ids = set(self.pending_region_node_ids)
        name = self.mark_region_name.strip() or f"Region {len(self.canvas_regions) + 1}"
        self._push_canvas_history()
        for node in self.diagram_nodes:
            if node["id"] not in selected_node_ids:
                continue
            if node.get("hidden") or not is_canvas_visible(node):
                continue
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            layout["locked"] = True
        self.canvas_regions.append(
            {
                "id": self._next_canvas_region_id(),
                "name": name,
                "x": bounds["x"],
                "y": bounds["y"],
                "width": bounds["width"],
                "height": bounds["height"],
                "color": DEFAULT_CANVAS_REGION_COLOR,
                "summary": False,
                "summary_node_ids": [],
            }
        )
        self.is_mark_region_dialog_open = False
        self.mark_region_name = ""
        self.pending_region_bounds = {}
        self.pending_region_node_ids = []
        self._sync_diagram_model()
        if self.selected_node_id:
            self.select_node(self.selected_node_id)

    def rename_canvas_region(self, region_id: str, name: str) -> None:
        """Rename a marked canvas region by id."""
        target_id = str(region_id)
        next_name = str(name).strip()
        if not target_id or not next_name:
            return
        for region in self.canvas_regions:
            if region["id"] != target_id:
                continue
            if str(region.get("name", "")) == next_name:
                return
            self._push_canvas_history()
            region["name"] = next_name
            self._sync_diagram_model()
            return

    def set_canvas_region_color(self, region_id: str, color: object) -> None:
        """Set the display color for a marked canvas region."""
        target_id = str(region_id)
        next_color = normalize_canvas_region_color(color)
        if not target_id:
            return
        for region in self.canvas_regions:
            if region["id"] != target_id:
                continue
            if normalize_canvas_region_color(region.get("color")) == next_color:
                return
            self._push_canvas_history()
            region["color"] = next_color
            self._sync_diagram_model()
            return

    def _canvas_node_rect(self, node: DiagramNode) -> dict[str, float] | None:
        """Return approximate flow-space bounds for a visible canvas node."""
        if node.get("hidden") or not is_canvas_visible(node):
            return None
        position = node.get("position", {})
        if not isinstance(position, dict):
            return None
        try:
            x = float(position.get("x", 0))
            y = float(position.get("y", 0))
        except TypeError, ValueError:
            return None
        width, height = CANVAS_REGION_NODE_SIZES.get(
            str(node.get("component", "")).lower(),
            (56.0, 76.0),
        )
        return {"x": x, "y": y, "right": x + width, "bottom": y + height}

    def _region_intersects_node(
        self,
        bounds: dict[str, float],
        node: DiagramNode,
    ) -> bool:
        """Return whether region bounds intersect a visible canvas node."""
        node_rect = self._canvas_node_rect(node)
        if node_rect is None:
            return False
        region_rect = {
            "x": bounds["x"],
            "y": bounds["y"],
            "right": bounds["x"] + bounds["width"],
            "bottom": bounds["y"] + bounds["height"],
        }
        return not (
            node_rect["right"] < region_rect["x"]
            or node_rect["x"] > region_rect["right"]
            or node_rect["bottom"] < region_rect["y"]
            or node_rect["y"] > region_rect["bottom"]
        )

    def node_ids_intersecting_region(
        self,
        bounds: dict[str, float],
    ) -> set[str]:
        """Return ids for visible nodes intersecting a region."""
        return {
            str(node["id"])
            for node in self.diagram_nodes
            if self._region_intersects_node(bounds, node)
        }

    def summarized_region_node_ids(self) -> set[str]:
        """Return node ids hidden by any active summary region."""
        node_ids: set[str] = set()
        for region in self.canvas_regions:
            if not bool(region.get("summary", False)):
                continue
            node_ids.update(
                str(node_id)
                for node_id in region.get("summary_node_ids", [])
                if str(node_id).strip()
            )
        return node_ids

    def summarize_canvas_region(self, region_id: str) -> None:
        """Hide visible nodes inside a region and mark it as a summary."""
        target_id = str(region_id)
        target_region = next(
            (region for region in self.canvas_regions if region["id"] == target_id),
            None,
        )
        if target_region is None:
            return
        bounds = self._coerce_region_bounds(target_region)
        if bounds is None:
            return
        node_ids = self.node_ids_intersecting_region(bounds)
        if not node_ids:
            return

        changed = not bool(target_region.get("summary", False))
        existing_summary_ids = {
            str(node_id)
            for node_id in target_region.get("summary_node_ids", [])
            if str(node_id).strip()
        }
        if existing_summary_ids != node_ids:
            changed = True
        for node in self.diagram_nodes:
            if node["id"] not in node_ids:
                continue
            if is_canvas_visible(node):
                changed = True
                break
        if not changed:
            return

        self._push_canvas_history()
        for node in self.diagram_nodes:
            if node["id"] not in node_ids:
                continue
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            layout["visible"] = False
        target_region["summary"] = True
        target_region["summary_node_ids"] = sorted(node_ids)
        if self.selected_node_id in node_ids:
            self.selected_node_id = ""
            self.selected_component_name = ""
            self.selected_attr_rows = []
        self._sync_diagram_model()

    def unhide_canvas_region_summary(self, region_id: str) -> None:
        """Unhide nodes hidden by a specific summary region."""
        target_id = str(region_id)
        target_region = next(
            (region for region in self.canvas_regions if region["id"] == target_id),
            None,
        )
        if target_region is None:
            return
        node_ids = {
            str(node_id)
            for node_id in target_region.get("summary_node_ids", [])
            if str(node_id).strip()
        }
        changed = bool(target_region.get("summary", False)) or bool(node_ids)
        nodes_by_id = {str(node["id"]): node for node in self.diagram_nodes}
        for node_id in node_ids:
            node = nodes_by_id.get(node_id)
            layout = node.get("layout", {}) if node is not None else {}
            if isinstance(layout, dict) and layout.get("visible") is False:
                changed = True
                break
        if not changed:
            return

        self._push_canvas_history()
        for node_id in node_ids:
            node = nodes_by_id.get(node_id)
            if node is None:
                continue
            layout = node.get("layout", {})
            if isinstance(layout, dict):
                layout.pop("visible", None)
        target_region["summary"] = False
        target_region["summary_node_ids"] = []
        self._sync_diagram_model()

    def move_canvas_region(
        self,
        region_id: str,
        bounds: dict[str, object],
        node_updates: list[object],
        lock_node_ids: list[object],
    ) -> None:
        """Move a region and optionally move or lock intersecting nodes."""
        target_id = str(region_id)
        region_bounds = self._coerce_region_bounds(bounds)
        if not target_id or region_bounds is None:
            return
        target_region = next(
            (region for region in self.canvas_regions if region["id"] == target_id),
            None,
        )
        if target_region is None:
            return

        parsed_positions: dict[str, dict[str, float]] = {}
        for update in node_updates:
            if not isinstance(update, dict) or "id" not in update:
                continue
            position = update.get("position", {})
            if not isinstance(position, dict):
                continue
            try:
                parsed_positions[str(update["id"])] = {
                    "x": float(position.get("x", 0)),
                    "y": float(position.get("y", 0)),
                }
            except TypeError, ValueError:
                continue

        final_lock_ids = {
            str(node_id) for node_id in lock_node_ids if str(node_id).strip()
        }
        final_lock_ids.update(self.node_ids_intersecting_region(region_bounds))
        changed = any(
            float(target_region[key]) != region_bounds[key]
            for key in ("x", "y", "width", "height")
        )

        nodes_by_id = {str(node["id"]): node for node in self.diagram_nodes}
        for node_id, position in parsed_positions.items():
            node = nodes_by_id.get(node_id)
            if node is None or node.get("hidden") or not is_canvas_visible(node):
                continue
            if node["position"] != position:
                changed = True

        for node_id in final_lock_ids:
            node = nodes_by_id.get(node_id)
            if node is None or node.get("hidden") or not is_canvas_visible(node):
                continue
            if not self.is_node_layout_locked(node):
                changed = True

        if not changed:
            return

        self._push_canvas_history()
        target_region.update(region_bounds)
        for node_id, position in parsed_positions.items():
            node = nodes_by_id.get(node_id)
            if node is None or node.get("hidden") or not is_canvas_visible(node):
                continue
            node["position"] = position
        for node_id in final_lock_ids:
            node = nodes_by_id.get(node_id)
            if node is None or node.get("hidden") or not is_canvas_visible(node):
                continue
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            layout["locked"] = True
        self._sync_diagram_model()
        if self.selected_node_id:
            self.select_node(self.selected_node_id)

    def delete_canvas_region(self, region_id: str) -> None:
        """Delete a marked canvas region by id."""
        target_id = str(region_id)
        if not target_id:
            return
        if not any(region["id"] == target_id for region in self.canvas_regions):
            return
        self._push_canvas_history()
        self.canvas_regions = [
            region for region in self.canvas_regions if region["id"] != target_id
        ]
        self._sync_diagram_model()

    def _carrier_table_values(self) -> list[str]:
        """Return carrier names from the editable carriers table."""
        table = self._ensure_network_data_table("carriers")
        carriers: list[str] = []
        seen: set[str] = set()
        for row in table["rows"]:
            carrier = str(row.get("id", "")).strip()
            if not carrier or carrier in seen:
                continue
            carriers.append(carrier)
            seen.add(carrier)
        return carriers

    def _component_count_for_carrier(self, carrier: str) -> int:
        """Return the number of diagram nodes with the given carrier value."""
        carrier_value = str(carrier)
        return sum(
            1
            for node in self.diagram_nodes
            if str(node.get("attrs", {}).get("carrier", "")).strip() == carrier_value
        )

    def _sync_carrier_visibility_rows(self) -> None:
        """Refresh carrier visibility dialog rows from the carriers table."""
        carriers = self._carrier_table_values()
        if not self.carrier_visibility_initialized:
            self.visible_canvas_carriers = carriers
            self.carrier_visibility_initialized = True
        visible_carriers = set(self.visible_canvas_carriers)
        self.carrier_visibility_rows = [
            {
                "carrier": carrier,
                "label": carrier,
                "checked": carrier in visible_carriers,
                "component_count": self._component_count_for_carrier(carrier),
            }
            for carrier in carriers
        ]

    def open_carrier_visibility_dialog(self) -> None:
        """Open the carrier-based canvas visibility dialog."""
        carriers = self._carrier_table_values()
        if not self.carrier_visibility_initialized:
            self.visible_canvas_carriers = carriers
            self.carrier_visibility_initialized = True
        else:
            valid_carriers = set(carriers)
            self.visible_canvas_carriers = [
                carrier
                for carrier in self.visible_canvas_carriers
                if carrier in valid_carriers
            ]
        self._sync_carrier_visibility_rows()
        self.is_carrier_visibility_dialog_open = True

    def set_carrier_visibility_dialog_open(self, value: bool) -> None:
        """Set whether the carrier visibility dialog is open."""
        self.is_carrier_visibility_dialog_open = bool(value)
        if value:
            self._sync_carrier_visibility_rows()

    def _set_nodes_with_carrier_visible(self, carrier: str, visible: bool) -> bool:
        """Set visibility for all nodes with a carrier and return whether any changed."""
        changed = False
        carrier_value = str(carrier)
        for node in self.diagram_nodes:
            attrs = node.get("attrs", {})
            if str(attrs.get("carrier", "")).strip() != carrier_value:
                continue
            layout = node.setdefault("layout", {})
            if not isinstance(layout, dict):
                layout = {}
                node["layout"] = layout
            if visible:
                if layout.get("visible") is False:
                    layout.pop("visible", None)
                    changed = True
            elif layout.get("visible") is not False:
                layout["visible"] = False
                changed = True
        return changed

    def _has_nodes_with_carrier_visibility_change(
        self, carrier: str, visible: bool
    ) -> bool:
        """Return whether setting carrier visibility would change any node."""
        carrier_value = str(carrier)
        for node in self.diagram_nodes:
            attrs = node.get("attrs", {})
            if str(attrs.get("carrier", "")).strip() != carrier_value:
                continue
            if is_canvas_visible(node) != bool(visible):
                return True
        return False

    async def set_canvas_carrier_visible(self, carrier: str, checked: bool):
        """Live-toggle canvas visibility for all components using a carrier."""
        carrier_value = str(carrier)
        next_checked = bool(checked)
        if not self.carrier_visibility_initialized:
            self.visible_canvas_carriers = self._carrier_table_values()
            self.carrier_visibility_initialized = True
        current = set(self.visible_canvas_carriers)
        if next_checked:
            current.add(carrier_value)
        else:
            current.discard(carrier_value)
        self.visible_canvas_carriers = [
            value for value in self._carrier_table_values() if value in current
        ]
        self._sync_carrier_visibility_rows()
        yield

        if self._has_nodes_with_carrier_visibility_change(carrier_value, next_checked):
            self._push_canvas_history()
            self._set_nodes_with_carrier_visible(carrier_value, next_checked)
            if self.selected_node_id:
                selected_node = next(
                    (
                        node
                        for node in self.diagram_nodes
                        if node["id"] == self.selected_node_id
                    ),
                    None,
                )
                if selected_node is not None and not is_canvas_visible(selected_node):
                    self.selected_node_id = ""
                    self.selected_component_name = ""
                    self.selected_attr_rows = []
            self._sync_diagram_model()
            self._sync_carrier_visibility_rows()
            yield

    def unhide_all_canvas_components(self) -> None:
        """Clear canvas visibility overrides from all diagram nodes."""
        changed = False
        for node in self.diagram_nodes:
            layout = node.get("layout", {})
            if isinstance(layout, dict) and layout.get("visible") is False:
                changed = True
                break
        if not changed:
            self.visible_canvas_carriers = self._carrier_table_values()
            self.carrier_visibility_initialized = True
            self._sync_carrier_visibility_rows()
            return

        self._push_canvas_history()
        for node in self.diagram_nodes:
            layout = node.get("layout", {})
            if isinstance(layout, dict):
                layout.pop("visible", None)
        self.visible_canvas_carriers = self._carrier_table_values()
        self.carrier_visibility_initialized = True
        self._sync_diagram_model()
        self._sync_carrier_visibility_rows()

    def handle_canvas_context_menu_action(self, payload: dict[str, object]) -> None:
        """Dispatch a selected canvas context-menu action."""
        action_id = str(payload.get("action_id", ""))
        target_kind = str(payload.get("target_kind", ""))
        node_id = str(payload.get("node_id", ""))
        if action_id not in {
            "select",
            "delete",
            "toggle_lock",
            "hide",
            "lock_selection",
            "mark_regions",
            "finish_rectangle_selection",
            "rename_region",
            "set_region_color",
            "move_region",
            "hide_region_summary",
            "unhide_region_summary",
        }:
            return
        if target_kind not in {"component", "branch", "selection", "region"}:
            return
        if action_id == "finish_rectangle_selection":
            self.rectangle_selection_armed = False
            return
        if target_kind == "region":
            if action_id == "delete":
                self.delete_canvas_region(str(payload.get("region_id", "")))
            if action_id == "rename_region":
                self.rename_canvas_region(
                    str(payload.get("region_id", "")),
                    str(payload.get("region_name", "")),
                )
            if action_id == "set_region_color":
                self.set_canvas_region_color(
                    str(payload.get("region_id", "")),
                    payload.get("region_color", ""),
                )
            if action_id == "move_region":
                region_bounds = payload.get("region_bounds", {})
                node_updates = payload.get("node_updates", [])
                lock_node_ids = payload.get("lock_node_ids", [])
                if (
                    isinstance(region_bounds, dict)
                    and isinstance(node_updates, list)
                    and isinstance(lock_node_ids, list)
                ):
                    self.move_canvas_region(
                        str(payload.get("region_id", "")),
                        region_bounds,
                        node_updates,
                        lock_node_ids,
                    )
            if action_id == "hide_region_summary":
                self.summarize_canvas_region(str(payload.get("region_id", "")))
            if action_id == "unhide_region_summary":
                self.unhide_canvas_region_summary(str(payload.get("region_id", "")))
            return
        if target_kind == "selection":
            node_ids = payload.get("node_ids", [])
            region_bounds = payload.get("region_bounds", {})
            if action_id == "hide" and isinstance(node_ids, list):
                self.hide_canvas_selection(node_ids)
            if action_id == "lock_selection" and isinstance(node_ids, list):
                self.lock_canvas_selection(node_ids)
            if (
                action_id == "mark_regions"
                and isinstance(node_ids, list)
                and isinstance(region_bounds, dict)
            ):
                self.open_mark_region_dialog(node_ids, region_bounds)
            return
        if not any(node["id"] == node_id for node in self.diagram_nodes):
            return

        if action_id == "select":
            self.select_node(node_id)
            return

        if action_id == "delete":
            self.delete_node_by_id(node_id)
            return

        if action_id == "toggle_lock" and target_kind == "component":
            self.toggle_node_layout_locked(node_id)
            return

        if action_id == "hide":
            self.set_node_canvas_visible(node_id, False)

    def delete_selected_node(self) -> None:
        """Delete the selected component and rebuild derived canvas data."""
        self.delete_node_by_id(str(self.selected_node_id))

    def delete_node_by_id(self, node_id: str) -> None:
        """Delete a diagram node by id and rebuild derived canvas data."""
        selected_node_id = str(node_id)
        if not selected_node_id:
            return

        selected_node = next(
            (node for node in self.diagram_nodes if node["id"] == selected_node_id),
            None,
        )
        if selected_node is None:
            self.selected_node_id = ""
            self.selected_component_name = ""
            self.selected_attr_rows = []
            return

        self._push_canvas_history()
        selected_component = str(selected_node["component"])
        selected_attrs = selected_node.get("attrs", {})
        selected_bus_name = (
            str(selected_attrs.get("name") or selected_node_id)
            if selected_component == "buses" and isinstance(selected_attrs, dict)
            else ""
        )

        remaining_nodes: list[DiagramNode] = []
        for node in self.diagram_nodes:
            if node["id"] == selected_node_id:
                continue
            attrs = node.get("attrs", {})
            if (
                selected_bus_name
                and node["component"] in NETWORK_MODEL.branch_components
                and isinstance(attrs, dict)
                and (
                    str(attrs.get("bus0", "")) == selected_bus_name
                    or str(attrs.get("bus1", "")) == selected_bus_name
                )
            ):
                continue
            if (
                selected_bus_name
                and isinstance(attrs, dict)
                and str(attrs.get("bus", "")) == selected_bus_name
            ):
                attrs["bus"] = ""
                component = NETWORK_MODEL.component(node["component"])
                node["attr_rows"] = diagram_attr_rows(component, attrs)
            remaining_nodes.append(node)

        self.diagram_nodes = remaining_nodes
        self.selected_node_id = ""
        self.selected_component_name = ""
        self.selected_attr_rows = []
        if self.pending_branch_node_id == selected_node_id:
            self.pending_branch_node_id = ""
            self.branch_bus0_node_id = ""
        if self.branch_bus0_node_id == selected_node_id:
            self.branch_bus0_node_id = ""
        if self.pending_branch_node_id and not any(
            node["id"] == self.pending_branch_node_id for node in self.diagram_nodes
        ):
            self.pending_branch_node_id = ""
            self.branch_bus0_node_id = ""
        self._sync_diagram_model()

    async def open_selected_time_series_attr(self, attr_name: str):
        """Open the selected component column for a time-series attribute."""
        if not self.selected_node_id:
            return
        for node in self.diagram_nodes:
            if node["id"] != self.selected_node_id:
                continue
            component_name = str(node["component"])
            pypsa_name = str(node["attrs"].get("name") or node["id"])
            self.is_operation_dialog_open = True
            self.operation_title = "Loading time series"
            self.operation_status = f"Opening {component_name}.{attr_name}..."
            self.operation_kind = "load"
            self.operation_is_error = False
            self.operation_retry_load = False
            yield

            self._open_time_series_table(component_name, str(attr_name), pypsa_name)
            self.is_operation_dialog_open = False
            self.operation_title = ""
            self.operation_status = ""
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            yield
            return

    def update_node_positions(self, updates: list[dict[str, object]]) -> None:
        """Persist dragged node positions and optional bus-drop connections."""
        original_snapshot = self._canvas_snapshot()
        positions = {
            str(update["id"]): update.get("position", {})
            for update in updates
            if "id" in update
        }
        layout_updates = {
            str(update["id"]): update.get("layout", {})
            for update in updates
            if "id" in update
        }
        bus_targets = {
            str(update["id"]): str(update.get("bus_node_id", ""))
            for update in updates
            if "id" in update and update.get("bus_node_id")
        }
        changed = False
        for node in self.diagram_nodes:
            position = positions.get(node["id"])
            if isinstance(position, dict):
                new_position = {
                    "x": float(position.get("x", node["position"]["x"])),
                    "y": float(position.get("y", node["position"]["y"])),
                }
                if new_position != node["position"]:
                    changed = True
                node["position"] = {
                    "x": new_position["x"],
                    "y": new_position["y"],
                }
            layout_update = layout_updates.get(node["id"])
            if isinstance(layout_update, dict):
                bus_side = normalize_bus_side(layout_update.get("bus_side"))
                if bus_side:
                    layout = node.setdefault("layout", {})
                    if layout.get("bus_side") != bus_side:
                        layout["bus_side"] = bus_side
                        changed = True
            bus_node_id = bus_targets.get(node["id"])
            if bus_node_id and "bus" in node["attrs"] and not node["attrs"].get("bus"):
                bus_name = self._bus_name_for_node_id(bus_node_id)
                if bus_name:
                    changed = True
                    node["attrs"]["bus"] = bus_name
                    bus_position = self._node_position(bus_node_id)
                    if bus_position:
                        layout = node.setdefault("layout", {})
                        bus_side = normalize_bus_side(
                            layout.get("bus_side")
                        ) or default_bus_side_for_component(node["component"])
                        if bus_side == "left":
                            node["position"] = {
                                "x": bus_position["x"] - BUS_COMPONENT_DROP_OFFSET,
                                "y": bus_position["y"] + 8,
                            }
                            layout["bus_side"] = "left"
                        else:
                            node["position"] = {
                                "x": bus_position["x"] + BUS_COMPONENT_DROP_OFFSET,
                                "y": bus_position["y"] + 8,
                            }
                            layout["bus_side"] = "right"
                    component = NETWORK_MODEL.component(node["component"])
                    node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
                    if node["id"] == self.selected_node_id:
                        self.selected_attr_rows = self._selected_attr_rows_for_node(
                            node
                        )
        if changed and self.operation_kind != "load":
            self._mark_network_dirty()
            self.canvas_undo_stack.append(original_snapshot)
            if len(self.canvas_undo_stack) > CANVAS_HISTORY_LIMIT:
                self.canvas_undo_stack = self.canvas_undo_stack[-CANVAS_HISTORY_LIMIT:]
            self.canvas_redo_stack = []
            self._set_canvas_history_availability()
        self._sync_diagram_model()

    def update_selected_attr(self, attr_name: str, value: object) -> None:
        """Update an attribute on the currently selected diagram node."""
        if self.selected_node_id == "":
            return

        for node in self.diagram_nodes:
            if node["id"] != self.selected_node_id:
                continue

            component = NETWORK_MODEL.component(node["component"])
            attr = component.attrs[str(attr_name)]
            parsed_value = self._parse_attr_value(
                value, attr.pypsa_type, attr.python_type
            )
            if node["attrs"].get(str(attr_name)) == parsed_value:
                return
            self._push_canvas_history()
            node["attrs"][str(attr_name)] = parsed_value
            node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
            self.selected_attr_rows = self._selected_attr_rows_for_node(node)
            self._sync_diagram_model()
            return

    def _sync_diagram_model(self) -> None:
        """Rebuild derived edges, display rows, and bus-name lists."""
        for node in self.diagram_nodes:
            if node["component"] in NETWORK_MODEL.branch_components:
                node["hidden"] = True
        self._sync_diagram_edges()
        components = [
            {
                "id": node["id"],
                "component": node["component"],
                "pypsa_name": node["pypsa_name"],
                "position": node["position"],
                "layout": node.get("layout", {}),
                "attrs": node["attrs"],
                "hidden": node["hidden"],
            }
            for node in self.diagram_nodes
        ]
        connections = [
            {
                "id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "sourceHandle": edge["sourceHandle"],
                "targetHandle": edge["targetHandle"],
                "type": edge["type"],
                "label": edge["label"],
                "component": edge["component"],
                "icon_src": edge.get("icon_src", ""),
                "icon_svg": edge.get("icon_svg", ""),
                "style": edge["style"],
                "attrs": edge["attrs"],
            }
            for edge in self.diagram_edges
        ]
        self.diagram_model = {
            "components": components,
            "connections": connections,
            "regions": copy.deepcopy(self.canvas_regions),
        }
        self.network_component_rows = [
            {
                "id": str(component["id"]),
                "component": str(component["component"]),
                "pypsa_name": str(component["pypsa_name"]),
                "position_json": json.dumps(
                    component["position"], indent=2, default=str
                ),
                "attrs_json": json.dumps(component["attrs"], indent=2, default=str),
            }
            for component in components[:NETWORK_OBJECT_DISPLAY_LIMIT]
        ]
        self.network_connection_rows = [
            {
                "id": str(connection["id"]),
                "source": str(connection["source"]),
                "target": str(connection["target"]),
                "component": str(connection["component"]),
                "attrs_json": json.dumps(connection["attrs"], indent=2, default=str),
            }
            for connection in connections[:NETWORK_OBJECT_DISPLAY_LIMIT]
        ]
        self.canvas_bus_names = [
            str(node["attrs"].get("name") or node["id"])
            for node in self.diagram_nodes
            if node["component"] == "buses"
        ]
        if self._should_sync_network_data_view():
            self._sync_network_data_dialog()

    def _sync_diagram_edges(self) -> None:
        """Regenerate React Flow edge data from node bus attributes."""
        bus_ids_by_name = {
            str(node["attrs"].get("name") or node["id"]): node["id"]
            for node in self.diagram_nodes
            if node["component"] == "buses"
        }
        summarized_node_ids = self.summarized_region_node_ids()
        summary_node_sets = [
            {
                str(node_id)
                for node_id in region.get("summary_node_ids", [])
                if str(node_id).strip()
            }
            for region in self.canvas_regions
            if bool(region.get("summary", False))
        ]
        edges: list[DiagramEdge] = []

        def is_internal_summary_edge(source_id: str, target_id: str) -> bool:
            """Return whether both edge endpoints are inside one summary."""
            return any(
                source_id in summary_nodes and target_id in summary_nodes
                for summary_nodes in summary_node_sets
            )

        for node in self.diagram_nodes:
            component_name = node["component"]
            if component_name == "buses":
                continue
            if not is_canvas_visible(node) and node["id"] not in summarized_node_ids:
                continue

            attrs = node["attrs"]
            if component_name in NETWORK_MODEL.branch_components:
                bus0_id = bus_ids_by_name.get(str(attrs.get("bus0", "")))
                bus1_id = bus_ids_by_name.get(str(attrs.get("bus1", "")))
                if bus0_id and bus1_id and bus0_id != bus1_id:
                    if is_internal_summary_edge(bus0_id, bus1_id):
                        continue
                    branch_style: dict[str, object] = {
                        "strokeWidth": 3,
                    }
                    if component_name == "links":
                        branch_style["strokeWidth"] = 1.6
                        branch_style["strokeDasharray"] = "8 7"
                    edges.append(
                        {
                            "id": f"branch:{node['id']}",
                            "source": bus0_id,
                            "target": bus1_id,
                            "sourceHandle": "right-source",
                            "targetHandle": "left-target",
                            "type": "step",
                            "label": str(attrs.get("name") or node["id"]),
                            "component": component_name,
                            "icon_src": node.get("icon_src", ""),
                            "icon_svg": node.get("icon_svg", ""),
                            "style": branch_style,
                            "attrs": {
                                "component_node_id": node["id"],
                                "bus0": attrs.get("bus0"),
                                "bus1": attrs.get("bus1"),
                            },
                        }
                    )
                continue

            bus_name = attrs.get("bus")
            bus_id = bus_ids_by_name.get(str(bus_name))
            if bus_id:
                if is_internal_summary_edge(node["id"], bus_id):
                    continue
                if component_name == "generators":
                    source = node["id"]
                    target = bus_id
                    source_handle = "right-source"
                    target_handle = "left-target"
                elif component_name in {"loads", "stores", "storage_units"}:
                    source = bus_id
                    target = node["id"]
                    source_handle = "right-source"
                    target_handle = "left-target"
                else:
                    source = node["id"]
                    target = bus_id
                    source_handle = "right-source"
                    target_handle = "left-target"

                edges.append(
                    {
                        "id": f"attach:{node['id']}:{bus_id}",
                        "source": source,
                        "target": target,
                        "sourceHandle": source_handle,
                        "targetHandle": target_handle,
                        "type": "step",
                        "label": None,
                        "component": component_name,
                        "icon_src": "",
                        "icon_svg": "",
                        "style": {},
                        "attrs": {
                            "component_node_id": node["id"],
                            "bus": bus_name,
                        },
                    }
                )

        self.diagram_edges = edges

    @rx.var
    def diagram_model_json(self) -> str:
        """Return the current diagram model as formatted JSON."""
        return json.dumps(self.diagram_model, indent=2, default=str)

    def _parse_attr_value(
        self,
        value: object,
        pypsa_type: str | None,
        python_type: str | None,
    ) -> object:
        """Parse editor string values according to PyPSA type metadata."""
        type_text = f"{pypsa_type or ''} {python_type or ''}".lower()
        clean_value = clean_numeric_text(value)
        if "bool" in type_text:
            return bool(value)
        if "int" in type_text:
            try:
                return int(clean_value)
            except TypeError, ValueError:
                return value
        if "float" in type_text:
            try:
                return float(clean_value)
            except TypeError, ValueError:
                return value
        return value

    def _clean_imported_value(self, value: object) -> object:
        """Convert pandas/numpy imported values into JSON-friendly objects."""
        if value is None:
            return None
        try:
            import pandas as pd

            if pd.isna(value):
                return None
        except TypeError, ValueError:
            pass
        if hasattr(value, "item"):
            try:
                return value.item()
            except TypeError, ValueError:
                pass
        return value
