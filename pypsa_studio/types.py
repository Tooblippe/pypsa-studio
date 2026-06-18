"""Shared typed dictionary contracts for PyPSA Studio."""

from typing import TypedDict

import pypsa

from pypsa_studio.network_model import PypsaLoadedNetwork


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
    has_time_series_value: bool
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


class NetworkLoadArtifacts(TypedDict):
    network: pypsa.Network
    loaded_network: PypsaLoadedNetwork
    other_csv_tables: dict[str, OtherCsvTable]
    time_series_tables: dict[str, OtherCsvTable]


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
    has_time_series_value: bool
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
