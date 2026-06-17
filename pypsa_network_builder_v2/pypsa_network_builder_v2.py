import asyncio
import copy
import io
import json
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import pandas as pd
import reflex as rx
import pypsa


from pypsa_network_builder_v2.network_model import (
    ComponentType,
    LAYOUT_FILE_NAME,
    PypsaLoadedNetwork,
    PypsaNetworkModel,
    build_network_model,
    export_diagram_to_csv_folder,
    load_pypsa_loaded_network,
    load_pypsa_network,
    pypsa_network_to_loaded_network,
    save_upload,
    save_uploads_as_csv_folder,
)
from pypsa_network_builder_v2.components import react_flow_canvas
from pypsa_network_builder_v2.routers import (
    RouterNetwork,
    discover_python_routers,
    router_options,
)

NETWORK_MODEL = build_network_model()
JS_ELK_ROUTER_NAME = "js-elk"
PYTHON_ROUTERS = discover_python_routers()
ROUTER_OPTIONS = [
    {
        "name": JS_ELK_ROUTER_NAME,
        "label": "ELK orthogonal",
        "description": "Browser-side ELK layered orthogonal layout.",
    },
    *router_options(PYTHON_ROUTERS),
]
UPLOAD_ID = "pypsa-network-upload"
FOLDER_UPLOAD_ID = "pypsa-network-folder-upload"
BUILDER_LOAD_UPLOAD_ID = "pypsa-builder-load-upload"
BUILDER_LOAD_FOLDER_UPLOAD_ID = "pypsa-builder-load-folder-upload"
EDITABLE_CSV_UPLOAD_ID = "editable-csv-upload"
NETWORK_OBJECT_DISPLAY_LIMIT = 100
CANVAS_HISTORY_LIMIT = 100
REFERENCE_ATTR_TABLES = {
    "carrier": "carriers",
    "sub_network": "sub_networks",
}
OTHER_TABLE_COMPONENTS = {
    "carriers": "carriers.csv",
    "shapes": "shapes.csv",
    "sub_networks": "sub_networks.csv",
}
SNAPSHOT_TABLE_COMPONENTS = {
    "snapshots": "snapshots.csv",
    "investment_periods": "investment_periods.csv",
}
CSV_TABLE_COMPONENTS = {
    **OTHER_TABLE_COMPONENTS,
    **SNAPSHOT_TABLE_COMPONENTS,
}
SNAPSHOT_TABLE_COLUMNS = {
    "snapshots": ["period", "timestep", "objective", "stores", "generators"],
    "investment_periods": ["objective", "years"],
}
SNAPSHOT_TABLE_INDEX_NAMES = {
    "snapshots": "",
    "investment_periods": "period",
}
APP_STATE_DIR = Path(".states")
APP_SETTINGS_FILE = APP_STATE_DIR / "pypsa_network_builder_settings.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPSA_EXAMPLES_DIR = PROJECT_ROOT / "test_networks" / "pypsa_examples"
JUPYTER_ROOT_DIR = PROJECT_ROOT / ".jupyter"
JUPYTER_NOTEBOOKS_DIR = JUPYTER_ROOT_DIR / "notebooks"
JUPYTER_RUNTIME_DIR = JUPYTER_ROOT_DIR / "runtime"
JUPYTER_START_TIMEOUT_SECONDS = 30
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
    deadline = time.monotonic() + JUPYTER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _JUPYTER_PROCESS.stdout is None:
            break
        readable, _, _ = select.select([_JUPYTER_PROCESS.stdout], [], [], 0.2)
        line = _JUPYTER_PROCESS.stdout.readline() if readable else ""
        if line:
            output.append(line)
            url = _extract_jupyter_url(line)
            if url:
                _JUPYTER_BASE_URL = url
                _start_jupyter_output_drain(_JUPYTER_PROCESS)
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


def discover_pypsa_example_networks() -> list[ExampleNetworkGroup]:
    """Return bundled PyPSA example .nc files grouped by top-level directory."""
    if not PYPSA_EXAMPLES_DIR.exists():
        return []
    groups: list[ExampleNetworkGroup] = []
    for directory in sorted(PYPSA_EXAMPLES_DIR.iterdir()):
        if not directory.is_dir():
            continue
        networks = [
            {
                "label": path.relative_to(directory).as_posix(),
                "path": str(path),
            }
            for path in sorted(directory.rglob("*.nc"))
        ]
        if networks:
            groups.append({"label": directory.name, "networks": networks})
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


class AttrRow(TypedDict):
    name: str
    label: str
    is_time_series: bool


class ComponentRow(TypedDict):
    component: str
    pypsa_name: str
    icon_src: str
    icon_svg: str
    attrs: list[AttrRow]
    default_attr: str


class DiagramAttr(TypedDict):
    name: str
    value: object
    type: str
    input_type: str
    is_time_series: bool
    has_time_series_table: bool
    is_bus_reference: bool
    options: list[str]


class DiagramNode(TypedDict):
    id: str
    component: str
    pypsa_name: str
    icon_src: str
    icon_svg: str
    position: dict[str, float]
    attrs: dict[str, object]
    attr_rows: list[DiagramAttr]
    hidden: bool


class DiagramEdge(TypedDict):
    id: str
    source: str
    target: str
    sourceHandle: str | None
    targetHandle: str | None
    type: str
    label: str | None
    component: str | None
    style: dict[str, object]
    attrs: dict[str, object]


class DiagramModel(TypedDict):
    components: list[dict[str, object]]
    connections: list[dict[str, object]]


class NetworkObjectComponentRow(TypedDict):
    id: str
    component: str
    pypsa_name: str
    position_json: str
    attrs_json: str


class NetworkObjectConnectionRow(TypedDict):
    id: str
    source: str
    target: str
    component: str
    attrs_json: str


class StandardTypeRow(TypedDict):
    name: str
    values: list[str]


class RouterOption(TypedDict):
    name: str
    label: str
    description: str


class ExampleNetworkOption(TypedDict):
    label: str
    path: str


class ExampleNetworkGroup(TypedDict):
    label: str
    networks: list[ExampleNetworkOption]


class OtherTableCell(TypedDict):
    row_index: int
    column: str
    value: str


class OtherTableRow(TypedDict):
    row_index: int
    id: str
    cells: list[OtherTableCell]


class OtherCsvTable(TypedDict):
    component: str
    file_name: str
    columns: list[str]
    rows: list[OtherTableRow]
    index_name: str
    loaded: bool
    dirty: bool


class NetworkDataColumn(TypedDict):
    component: str
    name: str
    type: str
    input_type: str
    is_time_series: bool
    is_bus_reference: bool
    options: list[str]


class NetworkDataCell(TypedDict):
    component: str
    row_id: str
    row_index: int
    attr_name: str
    value: object
    type: str
    input_type: str
    is_time_series: bool
    is_bus_reference: bool
    options: list[str]


class NetworkDataRow(TypedDict):
    component: str
    row_id: str
    row_index: int
    name: str
    cells: list[NetworkDataCell]


class NetworkDataTab(TypedDict):
    component: str
    label: str
    columns: list[NetworkDataColumn]
    rows: list[NetworkDataRow]
    row_count: int


class CanvasSnapshot(TypedDict):
    diagram_nodes: list[DiagramNode]
    component_counters: dict[str, int]
    route_version: int
    selected_node_id: str
    armed_component: str
    armed_branch_component: str
    pending_branch_node_id: str
    branch_bus0_node_id: str


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


def attr_select(attrs: list[AttrRow], default_attr: str) -> rx.Component:
    """Render a dropdown listing component attributes."""
    return rx.select.root(
        rx.select.trigger(width="100%"),
        rx.select.content(
            rx.select.group(
                rx.foreach(attrs, attr_select_item),
            ),
        ),
        default_value=default_attr,
        width="100%",
    )


def attr_select_item(attr: rx.Var[AttrRow]) -> rx.Component:
    """Render one attribute dropdown option."""
    return rx.select.item(
        rx.text(
            attr["label"],
            color=rx.cond(attr["is_time_series"], "orange", "inherit"),
        ),
        value=attr["name"],
    )


