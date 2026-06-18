"""Shared constants for the PyPSA Studio app."""

from pathlib import Path

from pypsa_studio.network_model import build_network_model
from pypsa_studio.routers import discover_python_routers, router_options

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
TEST_NETWORKS_DIR = PROJECT_ROOT / "test_networks"
SUPPORTED_NETWORK_FILE_SUFFIXES = {".nc", ".h5", ".hdf5", ".zip"}
JUPYTER_ROOT_DIR = PROJECT_ROOT / ".jupyter"
JUPYTER_NOTEBOOKS_DIR = JUPYTER_ROOT_DIR / "notebooks"
JUPYTER_RUNTIME_DIR = JUPYTER_ROOT_DIR / "runtime"
JUPYTER_START_TIMEOUT_SECONDS = 30
JUPYTER_EXECUTION_TIMEOUT_SECONDS = 180