def component_row(component: rx.Var[ComponentRow]) -> rx.Component:
    """Render one component row in the catalog table."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.vstack(
                rx.text(component["pypsa_name"], weight="medium"),
                rx.text(component["component"], size="2", color_scheme="gray"),
                spacing="1",
                align="start",
            ),
        ),
        rx.table.cell(
            rx.image(
                src=component["icon_src"],
                alt="Component icon",
                width="36px",
                height="36px",
            ),
        ),
        rx.table.cell(
            attr_select(
                component["attrs"].to(list[AttrRow]),
                component["default_attr"].to(str),
            ),
        ),
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
    return model_sections(NETWORK_MODEL)


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


def load_layout_positions(
    csv_folder: Path,
) -> dict[tuple[str, str], dict[str, float]]:
    """Load saved builder canvas positions keyed by component and PyPSA name."""
    layout_path = csv_folder / LAYOUT_FILE_NAME
    if not layout_path.exists():
        return {}
    try:
        payload = json.loads(layout_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}

    positions: dict[tuple[str, str], dict[str, float]] = {}
    entries = payload.get("positions", []) if isinstance(payload, dict) else []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        component_name = str(entry.get("component", "")).strip()
        pypsa_name = str(entry.get("name", "")).strip()
        if not component_name or not pypsa_name:
            continue
        try:
            positions[(component_name, pypsa_name)] = {
                "x": float(entry.get("x", 0)),
                "y": float(entry.get("y", 0)),
            }
        except TypeError, ValueError:
            continue
    return positions


def apply_layout_positions(
    diagram_nodes: list[DiagramNode],
    layout_positions: dict[tuple[str, str], dict[str, float]],
) -> None:
    """Apply saved builder positions to imported diagram nodes in place."""
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
            node["position"] = {"x": position["x"], "y": position["y"]}


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
    return {
        "id": node_id,
        "component": component.component,
        "pypsa_name": component.pypsa_name,
        "icon_src": row["icon_src"],
        "icon_svg": row["icon_svg"],
        "position": {"x": x, "y": y},
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
    if component_name == "buses":
        return "bus"
    return component_name[:-1] if component_name.endswith("s") else component_name


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
            return bus_position["x"] - 150, bus_position["y"] + y_offset
        return bus_position["x"] + 150, bus_position["y"] + y_offset

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
    return {
        "id": node_id,
        "component": component_type.component,
        "pypsa_name": component_type.pypsa_name,
        "icon_src": row_component["icon_src"],
        "icon_svg": row_component["icon_svg"],
        "position": {"x": float(x), "y": float(y)},
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


def component_table(components: list[ComponentRow]) -> rx.Component:
    """Render a table of component definitions."""
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Component"),
                rx.table.column_header_cell("Icon"),
                rx.table.column_header_cell("Attributes"),
            ),
        ),
        rx.table.body(
            rx.foreach(components, component_row),
        ),
        variant="surface",
        width="100%",
    )


def component_section(title: str, components: list[ComponentRow]) -> rx.Component:
    """Render a titled catalog component section."""
    return rx.vstack(
        rx.heading(title, size="5", as_="h2"),
        component_table(components),
        spacing="3",
        align="stretch",
        width="100%",
    )


def palette_item(component: rx.Var[ComponentRow]) -> rx.Component:
    """Render a draggable and armable palette item for visible canvas components."""
    return rx.tooltip(
        rx.box(
            rx.image(
                src=component["icon_src"],
                alt=component["pypsa_name"],
                width="32px",
                height="32px",
                class_name="palette-symbol",
            ),
            aria_label=component["pypsa_name"],
            draggable=True,
            custom_attrs={
                "data-pypsa-component": component["component"],
                "data-pypsa-icon-src": component["icon_src"],
            },
            on_click=lambda: State.arm_canvas_component(component["component"]),
            width="32px",
            height="32px",
            padding="0",
            margin="0",
            border=rx.cond(
                State.armed_component == component["component"],
                "2px solid var(--accent-9)",
                "0",
            ),
            border_radius="2px",
            cursor="grab",
            background=rx.cond(
                State.armed_component == component["component"],
                "var(--accent-3)",
                "transparent",
            ),
            _hover={"background": "var(--accent-3)"},
            display="flex",
            align_items="center",
            justify_content="center",
        ),
        content=component["pypsa_name"],
    )


def inert_palette_item(component: rx.Var[ComponentRow]) -> rx.Component:
    """Render a non-draggable palette item for unsupported canvas components."""
    return rx.tooltip(
        rx.box(
            rx.image(
                src=component["icon_src"],
                alt=component["pypsa_name"],
                width="32px",
                height="32px",
                opacity="0.55",
                class_name="palette-symbol",
            ),
            aria_label=component["pypsa_name"],
            on_click=lambda: State.open_other_component_dialog(component["component"]),
            width="32px",
            height="32px",
            padding="0",
            margin="0",
            border="0",
            border_radius="2px",
            cursor="pointer",
            background="transparent",
            _hover={"background": "var(--gray-3)"},
            display="flex",
            align_items="center",
            justify_content="center",
        ),
        content=component["pypsa_name"],
    )


def branch_palette_item(component: rx.Var[ComponentRow]) -> rx.Component:
    """Render a click-to-arm palette item for branch components."""
    return rx.tooltip(
        rx.box(
            rx.image(
                src=component["icon_src"],
                alt=component["pypsa_name"],
                width="32px",
                height="32px",
                class_name="palette-symbol",
            ),
            aria_label=component["pypsa_name"],
            on_click=lambda: State.arm_branch_component(component["component"]),
            width="32px",
            height="32px",
            padding="0",
            margin="0",
            border=rx.cond(
                State.armed_branch_component == component["component"],
                "2px solid var(--accent-9)",
                "0",
            ),
            border_radius="2px",
            cursor="pointer",
            background=rx.cond(
                State.armed_branch_component == component["component"],
                "var(--accent-3)",
                "transparent",
            ),
            _hover={"background": "var(--accent-3)"},
            display="flex",
            align_items="center",
            justify_content="center",
        ),
        content=component["pypsa_name"],
    )


def palette_section(
    title: str,
    components: list[ComponentRow],
    columns: str = "1",
    branch: bool = False,
    inert: bool = False,
) -> rx.Component:
    """Render one palette section with selectable item behavior."""
    item_renderer = (
        inert_palette_item if inert else branch_palette_item if branch else palette_item
    )
    return rx.vstack(
        rx.text(title, size="1", weight="medium", color_scheme="gray"),
        rx.grid(
            rx.foreach(components, item_renderer),
            columns=columns,
            spacing="1",
            width="100%",
        ),
        spacing="1",
        align="center",
        width="108px",
        padding="5px",
        border="1px solid var(--gray-6)",
        border_radius="6px",
        background="color-mix(in srgb, var(--color-panel-solid) 66%, transparent)",
    )


def bus_palette_section() -> rx.Component:
    """Render bus and bus-attached component icons."""
    return rx.vstack(
        rx.text("Bus", size="1", weight="medium", color_scheme="gray"),
        rx.grid(
            rx.foreach(State.palette["fundamental"], palette_item),
            rx.foreach(State.palette["primary_components"], palette_item),
            rx.foreach(State.palette["delayed_components"], palette_item),
            columns="2",
            spacing="1",
            width="100%",
        ),
        spacing="1",
        align="center",
        width="108px",
        padding="5px",
        border="1px solid var(--gray-6)",
        border_radius="6px",
        background="color-mix(in srgb, var(--color-panel-solid) 66%, transparent)",
    )


def branch_palette_section() -> rx.Component:
    """Render branch component icons."""
    return rx.vstack(
        rx.text("Branch", size="1", weight="medium", color_scheme="gray"),
        rx.grid(
            rx.foreach(State.palette["primary_branch_components"], branch_palette_item),
            rx.foreach(State.palette["delayed_branch_components"], branch_palette_item),
            columns="2",
            spacing="1",
            width="100%",
        ),
        spacing="1",
        align="center",
        width="108px",
        padding="5px",
        border="1px solid var(--gray-6)",
        border_radius="6px",
        background="color-mix(in srgb, var(--color-panel-solid) 66%, transparent)",
    )


def palette_sidebar() -> rx.Component:
    """Render the left component palette for the builder."""
    return rx.vstack(
        palette_section(
            "Snapshots", State.palette["snapshot_tables"], columns="2", inert=True
        ),
        bus_palette_section(),
        branch_palette_section(),
        palette_section("Other", State.palette["other"], columns="2", inert=True),
        palette_section(
            "Types", State.palette["standard_types"], columns="2", inert=True
        ),
        spacing="2",
        align="stretch",
        width="120px",
        min_width="120px",
        height="100%",
        min_height="0",
        overflow_y="auto",
        padding="6px",
        border_right="1px solid var(--gray-5)",
        class_name="palette-sidebar",
    )


def bus_select_item(bus_name: rx.Var[str]) -> rx.Component:
    """Render one bus option in a bus-reference select."""
    return rx.select.item(bus_name, value=bus_name)


def bus_attr_select(attr: rx.Var[DiagramAttr]) -> rx.Component:
    """Render a bus selector for bus-reference attributes."""
    return rx.select.root(
        rx.select.trigger(placeholder="Select bus", width="100%"),
        rx.select.content(
            rx.select.group(
                rx.foreach(State.canvas_bus_names, bus_select_item),
            ),
        ),
        value=attr["value"].to(str),
        on_change=lambda value: State.update_selected_attr(attr["name"], value),
        width="100%",
    )


def attr_option_item(option: rx.Var[str]) -> rx.Component:
    """Render one standard type option."""
    return rx.select.item(option, value=option)


def standard_type_attr_select(attr: rx.Var[DiagramAttr]) -> rx.Component:
    """Render a selector for PyPSA standard LineType or TransformerType names."""
    return rx.select.root(
        rx.select.trigger(placeholder="Select type", width="100%"),
        rx.select.content(
            rx.select.group(
                rx.foreach(attr["options"], attr_option_item),
            ),
        ),
        value=attr["value"].to(str),
        on_change=lambda value: State.update_selected_attr(attr["name"], value),
        width="100%",
    )


def reference_attr_input(attr: rx.Var[DiagramAttr]) -> rx.Component:
    """Render a global CSV-backed reference selector with free-text entry."""
    return rx.vstack(
        rx.select.root(
            rx.select.trigger(placeholder="Select saved value", width="100%"),
            rx.select.content(
                rx.select.group(
                    rx.foreach(attr["options"], attr_option_item),
                ),
            ),
            value=attr["value"].to(str),
            on_change=lambda value: State.update_selected_attr(attr["name"], value),
            width="100%",
        ),
        rx.hstack(
            rx.input(
                value=attr["value"].to(str),
                placeholder="Type value",
                on_change=lambda value: State.update_selected_attr(attr["name"], value),
                on_blur=lambda value: State.commit_selected_attr_reference(
                    attr["name"], value
                ),
                width="100%",
            ),
            rx.button(
                rx.icon("plus", size=14),
                aria_label="Add reference value",
                title="Add reference value",
                on_click=lambda: State.commit_selected_attr_reference(attr["name"]),
                variant="soft",
                size="2",
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        spacing="2",
        align="stretch",
        width="100%",
    )


def editor_attr(attr: rx.Var[DiagramAttr]) -> rx.Component:
    """Render the editor control for one selected component attribute."""
    return rx.vstack(
        rx.hstack(
            rx.text(
                attr["name"],
                size="2",
                weight="medium",
                color=rx.cond(attr["is_time_series"], "orange", "inherit"),
            ),
            rx.badge(attr["type"], size="1", variant="soft"),
            rx.cond(
                attr["has_time_series_table"],
                rx.button(
                    rx.icon("table-2", size=14),
                    aria_label="Edit time series",
                    title="Edit time series",
                    on_click=lambda: State.open_selected_time_series_attr(attr["name"]),
                    variant="soft",
                    size="1",
                ),
                rx.fragment(),
            ),
            justify="between",
            width="100%",
        ),
        rx.cond(
            attr["input_type"] == "boolean",
            rx.checkbox(
                checked=attr["value"].to(bool),
                on_change=lambda value: State.update_selected_attr(attr["name"], value),
            ),
            rx.cond(
                attr["is_bus_reference"],
                bus_attr_select(attr),
                rx.cond(
                    attr["input_type"] == "reference",
                    reference_attr_input(attr),
                    rx.cond(
                        attr["input_type"] == "select",
                        standard_type_attr_select(attr),
                        rx.input(
                            value=attr["value"].to(str),
                            type=rx.cond(
                                attr["input_type"] == "number",
                                "number",
                                "text",
                            ),
                            on_change=lambda value: State.update_selected_attr(
                                attr["name"], value
                            ),
                            width="100%",
                        ),
                    ),
                ),
            ),
        ),
        spacing="2",
        align="stretch",
        width="100%",
    )


def right_sidebar() -> rx.Component:
    """Render the selected component attribute editor."""
    return rx.vstack(
        rx.hstack(
            rx.heading("Selection", size="4"),
            rx.cond(
                State.selected_node_id != "",
                rx.button(
                    rx.icon("trash-2", size=15),
                    aria_label="Delete selected component",
                    title="Delete selected component",
                    on_click=State.delete_selected_node,
                    color_scheme="red",
                    variant="soft",
                    size="2",
                ),
                rx.fragment(),
            ),
            justify="between",
            align="center",
            width="100%",
        ),
        rx.cond(
            State.selected_node_id != "",
            rx.vstack(
                rx.text(State.selected_node_id, weight="bold"),
                rx.text(State.selected_component_name, size="2", color_scheme="gray"),
                rx.vstack(
                    rx.foreach(State.selected_attr_rows, editor_attr),
                    spacing="3",
                    align="stretch",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
                width="100%",
            ),
            rx.text(
                "Select a node to edit its attributes.", size="2", color_scheme="gray"
            ),
        ),
        spacing="4",
        align="stretch",
        width="var(--inspector-width, 300px)",
        min_width="220px",
        max_width="560px",
        height="100%",
        min_height="0",
        overflow_y="auto",
        padding="12px",
        border_left="1px solid var(--gray-5)",
        class_name="inspector-sidebar",
    )


def inspector_resize_handle() -> rx.Component:
    """Render the draggable divider between canvas and inspector."""
    return rx.box(
        aria_label="Resize selection panel",
        title="Drag to resize selection panel",
        custom_attrs={"data-inspector-resize-handle": "true"},
        width="7px",
        min_width="7px",
        height="100%",
        cursor="col-resize",
        class_name="inspector-resize-handle",
    )


def drag_payload_script() -> rx.Component:
    """Install browser drag payload handling for palette items."""
    return rx.script("""
        if (!window.__pypsaBuilderDragBound) {
          window.__pypsaBuilderDragBound = true;
          document.addEventListener("pointerdown", (event) => {
            const el = event.target.closest("[data-pypsa-component]");
            if (!el) return;
            window.__pypsaBuilderActiveComponent = el.dataset.pypsaComponent;
            window.__pypsaBuilderActivePayload = {
              component: el.dataset.pypsaComponent,
              iconSrc: el.dataset.pypsaIconSrc || "",
            };
          }, true);
          document.addEventListener("dragstart", (event) => {
            const el = event.target.closest("[data-pypsa-component]");
            if (!el || !event.dataTransfer) return;
            window.__pypsaBuilderActiveComponent = el.dataset.pypsaComponent;
            const payload = {
              component: el.dataset.pypsaComponent,
              iconSrc: el.dataset.pypsaIconSrc || "",
            };
            window.__pypsaBuilderActivePayload = payload;
            event.dataTransfer.setData(
              "application/pypsa-component",
              JSON.stringify(payload)
            );
            event.dataTransfer.effectAllowed = "copy";
            const dragImage = document.createElement("canvas");
            dragImage.width = 1;
            dragImage.height = 1;
            event.dataTransfer.setDragImage(dragImage, 0, 0);
          }, true);
          document.addEventListener("dragend", () => {
            window.__pypsaBuilderActiveComponent = "";
            window.__pypsaBuilderActivePayload = null;
          }, true);
        }
        """)


def inspector_resize_script() -> rx.Component:
    """Install browser resizing for the inspector sidebar."""
    return rx.script("""
        if (!window.__pypsaInspectorResizeBound) {
          window.__pypsaInspectorResizeBound = true;
          const savedWidth = localStorage.getItem("pypsaInspectorWidth");
          if (savedWidth) {
            document.documentElement.style.setProperty("--inspector-width", savedWidth);
          }
          let resizeState = null;
          const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
          document.addEventListener("pointerdown", (event) => {
            const handle = event.target.closest("[data-inspector-resize-handle]");
            if (!handle) return;
            const shell = handle.closest(".builder-shell");
            if (!shell) return;
            resizeState = {
              shell,
              pointerId: event.pointerId,
            };
            handle.setPointerCapture?.(event.pointerId);
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
            event.preventDefault();
          }, true);
          document.addEventListener("pointermove", (event) => {
            if (!resizeState) return;
            const rect = resizeState.shell.getBoundingClientRect();
            const width = clamp(rect.right - event.clientX, 220, 560);
            const cssWidth = `${width}px`;
            resizeState.shell.style.setProperty("--inspector-width", cssWidth);
            localStorage.setItem("pypsaInspectorWidth", cssWidth);
            event.preventDefault();
          }, true);
          const stopResize = () => {
            if (!resizeState) return;
            resizeState = null;
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
          };
          document.addEventListener("pointerup", stopResize, true);
          document.addEventListener("pointercancel", stopResize, true);
        }
        """)


def canvas_shortcuts_script() -> rx.Component:
    """Install application keyboard shortcuts."""
    return rx.script("""
        if (!window.__pypsaBuilderShortcutsBound) {
          window.__pypsaBuilderShortcutsBound = true;
          document.addEventListener("keydown", (event) => {
            const target = event.target;
            const tag = (target?.tagName || "").toLowerCase();
            const editable =
              target?.isContentEditable ||
              tag === "input" ||
              tag === "textarea" ||
              tag === "select";
            if (editable || event.metaKey) return;
            const key = String(event.key || "").toLowerCase();
            if (event.altKey && !event.ctrlKey && !event.shiftKey) {
              const menuTriggers = {
                n: "network-menu-trigger",
                c: "canvas-menu-trigger",
                v: "view-menu-trigger",
                d: "data-menu-trigger",
              };
              const triggerId = menuTriggers[key];
              if (triggerId) {
                event.preventDefault();
                document.getElementById(triggerId)?.click();
              }
              return;
            }
            if (!event.ctrlKey || event.altKey) return;
            const shortcutActions = {
              n: "network-name-shortcut",
              o: "network-load-shortcut",
              s: "network-save-shortcut",
              e: "network-export-shortcut",
              r: "canvas-auto-route-shortcut",
              "1": "view-builder-shortcut",
              "2": "view-debug-network-shortcut",
              "3": "view-catalog-shortcut",
            };
            if (event.shiftKey && key === "d") {
              event.preventDefault();
              document.getElementById("data-network-data-shortcut")?.click();
              return;
            }
            if (event.shiftKey && key === "backspace") {
              event.preventDefault();
              document.getElementById("canvas-clear-shortcut")?.click();
              return;
            }
            const actionId = !event.shiftKey ? shortcutActions[key] : null;
            if (actionId) {
              event.preventDefault();
              document.getElementById(actionId)?.click();
              return;
            }
            if (key === "z" && event.shiftKey) {
              event.preventDefault();
              document.getElementById("canvas-redo-button")?.click();
            } else if (key === "z") {
              event.preventDefault();
              document.getElementById("canvas-undo-button")?.click();
            }
          }, true);
        }
        """)


def directory_upload_script(upload_id: str) -> rx.Component:
    """Enable directory selection on a Reflex upload file input."""
    return rx.script(f"""
        setTimeout(() => {{
          const input = document.querySelector("#{upload_id} input[type='file']");
          if (input) {{
            input.setAttribute("webkitdirectory", "");
            input.setAttribute("directory", "");
            input.setAttribute("mozdirectory", "");
          }}
        }}, 0);
        """)


def router_select_item(option: rx.Var[RouterOption]) -> rx.Component:
    """Render one router selector option."""
    return rx.select.item(option["label"], value=option["name"])


def router_select() -> rx.Component:
    """Render the auto-router selector."""
    return rx.select.root(
        rx.select.trigger(placeholder="Router", width="170px"),
        rx.select.content(
            rx.select.group(
                rx.foreach(State.router_options, router_select_item),
            ),
        ),
        value=State.selected_router_name,
        on_change=State.set_selected_router_name,
        width="170px",
    )


def sidebar_toggle(label: str, checked: rx.Var[bool], on_change: Any) -> rx.Component:
    """Render a compact sidebar visibility toggle."""
    return rx.hstack(
        rx.text(label, size="2"),
        rx.spacer(),
        rx.switch(checked=checked, on_change=on_change, size="1"),
        align="center",
        width="190px",
        padding="4px 6px",
    )


def builder_tab() -> rx.Component:
    """Render the main schematic builder tab."""
    return rx.vstack(
        drag_payload_script(),
        inspector_resize_script(),
        canvas_shortcuts_script(),
        rx.hstack(
            rx.cond(State.show_left_sidebar, palette_sidebar(), rx.fragment()),
            rx.vstack(
                rx.box(
                    react_flow_canvas(
                        nodes=State.diagram_nodes,
                        edges=State.diagram_edges,
                        route_version=State.route_version,
                        armed_component=State.armed_component,
                        armed_branch_component=State.armed_branch_component,
                        branch_bus0_node_id=State.branch_bus0_node_id,
                        on_node_drop=State.add_diagram_node,
                        on_node_select=State.select_node,
                        on_branch_bus_click=State.handle_branch_bus_click,
                        on_edge_select=State.select_node,
                        on_nodes_update=State.update_node_positions,
                        on_route_complete=State.finish_auto_route,
                    ),
                    flex="1",
                    min_width="0",
                    min_height="0",
                    height="100%",
                    width="100%",
                    class_name="canvas-panel",
                ),
                flex="1",
                min_width="0",
                min_height="0",
                height="100%",
                width="100%",
                spacing="0",
                align="stretch",
            ),
            rx.cond(
                State.show_right_sidebar,
                rx.fragment(inspector_resize_handle(), right_sidebar()),
                rx.fragment(),
            ),
            spacing="0",
            align="stretch",
            width="100%",
            flex="1",
            border="1px solid var(--gray-5)",
            border_radius="8px",
            overflow="hidden",
            min_height="0",
            min_width="0",
            class_name="builder-shell",
        ),
        spacing="4",
        align="stretch",
        width="100%",
        flex="1",
        min_height="0",
        max_width="100%",
    )


def load_network_dialog() -> rx.Component:
    """Render the controlled dialog for loading a local PyPSA CSV folder."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Load network"),
                rx.dialog.description(
                    "Enter a folder path on the machine running this app.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.input(
                    value=State.network_file_path,
                    on_change=State.set_network_file_path,
                    placeholder="PyPSA CSV folder path",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button(
                        rx.cond(State.is_loading_network, "Loading...", "Load"),
                        on_click=State.load_network_directory_path_to_canvas,
                        disabled=State.is_loading_network,
                    ),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="560px",
        ),
        open=State.is_load_dialog_open,
        on_open_change=State.set_load_dialog_open,
    )


def network_name_dialog() -> rx.Component:
    """Render the controlled dialog for setting the network name."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Set network name"),
                rx.dialog.description(
                    "Enter the name used for display and exports.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.input(
                    value=State.network_name,
                    on_change=State.set_network_name,
                    placeholder="Network name",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button("Done", on_click=State.close_network_name_dialog),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="460px",
        ),
        open=State.is_network_name_dialog_open,
        on_open_change=State.set_network_name_dialog_open,
    )


def undo_redo_buttons() -> rx.Component:
    """Render canvas undo and redo controls."""
    return rx.hstack(
        rx.tooltip(
            rx.button(
                rx.icon("undo-2", size=16),
                aria_label="Undo",
                title="Undo (Ctrl+Z)",
                on_click=State.undo_canvas,
                disabled=rx.cond(State.can_undo_canvas, False, True),
                variant="soft",
                size="2",
                custom_attrs={"id": "canvas-undo-button"},
            ),
            content="Undo (Ctrl+Z)",
        ),
        rx.tooltip(
            rx.button(
                rx.icon("redo-2", size=16),
                aria_label="Redo",
                title="Redo (Ctrl+Shift+Z)",
                on_click=State.redo_canvas,
                disabled=rx.cond(State.can_redo_canvas, False, True),
                variant="soft",
                size="2",
                custom_attrs={"id": "canvas-redo-button"},
            ),
            content="Redo (Ctrl+Shift+Z)",
        ),
        spacing="1",
        align="center",
    )


def clear_canvas_dialog() -> rx.Component:
    """Render the confirmation dialog for clearing the canvas."""
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Clear canvas"),
            rx.alert_dialog.description(
                "This will remove all components, branches, connections, and selection state from the builder canvas.",
                size="2",
                color_scheme="gray",
            ),
            rx.flex(
                rx.alert_dialog.cancel(
                    rx.button("Cancel", variant="soft", color_scheme="gray")
                ),
                rx.alert_dialog.action(
                    rx.button(
                        "Clear canvas",
                        on_click=State.confirm_clear_canvas,
                        color_scheme="red",
                    )
                ),
                spacing="3",
                justify="end",
                width="100%",
            ),
            max_width="460px",
        ),
        open=State.is_clear_canvas_dialog_open,
        on_open_change=State.set_clear_canvas_dialog_open,
    )


def export_network_dialog() -> rx.Component:
    """Render the controlled dialog for exporting the network to a folder."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Export network"),
                rx.dialog.description(
                    "Enter a destination folder path on the machine running this app.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.input(
                    value=State.export_base_folder,
                    on_change=State.set_export_base_folder,
                    placeholder="Export folder path",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button(
                        rx.cond(
                            State.operation_kind == "export", "Exporting...", "Export"
                        ),
                        on_click=State.export_canvas_network,
                        disabled=State.operation_kind == "export",
                    ),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="520px",
        ),
        open=State.is_export_dialog_open,
        on_open_change=State.set_export_dialog_open,
    )


def network_data_tab_trigger(tab: rx.Var[NetworkDataTab]) -> rx.Component:
    """Render one Network Data component tab trigger."""
    return rx.tabs.trigger(
        rx.hstack(
            rx.text(tab["label"], size="2"),
            rx.badge(tab["row_count"].to(str), variant="soft", size="1"),
            spacing="1",
            align="center",
        ),
        value=tab["component"],
    )


def network_data_header_cell(column: rx.Var[NetworkDataColumn]) -> rx.Component:
    """Render one Network Data table header cell."""
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(
                column["name"],
                size="2",
                weight="medium",
                color=rx.cond(column["is_time_series"], "orange", "inherit"),
            ),
            rx.badge(column["type"], size="1", variant="soft"),
            spacing="1",
            align="center",
        ),
        min_width="170px",
        white_space="nowrap",
    )


def network_data_option_item(option: rx.Var[str]) -> rx.Component:
    """Render one Network Data select option."""
    return rx.select.item(option, value=option)


def network_data_bus_select(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render a bus reference selector in the Network Data grid."""
    return rx.select.root(
        rx.select.trigger(placeholder="Select bus", width="100%"),
        rx.select.content(
            rx.select.group(
                rx.foreach(State.canvas_bus_names, network_data_option_item),
            ),
        ),
        value=cell["value"].to(str),
        on_change=lambda value: State.update_network_data_cell(
            cell["component"],
            cell["row_id"],
            cell["row_index"],
            cell["attr_name"],
            value,
        ),
        width="100%",
    )


def network_data_option_select(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render an option selector in the Network Data grid."""
    return rx.select.root(
        rx.select.trigger(placeholder="Select value", width="100%"),
        rx.select.content(
            rx.select.group(
                rx.foreach(cell["options"], network_data_option_item),
            ),
        ),
        value=cell["value"].to(str),
        on_change=lambda value: State.update_network_data_cell(
            cell["component"],
            cell["row_id"],
            cell["row_index"],
            cell["attr_name"],
            value,
        ),
        width="100%",
    )


def network_data_text_input(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render a text/number input in the Network Data grid."""
    return rx.input(
        value=cell["value"].to(str),
        type=rx.cond(cell["input_type"] == "number", "number", "text"),
        on_change=lambda value: State.update_network_data_cell(
            cell["component"],
            cell["row_id"],
            cell["row_index"],
            cell["attr_name"],
            value,
        ),
        on_blur=lambda value: State.commit_network_data_reference(
            cell["component"],
            cell["attr_name"],
            value,
        ),
        width="100%",
        min_width="150px",
    )


def network_data_cell_control(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render the appropriate Network Data cell editor."""
    return rx.cond(
        cell["input_type"] == "boolean",
        rx.checkbox(
            checked=cell["value"].to(bool),
            on_change=lambda value: State.update_network_data_cell(
                cell["component"],
                cell["row_id"],
                cell["row_index"],
                cell["attr_name"],
                value,
            ),
        ),
        rx.cond(
            cell["is_bus_reference"],
            network_data_bus_select(cell),
            rx.cond(
                cell["input_type"] == "select",
                network_data_option_select(cell),
                network_data_text_input(cell),
            ),
        ),
    )


def network_data_cell(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render one editable Network Data table cell."""
    return rx.table.cell(
        rx.hstack(
            network_data_cell_control(cell),
            rx.cond(
                cell["is_time_series"],
                rx.button(
                    rx.icon("table-2", size=14),
                    aria_label="Edit time series",
                    title="Edit time series",
                    on_click=lambda: State.open_network_data_time_series_attr(
                        cell["component"],
                        cell["row_id"],
                        cell["row_index"],
                        cell["attr_name"],
                    ),
                    variant="soft",
                    size="1",
                    flex_shrink="0",
                ),
                rx.fragment(),
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        min_width="190px",
    )


def network_data_row(row: rx.Var[NetworkDataRow]) -> rx.Component:
    """Render one Network Data table row."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.input(
                value=row["name"],
                placeholder="name",
                on_change=lambda value: State.update_network_data_row_name(
                    row["component"],
                    row["row_id"],
                    row["row_index"],
                    value,
                ),
                width="100%",
                min_width="180px",
            ),
            min_width="190px",
            position="sticky",
            left="0",
            background="var(--color-panel-solid)",
            z_index="1",
        ),
        rx.foreach(row["cells"], network_data_cell),
    )


def network_data_table(tab: rx.Var[NetworkDataTab]) -> rx.Component:
    """Render one Network Data component table."""
    return rx.vstack(
        rx.text(
            rx.cond(
                tab["row_count"] == 0,
                "No rows for this component.",
                "",
            ),
            size="2",
            color_scheme="gray",
        ),
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell(
                            "Name",
                            min_width="190px",
                            position="sticky",
                            left="0",
                            background="var(--color-panel-solid)",
                            z_index="2",
                        ),
                        rx.foreach(tab["columns"], network_data_header_cell),
                    ),
                ),
                rx.table.body(rx.foreach(tab["rows"], network_data_row)),
                variant="surface",
                size="2",
                width="100%",
                min_width="max-content",
            ),
            max_height="62vh",
            max_width="100%",
            overflow_x="auto",
            overflow_y="auto",
        ),
        spacing="3",
        align="stretch",
        width="100%",
    )


def network_data_tab_content(tab: rx.Var[NetworkDataTab]) -> rx.Component:
    """Render one Network Data tab content panel."""
    return rx.tabs.content(
        network_data_table(tab),
        value=tab["component"],
        width="100%",
        min_height="0",
    )


def network_data_dialog() -> rx.Component:
    """Render the editable whole-network data dialog."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.dialog.title("Network Data"),
                rx.dialog.close(
                    rx.button(
                        rx.icon("x", size=16),
                        aria_label="Close network data",
                        title="Close",
                        variant="ghost",
                        size="2",
                    )
                ),
                justify="between",
                align="center",
                width="100%",
            ),
            rx.tabs.root(
                rx.tabs.list(
                    rx.foreach(State.network_data_tabs, network_data_tab_trigger),
                    overflow_x="auto",
                    width="100%",
                    flex_wrap="nowrap",
                ),
                rx.foreach(State.network_data_tabs, network_data_tab_content),
                value=State.network_data_active_component,
                on_change=State.set_network_data_active_component,
                width="100%",
                margin_top="12px",
            ),
            width="96vw",
            max_width="1800px",
        ),
        open=State.is_network_data_dialog_open,
        on_open_change=State.set_network_data_dialog_open,
    )


def network_object_component_item(
    component: rx.Var[NetworkObjectComponentRow],
) -> rx.Component:
    """Render one component entry in the debug network object view."""
    return rx.el.details(
        rx.el.summary(
            rx.hstack(
                rx.text(component["id"], weight="medium"),
                rx.badge(component["component"], variant="soft"),
                spacing="2",
                align="center",
            ),
        ),
        rx.vstack(
            rx.hstack(
                rx.text("pypsa_name", size="2", color_scheme="gray"),
                rx.code(component["pypsa_name"]),
                spacing="2",
                align="center",
            ),
            rx.text("position", size="2", color_scheme="gray"),
            rx.code_block(component["position_json"], language="json", width="100%"),
            rx.text("attrs", size="2", color_scheme="gray"),
            rx.code_block(component["attrs_json"], language="json", width="100%"),
            spacing="2",
            align="stretch",
            padding="8px 0 0 16px",
        ),
        style={
            "border": "1px solid var(--gray-5)",
            "borderRadius": "6px",
            "padding": "8px 10px",
            "background": "var(--color-panel-solid)",
        },
    )


def network_object_connection_item(
    connection: rx.Var[NetworkObjectConnectionRow],
) -> rx.Component:
    """Render one connection entry in the debug network object view."""
    return rx.el.details(
        rx.el.summary(
            rx.hstack(
                rx.text(connection["id"], weight="medium"),
                rx.badge(connection["component"], variant="soft"),
                spacing="2",
                align="center",
            ),
        ),
        rx.vstack(
            rx.hstack(
                rx.text("source", size="2", color_scheme="gray"),
                rx.code(connection["source"]),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                rx.text("target", size="2", color_scheme="gray"),
                rx.code(connection["target"]),
                spacing="2",
                align="center",
            ),
            rx.text("attrs", size="2", color_scheme="gray"),
            rx.code_block(connection["attrs_json"], language="json", width="100%"),
            spacing="2",
            align="stretch",
            padding="8px 0 0 16px",
        ),
        style={
            "border": "1px solid var(--gray-5)",
            "borderRadius": "6px",
            "padding": "8px 10px",
            "background": "var(--color-panel-solid)",
        },
    )


def network_object_view() -> rx.Component:
    """Render the current diagram model as expandable data."""
    return rx.vstack(
        rx.el.details(
            rx.el.summary(rx.text("components", weight="medium")),
            rx.vstack(
                rx.foreach(
                    State.network_component_rows,
                    network_object_component_item,
                ),
                spacing="2",
                align="stretch",
                padding="8px 0 0 16px",
            ),
            open=True,
        ),
        rx.el.details(
            rx.el.summary(rx.text("connections", weight="medium")),
            rx.vstack(
                rx.foreach(
                    State.network_connection_rows,
                    network_object_connection_item,
                ),
                spacing="2",
                align="stretch",
                padding="8px 0 0 16px",
            ),
        ),
        spacing="2",
        align="stretch",
        width="100%",
    )


def demo_styles() -> rx.Component:
    """Render CSS used by the builder canvas and schematic nodes."""
    return rx.html("""
        <style>
          html,
          body {
            background:
              radial-gradient(circle at 22% 0%, color-mix(in srgb, var(--accent-3) 22%, transparent) 0, transparent 34%),
              linear-gradient(180deg, var(--gray-4), var(--gray-3) 45%, var(--gray-4));
          }
          .app-menu,
          .app-footer {
            backdrop-filter: blur(14px);
            background: #1f4e5f !important;
            color: #f8fafc;
          }
          .app-menu {
            box-shadow: 0 1px 0 color-mix(in srgb, #0f2f3a 48%, transparent);
          }
          .app-menu :where(button, a, [role="button"]),
          .app-footer :where(button, a, [role="button"]) {
            color: #f8fafc;
          }
          .app-content {
            background: var(--gray-4);
          }
          .builder-shell {
            border-color: color-mix(in srgb, var(--gray-7) 72%, transparent) !important;
            border-radius: 10px !important;
            background: var(--gray-3);
            box-shadow:
              0 18px 45px color-mix(in srgb, var(--gray-12) 10%, transparent),
              0 1px 0 color-mix(in srgb, white 55%, transparent) inset;
          }
          .builder-toolbar {
            min-height: 46px;
            background: linear-gradient(180deg, var(--gray-4), var(--gray-3));
          }
          .palette-sidebar,
          .inspector-sidebar {
            background: var(--gray-4);
          }
          .palette-sidebar {
            padding: 6px !important;
          }
          .inspector-sidebar {
            padding: 14px !important;
          }
          .inspector-resize-handle {
            background: color-mix(in srgb, var(--gray-6) 42%, transparent);
            border-left: 1px solid color-mix(in srgb, var(--gray-7) 60%, transparent);
            border-right: 1px solid color-mix(in srgb, var(--gray-7) 60%, transparent);
            transition: background 120ms ease;
          }
          .inspector-resize-handle:hover {
            background: var(--accent-6);
          }
          .canvas-panel {
            background: var(--gray-3);
          }
          .react-flow-shell {
            position: relative;
            width: 100%;
            height: 680px;
            background:
              linear-gradient(var(--gray-4) 1px, transparent 1px),
              linear-gradient(90deg, var(--gray-4) 1px, transparent 1px),
              radial-gradient(circle at 50% 0%, color-mix(in srgb, var(--accent-3) 22%, transparent), transparent 42%),
              var(--gray-3);
            background-size: 28px 28px, 28px 28px, 100% 100%, 100% 100%;
          }
          .schematic-node {
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            gap: 3px;
            width: 100%;
            height: 100%;
            border: 1px solid transparent;
            border-radius: 6px;
            background: transparent;
            cursor: grab;
            overflow: visible;
            transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
          }
          .schematic-node[data-selected="true"] {
            border-color: var(--accent-9);
            background: color-mix(in srgb, var(--accent-3) 70%, transparent);
            box-shadow: 0 0 0 2px var(--accent-5), 0 10px 24px color-mix(in srgb, var(--accent-9) 20%, transparent);
          }
          .schematic-node:hover {
            border-color: #2563eb;
            background: #dbeafe;
            box-shadow: 0 0 0 3px color-mix(in srgb, #60a5fa 58%, transparent);
            transform: translateY(-1px);
          }
          .schematic-node[data-is-bus="true"]:hover {
            transform: none;
          }
          .schematic-node[data-is-bus="true"] {
            justify-content: flex-start;
          }
          .schematic-node[data-branch-armed="true"] {
            cursor: crosshair;
          }
          .schematic-node[data-branch-hover="true"] {
            border-color: #2563eb;
            background: #dbeafe;
            box-shadow: 0 0 0 3px color-mix(in srgb, #60a5fa 58%, transparent);
          }
          .schematic-node[data-branch-start="true"] {
            border-color: var(--green-9);
            background: var(--green-3);
            box-shadow: 0 0 0 3px var(--green-5);
          }
          .drag-preview-node {
            position: absolute;
            z-index: 20;
            pointer-events: none;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px solid var(--accent-9);
            border-radius: 6px;
            background: color-mix(in srgb, var(--accent-3) 82%, white);
            color: var(--gray-12);
            font-size: 10px;
            font-weight: 700;
            box-shadow: 0 10px 28px color-mix(in srgb, var(--gray-12) 18%, transparent);
            opacity: 0.88;
            transform: translate(-50%, -50%);
          }
          .react-flow-shell[data-armed-component="true"] {
            cursor: crosshair;
          }
          .schematic-node-symbol {
            display: block;
            width: 100%;
            flex: 0 0 auto;
            min-height: 0;
          }
          .schematic-bus-symbol {
            display: block;
            width: 3px;
            min-height: 72px;
            border-radius: 999px;
            background: var(--gray-12);
            flex: 0 0 auto;
          }
          .schematic-terminal {
            position: absolute;
            z-index: 2;
            width: 13px;
            height: 2px;
            background: var(--gray-12);
            pointer-events: none;
            transform: translateY(-50%);
          }
          .schematic-terminal::after {
            content: "";
            position: absolute;
            top: 50%;
            width: 6px;
            height: 6px;
            border-radius: 999px;
            background: var(--gray-12);
            transform: translate(-50%, -50%);
          }
          .schematic-terminal-left {
            left: 0;
          }
          .schematic-terminal-left::after {
            left: 0;
          }
          .schematic-terminal-right {
            right: 0;
          }
          .schematic-terminal-right::after {
            left: 100%;
          }
          .schematic-node-symbol svg {
            display: block;
            width: 100%;
            height: 100%;
            overflow: visible;
          }
          .schematic-node-label {
            max-width: 96px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: var(--gray-12);
            font-size: 10px;
            line-height: 12px;
            pointer-events: none;
          }
          .schematic-node-handle {
            width: 6px;
            height: 6px;
            border: 0;
            background: transparent;
            opacity: 0;
          }
          .schematic-edge-label {
            position: absolute;
            z-index: 5;
            padding: 2px 5px;
            border-radius: 4px;
            background: var(--color-panel-solid);
            color: var(--gray-12);
            font-size: 10px;
            line-height: 14px;
            white-space: nowrap;
            pointer-events: none;
            transform-origin: center;
            box-shadow: 0 1px 3px color-mix(in srgb, var(--gray-12) 10%, transparent);
          }
          .schematic-edge-label[data-selected="true"] {
            outline: 1px solid var(--accent-8);
          }
          [data-is-root-theme="dark"] .schematic-node-symbol,
          [data-theme="dark"] .schematic-node-symbol,
          .dark .schematic-node-symbol,
          [data-is-root-theme="dark"] .palette-symbol,
          [data-theme="dark"] .palette-symbol,
          .dark .palette-symbol {
            filter: invert(1) brightness(1.35) contrast(1.1);
          }
          [data-is-root-theme="dark"] .schematic-node-label,
          [data-theme="dark"] .schematic-node-label,
          .dark .schematic-node-label {
            color: #ffffff;
          }
          [data-is-root-theme="dark"] .react-flow-shell,
          [data-theme="dark"] .react-flow-shell,
          .dark .react-flow-shell {
            background:
              linear-gradient(rgba(255,255,255,0.055) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.055) 1px, transparent 1px),
              radial-gradient(circle at 50% 0%, rgba(77, 144, 254, 0.14), transparent 42%),
              #0f1115;
            background-size: 28px 28px, 28px 28px, 100% 100%, 100% 100%;
          }
          [data-is-root-theme="dark"] .builder-shell,
          [data-theme="dark"] .builder-shell,
          .dark .builder-shell {
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.32);
          }
          [data-is-root-theme="dark"] .builder-toolbar,
          [data-theme="dark"] .builder-toolbar,
          .dark .builder-toolbar {
            background: linear-gradient(180deg, var(--gray-2), var(--color-panel-solid));
          }
        </style>
        """)


def catalog_tab() -> rx.Component:
    """Render the component metadata catalog tab."""
    return rx.vstack(
        component_section("Fundamental Component", State.sections["fundamental"]),
        component_section("Components", State.sections["components"]),
        component_section(
            "Branch Components",
            State.sections["branch_components"],
        ),
        component_section("Other", State.sections["other"]),
        spacing="5",
        align="stretch",
        width="100%",
        max_width="1100px",
    )


def upload_panel() -> rx.Component:
    """Render legacy catalog upload controls for inspecting loaded defaults."""
    return rx.vstack(
        rx.upload(
            rx.vstack(
                rx.text("Drop a PyPSA network file here, or click to choose one."),
                rx.text(
                    ".nc, .h5, .hdf5, or .zip containing a CSV-folder export",
                    size="2",
                    color_scheme="gray",
                ),
                rx.text(rx.selected_files(UPLOAD_ID), size="2"),
                spacing="2",
                align="center",
            ),
            id=UPLOAD_ID,
            max_files=1,
            multiple=False,
            accept={
                "application/netcdf": [".nc"],
                "application/x-hdf": [".h5", ".hdf5"],
                "application/zip": [".zip"],
            },
            border="1px dashed var(--gray-7)",
            border_radius="8px",
            padding="18px",
            width="100%",
        ),
        rx.hstack(
            rx.button(
                "Load network",
                on_click=State.load_network(rx.upload_files(upload_id=UPLOAD_ID)),
            ),
            rx.button(
                "Clear",
                variant="soft",
                on_click=rx.clear_selected_files(UPLOAD_ID),
            ),
            spacing="3",
        ),
        rx.divider(),
        rx.upload(
            rx.vstack(
                rx.text("Select a PyPSA CSV export directory."),
                rx.text(
                    "Use this for folders containing buses.csv, lines.csv, loads.csv, etc.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.text(rx.selected_files(FOLDER_UPLOAD_ID), size="2"),
                spacing="2",
                align="center",
            ),
            id=FOLDER_UPLOAD_ID,
            multiple=True,
            accept={"text/csv": [".csv"]},
            border="1px dashed var(--gray-7)",
            border_radius="8px",
            padding="18px",
            width="100%",
        ),
        directory_upload_script(FOLDER_UPLOAD_ID),
        rx.hstack(
            rx.button(
                "Load directory",
                on_click=State.load_network_folder(
                    rx.upload_files(upload_id=FOLDER_UPLOAD_ID)
                ),
            ),
            rx.button(
                "Clear",
                variant="soft",
                on_click=rx.clear_selected_files(FOLDER_UPLOAD_ID),
            ),
            spacing="3",
        ),
        rx.text(State.load_message, size="2", color_scheme="gray"),
        rx.cond(
            State.load_error != "",
            rx.text(State.load_error, size="2", color_scheme="red"),
            rx.fragment(),
        ),
        spacing="3",
        align="stretch",
        width="100%",
    )


def pypsa_example_menu_item(example: rx.Var[ExampleNetworkOption]) -> rx.Component:
    """Render one PyPSA example network submenu item."""
    return rx.menu.item(
        example["label"],
        on_select=lambda: State.load_pypsa_example_network(example["path"]),
    )


def pypsa_example_menu_group(group: rx.Var[ExampleNetworkGroup]) -> rx.Component:
    """Render one top-level PyPSA example directory submenu."""
    return rx.menu.sub(
        rx.menu.sub_trigger(group["label"]),
        rx.menu.sub_content(
            rx.foreach(
                group["networks"],
                pypsa_example_menu_item,
            ),
            align="start",
            size="2",
            variant="soft",
        ),
    )


def network_menu() -> rx.Component:
    """Render the top-level network file menu."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                "Network",
                rx.icon("chevron-down", size=14),
                aria_label="Network menu",
                variant="ghost",
                size="2",
                title="Network menu (Alt+N)",
                custom_attrs={"id": "network-menu-trigger"},
            )
        ),
        rx.menu.content(
            rx.menu.item(
                "Set Name",
                shortcut="Ctrl+N",
                on_select=State.open_network_name_dialog,
            ),
            rx.menu.separator(),
            rx.menu.item(
                "New",
                on_select=State.new_network,
            ),
            rx.menu.item(
                "Load",
                shortcut="Ctrl+O",
                on_select=State.choose_network_directory_and_load,
                disabled=State.is_loading_network,
            ),
            rx.menu.item(
                "Save",
                shortcut="Ctrl+S",
                on_select=State.save_canvas_network_to_loaded_folder,
                disabled=rx.cond(
                    State.save_network_folder != "",
                    State.operation_kind == "save",
                    True,
                ),
            ),
            rx.menu.item(
                "Open in Jupyter",
                on_select=State.open_network_in_jupyter,
                disabled=State.operation_kind != "",
            ),
            rx.menu.sub(
                rx.menu.sub_trigger("Pypsa Network Examples"),
                rx.menu.sub_content(
                    rx.foreach(
                        State.pypsa_example_networks,
                        pypsa_example_menu_group,
                    ),
                    align="start",
                    size="2",
                    variant="soft",
                ),
            ),
            rx.menu.separator(),
            rx.menu.item(
                "Export",
                shortcut="Ctrl+E",
                on_select=State.choose_export_folder,
                disabled=State.operation_kind == "export",
            ),
            align="start",
            size="2",
            variant="soft",
        ),
    )


def canvas_menu() -> rx.Component:
    """Render the top-level canvas menu."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                "Canvas",
                rx.icon("chevron-down", size=14),
                aria_label="Canvas menu",
                variant="ghost",
                size="2",
                title="Canvas menu (Alt+C)",
                custom_attrs={"id": "canvas-menu-trigger"},
            )
        ),
        rx.menu.content(
            rx.menu.item(
                "Auto route",
                shortcut="Ctrl+R",
                on_select=State.auto_route_canvas,
            ),
            rx.box(
                rx.hstack(
                    rx.text("Router", size="2"),
                    router_select(),
                    spacing="2",
                    align="center",
                    padding="4px 6px",
                )
            ),
            rx.menu.separator(),
            rx.menu.item(
                "Undo",
                shortcut="Ctrl+Z",
                on_select=State.undo_canvas,
                disabled=rx.cond(State.can_undo_canvas, False, True),
            ),
            rx.menu.item(
                "Redo",
                shortcut="Ctrl+Shift+Z",
                on_select=State.redo_canvas,
                disabled=rx.cond(State.can_redo_canvas, False, True),
            ),
            rx.menu.separator(),
            rx.menu.item(
                "Clear",
                shortcut="Ctrl+Shift+Backspace",
                on_select=State.open_clear_canvas_dialog,
                color_scheme="red",
            ),
            rx.menu.separator(),
            rx.box(
                sidebar_toggle(
                    "Left sidebar",
                    State.show_left_sidebar,
                    State.set_show_left_sidebar,
                ),
                sidebar_toggle(
                    "Right sidebar",
                    State.show_right_sidebar,
                    State.set_show_right_sidebar,
                ),
                padding="2px",
            ),
            align="start",
            size="2",
            variant="soft",
        ),
    )


def view_menu() -> rx.Component:
    """Render the top-level view selector menu."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                "View",
                rx.icon("chevron-down", size=14),
                aria_label="View menu",
                variant="ghost",
                size="2",
                title="View menu (Alt+V)",
                custom_attrs={"id": "view-menu-trigger"},
            )
        ),
        rx.menu.content(
            rx.menu.item(
                "Builder",
                shortcut="Ctrl+1",
                on_select=State.show_builder_view,
                disabled=State.active_view == "builder",
            ),
            rx.menu.item(
                "Debug-Network",
                shortcut="Ctrl+2",
                on_select=State.show_debug_network_view,
                disabled=State.active_view == "debug-network",
            ),
            rx.menu.item(
                "Catalog",
                shortcut="Ctrl+3",
                on_select=State.show_catalog_view,
                disabled=State.active_view == "catalog",
            ),
            align="start",
            size="2",
            variant="soft",
        ),
    )


def data_menu() -> rx.Component:
    """Render the top-level data menu."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                "Data",
                rx.icon("chevron-down", size=14),
                aria_label="Data menu",
                variant="ghost",
                size="2",
                title="Data menu (Alt+D)",
                custom_attrs={"id": "data-menu-trigger"},
            )
        ),
        rx.menu.content(
            rx.menu.item(
                "Network Data",
                shortcut="Ctrl+Shift+D",
                on_select=State.open_network_data_dialog,
            ),
            align="start",
            size="2",
            variant="soft",
        ),
    )


def shortcut_actions() -> rx.Component:
    """Render hidden controls used by global keyboard shortcuts."""
    return rx.box(
        rx.button(
            "Set Name",
            id="network-name-shortcut",
            on_click=State.open_network_name_dialog,
        ),
        rx.button(
            "Load",
            id="network-load-shortcut",
            on_click=State.choose_network_directory_and_load,
            disabled=State.is_loading_network,
        ),
        rx.button(
            "Save",
            id="network-save-shortcut",
            on_click=State.save_canvas_network_to_loaded_folder,
            disabled=rx.cond(
                State.save_network_folder != "",
                State.operation_kind == "save",
                True,
            ),
        ),
        rx.button(
            "Export",
            id="network-export-shortcut",
            on_click=State.choose_export_folder,
            disabled=State.operation_kind == "export",
        ),
        rx.button(
            "Auto route",
            id="canvas-auto-route-shortcut",
            on_click=State.auto_route_canvas,
        ),
        rx.button(
            "Undo",
            id="canvas-undo-button",
            on_click=State.undo_canvas,
            disabled=rx.cond(State.can_undo_canvas, False, True),
        ),
        rx.button(
            "Redo",
            id="canvas-redo-button",
            on_click=State.redo_canvas,
            disabled=rx.cond(State.can_redo_canvas, False, True),
        ),
        rx.button(
            "Clear",
            id="canvas-clear-shortcut",
            on_click=State.open_clear_canvas_dialog,
        ),
        rx.button(
            "Builder",
            id="view-builder-shortcut",
            on_click=State.show_builder_view,
        ),
        rx.button(
            "Debug-Network",
            id="view-debug-network-shortcut",
            on_click=State.show_debug_network_view,
        ),
        rx.button(
            "Catalog",
            id="view-catalog-shortcut",
            on_click=State.show_catalog_view,
        ),
        rx.button(
            "Network Data",
            id="data-network-data-shortcut",
            on_click=State.open_network_data_dialog,
        ),
        display="none",
    )


def menu_bar() -> rx.Component:
    """Render the compact application menu bar."""
    return rx.hstack(
        network_menu(),
        canvas_menu(),
        view_menu(),
        data_menu(),
        shortcut_actions(),
        rx.spacer(),
        rx.text(State.network_name, size="2", color="#f8fafc"),
        spacing="4",
        align="center",
        width="100%",
        height="44px",
        padding="0 16px",
        border_bottom="1px solid var(--gray-5)",
        background="var(--color-panel-solid)",
        class_name="app-menu",
    )


def footer_bar() -> rx.Component:
    """Render the compact footer with the color mode selector."""
    return rx.hstack(
        rx.text(
            rx.cond(
                State.is_operation_dialog_open,
                State.operation_status,
                "Ready",
            ),
            size="2",
            color_scheme="gray",
        ),
        rx.spacer(),
        rx.color_mode.button(size="2", variant="soft"),
        align="center",
        width="100%",
        height="34px",
        padding="0 16px",
        border_top="1px solid var(--gray-5)",
        background="var(--color-panel-solid)",
        class_name="app-footer",
    )


def operation_dialog() -> rx.Component:
    """Render the modal progress dialog for long-running network operations."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.cond(
                        State.operation_is_error,
                        rx.badge("Error", color_scheme="red", variant="soft"),
                        rx.spinner(size="3"),
                    ),
                    rx.vstack(
                        rx.dialog.title(State.operation_title),
                        rx.dialog.description(
                            State.operation_status,
                            size="2",
                            color_scheme=rx.cond(
                                State.operation_is_error,
                                "red",
                                "gray",
                            ),
                        ),
                        spacing="1",
                        align="start",
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                rx.cond(
                    State.operation_is_error,
                    rx.hstack(
                        rx.button(
                            "Close",
                            on_click=State.close_operation_dialog,
                            variant="soft",
                        ),
                        justify="end",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="420px",
        ),
        open=State.is_operation_dialog_open,
    )


def other_component_dialog() -> rx.Component:
    """Render dialogs for non-canvas sidebar components."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(State.other_component_dialog_title),
            rx.cond(
                State.other_component_dialog_kind == "standard_type",
                standard_type_table(),
                rx.cond(
                    State.other_component_dialog_kind == "csv_table",
                    other_csv_table_editor(),
                    rx.dialog.description(
                        "List manager to be added",
                        size="2",
                        color_scheme="gray",
                    ),
                ),
            ),
            rx.cond(
                State.other_table_error != "",
                rx.text(State.other_table_error, size="2", color_scheme="red"),
                rx.fragment(),
            ),
            rx.flex(
                rx.cond(
                    State.other_component_dialog_kind == "csv_table",
                    rx.hstack(
                        rx.upload(
                            rx.button("Upload CSV", variant="soft"),
                            id=EDITABLE_CSV_UPLOAD_ID,
                            multiple=False,
                            max_files=1,
                            accept={"text/csv": [".csv"]},
                            on_drop=State.upload_editable_csv(
                                rx.upload_files(upload_id=EDITABLE_CSV_UPLOAD_ID)
                            ),
                            border="none",
                            padding="0",
                            width="fit-content",
                        ),
                        rx.button(
                            "Add row",
                            on_click=State.add_other_table_row,
                            variant="soft",
                        ),
                        spacing="2",
                    ),
                    rx.fragment(),
                ),
                rx.dialog.close(
                    rx.button("OK", on_click=State.close_other_component_dialog)
                ),
                spacing="2",
                justify="end",
                width="100%",
                margin_top="16px",
            ),
            width="96vw",
            max_width="1600px",
        ),
        open=State.is_other_component_dialog_open,
        on_open_change=State.set_other_component_dialog_open,
    )


def other_csv_header_cell(column: rx.Var[str]) -> rx.Component:
    """Render one editable supplemental CSV table header."""
    return rx.table.column_header_cell(
        column,
        min_width="150px",
        white_space="nowrap",
    )


def other_csv_cell(cell: rx.Var[OtherTableCell]) -> rx.Component:
    """Render one editable supplemental CSV table value."""
    return rx.table.cell(
        rx.input(
            value=cell["value"],
            on_change=lambda value: State.update_other_table_cell(
                cell["row_index"],
                cell["column"],
                value,
            ),
            width="100%",
            min_width="150px",
        ),
        min_width="150px",
    )


def other_csv_row(row: rx.Var[OtherTableRow]) -> rx.Component:
    """Render one editable supplemental CSV table row."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.input(
                value=row["id"],
                placeholder="row id",
                on_change=lambda value: State.update_other_table_row_id(
                    row["row_index"],
                    value,
                ),
                width="100%",
                min_width="180px",
            ),
            min_width="180px",
        ),
        rx.foreach(row["cells"], other_csv_cell),
        rx.table.cell(
            rx.button(
                rx.icon("trash-2", size=16),
                aria_label="Delete row",
                title="Delete row",
                on_click=lambda: State.delete_other_table_row(row["row_index"]),
                variant="soft",
                color_scheme="red",
                size="1",
            ),
            min_width="70px",
        ),
    )


def other_csv_table_editor() -> rx.Component:
    """Render an editable supplemental CSV table."""
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell(
                        "Name",
                        min_width="180px",
                        white_space="nowrap",
                    ),
                    rx.foreach(
                        State.other_table_dialog_columns,
                        other_csv_header_cell,
                    ),
                    rx.table.column_header_cell(""),
                ),
            ),
            rx.table.body(rx.foreach(State.other_table_dialog_rows, other_csv_row)),
            variant="surface",
            size="2",
            width="100%",
            min_width="max-content",
        ),
        max_height="520px",
        max_width="100%",
        overflow_x="auto",
        overflow_y="auto",
        margin_top="12px",
    )


def standard_type_row(row: rx.Var[StandardTypeRow]) -> rx.Component:
    """Render one standard line or transformer type row."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.text(row["name"], weight="medium", white_space="nowrap"),
            min_width="220px",
        ),
        rx.foreach(row["values"], standard_type_value_cell),
    )


def standard_type_header_cell(column: rx.Var[str]) -> rx.Component:
    """Render a standard type parameter table header."""
    return rx.table.column_header_cell(
        column,
        min_width="120px",
        white_space="nowrap",
    )


def standard_type_value_cell(value: rx.Var[str]) -> rx.Component:
    """Render one standard type parameter value."""
    return rx.table.cell(
        rx.text(value, size="2", white_space="nowrap"),
        min_width="120px",
    )


def standard_type_table() -> rx.Component:
    """Render the selected standard type table."""
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.foreach(
                        State.standard_type_dialog_columns,
                        standard_type_header_cell,
                    ),
                ),
            ),
            rx.table.body(
                rx.foreach(State.standard_type_dialog_rows, standard_type_row)
            ),
            variant="surface",
            size="2",
            width="100%",
            min_width="max-content",
        ),
        max_height="520px",
        max_width="100%",
        overflow_x="auto",
        overflow_y="auto",
        margin_top="12px",
    )


def debug_network_tab() -> rx.Component:
    """Render the debug view for the in-memory network object."""
    return rx.vstack(
        rx.heading("Debug-Network", size="5"),
        network_object_view(),
        spacing="3",
        align="stretch",
        width="100%",
    )


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
    diagram_model: DiagramModel = {"components": [], "connections": []}
    network_component_rows: list[NetworkObjectComponentRow] = []
    network_connection_rows: list[NetworkObjectConnectionRow] = []
    canvas_bus_names: list[str] = []
    router_options: list[RouterOption] = ROUTER_OPTIONS
    selected_router_name: str = JS_ELK_ROUTER_NAME
    active_view: str = "builder"
    show_left_sidebar: bool = True
    show_right_sidebar: bool = True
    route_version: int = 0
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
    pending_branch_node_id: str = ""
    branch_bus0_node_id: str = ""
    load_message: str = "Using empty PyPSA network defaults."
    load_error: str = ""
    loaded_source: str = ""
    network_has_unsaved_changes: bool = False
    is_loading_network: bool = False
    network_load_status: str = ""
    network_name: str = "Unnamed"
    network_file_path: str = ""
    save_network_folder: str = ""
    export_base_folder: str = str(Path.cwd() / "exports")
    export_message: str = ""
    export_error: str = ""
    is_network_name_dialog_open: bool = False
    is_load_dialog_open: bool = False
    is_export_dialog_open: bool = False
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
    is_network_data_dialog_open: bool = False
    network_data_active_component: str = "buses"
    network_data_tabs: list[NetworkDataTab] = []

    def load_default_model(self) -> None:
        """Reset catalog metadata to the empty PyPSA network defaults."""
        self.sections = model_sections(NETWORK_MODEL)
        self.loaded_source = ""
        self.network_has_unsaved_changes = False
        self.save_network_folder = ""
        self.other_csv_tables = {}
        self.time_series_tables = {}
        self.is_network_data_dialog_open = False
        self.network_data_tabs = []

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

    def open_other_component_dialog(self, title: str) -> None:
        """Open the placeholder dialog for an unsupported component."""
        component_name = str(title)
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

    def _sync_other_table_dialog(self) -> None:
        """Refresh editable supplemental CSV table dialog rows from state."""
        if self.time_series_dialog_key:
            table = self.time_series_tables.get(self.time_series_dialog_key)
            if table is None:
                return
            column = self.time_series_dialog_column
            self.other_table_dialog_columns = [column]
            rows: list[OtherTableRow] = []
            for row in table["rows"]:
                value = ""
                for cell in row["cells"]:
                    if cell["column"] == column:
                        value = cell["value"]
                        break
                rows.append(
                    {
                        "row_index": row["row_index"],
                        "id": row["id"],
                        "cells": [
                            {
                                "row_index": row["row_index"],
                                "column": column,
                                "value": value,
                            }
                        ],
                    }
                )
            self.other_table_dialog_rows = rows
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
        source_text = self.save_network_folder or self.loaded_source
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
                cells.append(
                    {
                        "component": component_name,
                        "row_id": node["id"],
                        "row_index": row_index,
                        "attr_name": attr_name,
                        "value": attrs.get(attr_name, attr.default),
                        "type": column["type"],
                        "input_type": column["input_type"],
                        "is_time_series": column["is_time_series"],
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
                cells.append(
                    {
                        "component": component_name,
                        "row_id": str(row["id"]),
                        "row_index": int(row["row_index"]),
                        "attr_name": attr_name,
                        "value": values_by_column.get(attr_name, ""),
                        "type": column["type"],
                        "input_type": column["input_type"],
                        "is_time_series": column["is_time_series"],
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
        """Refresh the whole-network data dialog tables from current state."""
        tabs: list[NetworkDataTab] = []
        for component_name, component in NETWORK_MODEL.all_components.items():
            if component_name in {"line_types", "transformer_types"}:
                continue
            columns = network_data_columns(component_name)
            rows = self._network_data_rows_for_component(component_name)
            tabs.append(
                {
                    "component": component_name,
                    "label": component.pypsa_name,
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
        if component_name in NETWORK_MODEL.all_components:
            self.network_data_active_component = component_name

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
        """Update a row name from the Network Data dialog."""
        component_name = str(component_name)
        new_name = str(value)
        if component_name not in NETWORK_MODEL.all_components:
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
        if component_name not in NETWORK_MODEL.all_components:
            return
        component = NETWORK_MODEL.component(component_name)
        attr = component.attrs.get(attr_name)
        if attr is None:
            return
        if is_canvas_data_component(component_name):
            for node in self.diagram_nodes:
                if node["id"] != str(row_id):
                    continue
                parsed_value = self._parse_attr_value(
                    value, attr.pypsa_type, attr.python_type
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
                return

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
            self._sync_network_data_dialog()
            return

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
            self._sync_network_data_dialog()

    def _open_time_series_table(
        self,
        component_name: str,
        attr_name: str,
        pypsa_name: str,
    ) -> None:
        """Open the editable time-series table for one component attr and row."""
        component_name = str(component_name)
        attr_name = str(attr_name)
        pypsa_name = str(pypsa_name)
        key = f"{component_name}:{attr_name}"
        table = self.time_series_tables.get(key)
        if table is None:
            table = {
                "component": key,
                "file_name": f"{component_name}-{attr_name}.csv",
                "columns": [pypsa_name],
                "rows": [],
                "index_name": "snapshot",
                "loaded": False,
                "dirty": False,
            }
            self.time_series_tables[key] = table
        if pypsa_name not in table["columns"]:
            table["columns"].append(pypsa_name)
            for row in table["rows"]:
                row["cells"].append(
                    {
                        "row_index": row["row_index"],
                        "column": pypsa_name,
                        "value": "",
                    }
                )
            table["dirty"] = True
            self._mark_network_dirty()
        self.other_component_dialog_title = (
            f"{component_name}.{attr_name} - {pypsa_name}"
        )
        self.other_component_dialog_kind = "csv_table"
        self.other_table_dialog_component = ""
        self.time_series_dialog_key = key
        self.time_series_dialog_column = pypsa_name
        self.other_table_error = ""
        self._sync_other_table_dialog()
        self.is_other_component_dialog_open = True

    def open_network_data_time_series_attr(
        self,
        component_name: str,
        row_id: str,
        row_index: int,
        attr_name: str,
    ) -> None:
        """Open a time-series table from a Network Data cell."""
        pypsa_name = self._row_name_for_network_data(
            str(component_name),
            str(row_id),
            int(row_index),
        )
        self.is_network_data_dialog_open = False
        self._open_time_series_table(str(component_name), str(attr_name), pypsa_name)

    def _canvas_snapshot(self) -> CanvasSnapshot:
        """Return a deep snapshot of undoable canvas state."""
        return {
            "diagram_nodes": copy.deepcopy(self.diagram_nodes),
            "component_counters": copy.deepcopy(self.component_counters),
            "route_version": self.route_version,
            "selected_node_id": self.selected_node_id,
            "armed_component": self.armed_component,
            "armed_branch_component": self.armed_branch_component,
            "pending_branch_node_id": self.pending_branch_node_id,
            "branch_bus0_node_id": self.branch_bus0_node_id,
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
        self.component_counters = copy.deepcopy(snapshot["component_counters"])
        self.route_version = int(snapshot["route_version"])
        self.armed_component = str(snapshot["armed_component"])
        self.armed_branch_component = str(snapshot["armed_branch_component"])
        self.pending_branch_node_id = str(snapshot["pending_branch_node_id"])
        self.branch_bus0_node_id = str(snapshot["branch_bus0_node_id"])
        self._sync_diagram_model()
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
                if (
                    self.time_series_dialog_column
                    and self.time_series_dialog_column not in table["columns"]
                ):
                    table["columns"].append(self.time_series_dialog_column)
                    for row in table["rows"]:
                        row["cells"].append(
                            {
                                "row_index": row["row_index"],
                                "column": self.time_series_dialog_column,
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
            loaded_network = load_pypsa_loaded_network(saved_path)
            self.sections = model_sections(NETWORK_MODEL, loaded_network)
            self.loaded_source = loaded_network.source or file_name
            self.other_csv_tables = {}
            self.time_series_tables = {}
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
            loaded_network = load_pypsa_loaded_network(csv_folder)
            self.sections = model_sections(NETWORK_MODEL, loaded_network)
            self.loaded_source = loaded_network.source or str(csv_folder)
            self.other_csv_tables = load_other_csv_tables(Path(csv_folder))
            self.time_series_tables = load_time_series_csv_tables(Path(csv_folder))
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
            network = load_pypsa_network(saved_path)
            loaded_network = load_pypsa_loaded_network(saved_path)
            self.sections = model_sections(NETWORK_MODEL, loaded_network)
            self.loaded_source = str(saved_path)
            self.save_network_folder = ""
            self.other_csv_tables = {}
            self.time_series_tables = {}
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

            network, loaded_network = await asyncio.to_thread(load_network_file, path)
            self.sections = model_sections(NETWORK_MODEL, loaded_network)
            self.loaded_source = str(path)
            self.save_network_folder = ""
            self.other_csv_tables = {}
            self.time_series_tables = {}
            self.network_name = str(network.name or path.stem or "Unnamed")
            self.operation_status = "Building canvas object..."
            self.network_load_status = self.operation_status
            yield

            self._populate_canvas_from_network(network, trigger_route=False)
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
        csv_folder = selected_directory.expanduser()
        self.is_loading_network = True
        self.is_load_dialog_open = False
        self.is_operation_dialog_open = True
        self.operation_title = "Loading network"
        self.operation_status = "Importing selected folder..."
        self.operation_kind = "load"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.network_load_status = self.operation_status
        self.export_message = ""
        self.export_error = ""
        yield

        self.operation_status = f"Importing PyPSA CSV folder {csv_folder}..."
        self.network_load_status = self.operation_status
        yield

        try:
            network, loaded_network = await asyncio.to_thread(
                load_csv_folder_network,
                csv_folder,
            )
        except Exception as exc:
            message = f"Could not import PyPSA CSV folder {csv_folder}: {exc}"
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

        self.sections = model_sections(NETWORK_MODEL, loaded_network)
        self.loaded_source = str(csv_folder)
        self.save_network_folder = str(csv_folder)
        self.other_csv_tables = load_other_csv_tables(csv_folder)
        self.time_series_tables = load_time_series_csv_tables(csv_folder)
        self.network_name = str(network.name or csv_folder.name)
        print(network)
        self.operation_status = "Building canvas object..."
        self.network_load_status = self.operation_status
        yield

        diagram_nodes, component_counters = await asyncio.to_thread(
            build_canvas_nodes_from_network,
            network,
        )
        layout_positions = await asyncio.to_thread(load_layout_positions, csv_folder)
        apply_layout_positions(diagram_nodes, layout_positions)
        self._apply_canvas_nodes(diagram_nodes, component_counters)
        if remember and is_pypsa_csv_folder(csv_folder):
            await asyncio.to_thread(write_last_network_folder, csv_folder)
        yield

        if not any(not node["hidden"] for node in self.diagram_nodes):
            self.operation_status = "Network loaded with no visible canvas components."
            self.load_message = f"Loaded {csv_folder} onto canvas."
            self.export_message = f"Loaded network folder {csv_folder} onto canvas."
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

        self.load_message = f"Loaded {csv_folder} onto canvas."
        self.export_message = f"Loaded network folder {csv_folder} onto canvas."
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
    ) -> None:
        """Assign prepared canvas nodes to state and rebuild derived data."""
        self.diagram_nodes = []
        self.diagram_edges = []
        self.diagram_model = {"components": [], "connections": []}
        self.network_component_rows = []
        self.network_connection_rows = []
        self.canvas_bus_names = []
        self.selected_node_id = ""
        self.selected_component_name = ""
        self.selected_attr_rows = []
        self.component_counters = {}
        self.armed_component = ""
        self.armed_branch_component = ""
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""
        if self.is_network_data_dialog_open:
            self._sync_network_data_dialog()
        self._clear_canvas_history()

        self.diagram_nodes = diagram_nodes
        self.component_counters = component_counters
        self._sync_diagram_model()
        self._mark_network_saved()

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
        if self.diagram_nodes:
            self._push_canvas_history()
        self.diagram_nodes = []
        self.diagram_edges = []
        self.diagram_model = {"components": [], "connections": []}
        self.network_component_rows = []
        self.network_connection_rows = []
        self.canvas_bus_names = []
        self.selected_node_id = ""
        self.selected_component_name = ""
        self.selected_attr_rows = []
        self.component_counters = {}
        self.armed_component = ""
        self.armed_branch_component = ""
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""

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
        self.other_csv_tables = {}
        self.time_series_tables = {}
        self.load_message = "Using empty PyPSA network defaults."
        self.load_error = ""
        self.export_message = ""
        self.export_error = ""
        self.network_has_unsaved_changes = False
        if self.is_network_data_dialog_open:
            self._sync_network_data_dialog()

    def reset_builder_on_load(self) -> None:
        """Reset transient builder state when the app page is loaded."""
        self.clear_canvas()
        self._clear_canvas_history()
        self.load_message = "Using empty PyPSA network defaults."
        self.load_error = ""
        self.loaded_source = ""
        self.network_has_unsaved_changes = False
        self.save_network_folder = ""
        self.other_csv_tables = {}
        self.time_series_tables = {}
        self.is_loading_network = False
        self.network_load_status = ""
        self.export_message = ""
        self.export_error = ""
        self.is_network_name_dialog_open = False
        self.is_load_dialog_open = False
        self.is_export_dialog_open = False
        self.is_operation_dialog_open = False
        self.operation_title = ""
        self.operation_status = ""
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        self.is_clear_canvas_dialog_open = False
        self.is_network_data_dialog_open = False
        self.network_data_tabs = []

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
        source_text = (self.save_network_folder or self.loaded_source).strip()
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

    def show_builder_view(self) -> None:
        """Show the schematic builder view."""
        self.active_view = "builder"

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
                    "component_x": 150,
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

    async def auto_route_canvas(self):
        """Route the canvas with the selected JavaScript or Python router."""
        if not any(not node["hidden"] for node in self.diagram_nodes):
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
            self._push_canvas_history()
            self._apply_routed_network(routed_network)
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

    async def choose_network_directory_and_load(self):
        """Open the web dialog for loading a local CSV folder path."""
        self.is_load_dialog_open = True
        yield

    def arm_branch_component(self, component_name: str) -> None:
        """Arm or disarm a branch component type for bus-to-bus creation."""
        component_name = str(component_name)
        if component_name not in NETWORK_MODEL.branch_components:
            return
        self.armed_component = ""
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
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""
        self.armed_component = (
            "" if self.armed_component == component_name else component_name
        )

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

    async def choose_export_folder(self):
        """Open the web dialog for setting the export destination path."""
        self.is_export_dialog_open = True
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
        """Save the current diagram model back to the loaded PyPSA CSV folder."""
        if not self.diagram_nodes:
            self.export_error = "Add at least one component before saving."
            self.export_message = ""
            yield
            return
        if not self.save_network_folder:
            self.export_error = "Load a PyPSA CSV folder before using Save network."
            self.export_message = ""
            yield
            return

        self.is_operation_dialog_open = True
        self.is_export_dialog_open = False
        self.operation_title = "Saving network"
        self.operation_status = (
            f"Writing PyPSA CSV files to {self.save_network_folder}..."
        )
        self.operation_kind = "save"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.export_message = ""
        self.export_error = ""
        yield

        try:
            extra_csv_tables = self._extra_csv_tables_for_export()
            export_path = await asyncio.to_thread(
                export_diagram_to_csv_folder,
                self.diagram_model,
                NETWORK_MODEL,
                self.save_network_folder,
                "",
                self.network_name,
                self.save_network_folder,
                extra_csv_tables,
            )
            self.loaded_source = str(export_path)
            self.save_network_folder = str(export_path)
            self._mark_network_saved()
            self.export_message = f"Saved network to {export_path}."
            self.export_error = ""
            self.is_operation_dialog_open = False
            self.operation_title = ""
            self.operation_status = ""
            self.operation_kind = ""
            self.operation_is_error = False
            self.operation_retry_load = False
            yield rx.toast.success(f"Saved PyPSA CSV folder to {export_path}.")
        except Exception as exc:
            self.export_error = f"Could not save network: {exc}"
            self.export_message = ""
            self.show_operation_error("Could not save network", self.export_error)
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
                export_diagram_to_csv_folder,
                self.diagram_model,
                NETWORK_MODEL,
                self.export_base_folder,
                "",
                self.network_name,
                self.save_network_folder or None,
                extra_csv_tables,
            )
            self.loaded_source = str(export_path)
            self.save_network_folder = str(export_path)
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
                            "x": bus_position["x"] - 120,
                            "y": bus_position["y"] + 8,
                        }
                    else:
                        node["position"] = {
                            "x": bus_position["x"] + 120,
                            "y": bus_position["y"] + 8,
                        }
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
            }
            for row in node["attr_rows"]
        ]

    def select_node(self, node_id: str) -> None:
        """Select a visible or hidden diagram node for editing."""
        self.selected_node_id = node_id
        for node in self.diagram_nodes:
            if node["id"] == node_id:
                self.selected_component_name = str(node["pypsa_name"])
                self.selected_attr_rows = self._selected_attr_rows_for_node(node)
                return
        self.selected_component_name = ""
        self.selected_attr_rows = []

    def delete_selected_node(self) -> None:
        """Delete the selected component and rebuild derived canvas data."""
        selected_node_id = str(self.selected_node_id)
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

    def open_selected_time_series_attr(self, attr_name: str) -> None:
        """Open the selected component column for a time-series attribute."""
        if not self.selected_node_id:
            return
        for node in self.diagram_nodes:
            if node["id"] != self.selected_node_id:
                continue
            component_name = str(node["component"])
            pypsa_name = str(node["attrs"].get("name") or node["id"])
            self._open_time_series_table(component_name, str(attr_name), pypsa_name)
            return

    def update_node_positions(self, updates: list[dict[str, object]]) -> None:
        """Persist dragged node positions and optional bus-drop connections."""
        original_snapshot = self._canvas_snapshot()
        positions = {
            str(update["id"]): update.get("position", {})
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
            bus_node_id = bus_targets.get(node["id"])
            if bus_node_id and "bus" in node["attrs"] and not node["attrs"].get("bus"):
                bus_name = self._bus_name_for_node_id(bus_node_id)
                if bus_name:
                    changed = True
                    node["attrs"]["bus"] = bus_name
                    bus_position = self._node_position(bus_node_id)
                    if bus_position:
                        if node["component"] == "generators":
                            node["position"] = {
                                "x": bus_position["x"] - 120,
                                "y": bus_position["y"] + 8,
                            }
                        else:
                            node["position"] = {
                                "x": bus_position["x"] + 120,
                                "y": bus_position["y"] + 8,
                            }
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
        self._sync_diagram_edges()
        components = [
            {
                "id": node["id"],
                "component": node["component"],
                "pypsa_name": node["pypsa_name"],
                "position": node["position"],
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
                "style": edge["style"],
                "attrs": edge["attrs"],
            }
            for edge in self.diagram_edges
        ]
        self.diagram_model = {
            "components": components,
            "connections": connections,
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
        if self.is_network_data_dialog_open:
            self._sync_network_data_dialog()

    def _sync_diagram_edges(self) -> None:
        """Regenerate React Flow edge data from node bus attributes."""
        bus_ids_by_name = {
            str(node["attrs"].get("name") or node["id"]): node["id"]
            for node in self.diagram_nodes
            if node["component"] == "buses"
        }
        edges: list[DiagramEdge] = []

        for node in self.diagram_nodes:
            component_name = node["component"]
            if component_name == "buses":
                continue

            attrs = node["attrs"]
            if component_name in NETWORK_MODEL.branch_components:
                bus0_id = bus_ids_by_name.get(str(attrs.get("bus0", "")))
                bus1_id = bus_ids_by_name.get(str(attrs.get("bus1", "")))
                if bus0_id and bus1_id and bus0_id != bus1_id:
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
        if "bool" in type_text:
            return bool(value)
        if "int" in type_text:
            try:
                return int(value)
            except TypeError, ValueError:
                return value
        if "float" in type_text:
            try:
                return float(value)
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


def index() -> rx.Component:
    """Render the application root page."""
    return rx.vstack(
        demo_styles(),
        rx.toast.provider(),
        operation_dialog(),
        clear_canvas_dialog(),
        network_name_dialog(),
        load_network_dialog(),
        export_network_dialog(),
        other_component_dialog(),
        network_data_dialog(),
        menu_bar(),
        rx.box(
            rx.cond(
                State.active_view == "debug-network",
                rx.box(
                    debug_network_tab(),
                    height="100%",
                    min_height="0",
                    overflow_y="auto",
                ),
                rx.cond(
                    State.active_view == "catalog",
                    rx.box(
                        catalog_tab(),
                        height="100%",
                        min_height="0",
                        overflow_y="auto",
                    ),
                    rx.box(
                        builder_tab(),
                        height="100%",
                        min_height="0",
                        display="flex",
                        flex_direction="column",
                        overflow="hidden",
                    ),
                ),
            ),
            flex="1",
            min_height="0",
            width="100%",
            padding="10px",
            overflow="hidden",
            class_name="app-content",
        ),
        footer_bar(),
        spacing="0",
        align="stretch",
        min_height="100vh",
        height="100vh",
        width="100%",
    )


app = rx.App()
app.add_page(
    index,
    route="/",
    title="PyPSA Network Builder",
    on_load=State.initialize_builder_on_load,
)
