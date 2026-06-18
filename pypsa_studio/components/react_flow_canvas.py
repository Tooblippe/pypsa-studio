"""Reflex wrapper for the demo React Flow canvas."""

from pathlib import Path
from typing import Any

import reflex as rx


class ReactFlowCanvas(rx.Component):
    """A small React Flow wrapper used by the demo schematic editor."""

    library = None
    tag = "ReactFlowCanvas"
    is_default = False
    lib_dependencies = ["reactflow", "elkjs"]

    nodes: rx.Var[list[dict[str, Any]]]
    edges: rx.Var[list[dict[str, Any]]]
    route_version: rx.Var[int]
    fit_view_version: rx.Var[int]
    armed_component: rx.Var[str]
    armed_branch_component: rx.Var[str]
    branch_bus0_node_id: rx.Var[str]

    on_node_drop: rx.EventHandler[lambda node: [node]]
    on_node_select: rx.EventHandler[lambda node_id: [node_id]]
    on_branch_bus_click: rx.EventHandler[lambda node_id: [node_id]]
    on_edge_select: rx.EventHandler[lambda node_id: [node_id]]
    on_nodes_update: rx.EventHandler[lambda nodes: [nodes]]
    on_route_complete: rx.EventHandler[lambda: []]

    def _get_custom_code(self) -> str:
        """Inline the JSX implementation so Reflex bundles it without an import path."""
        component_path = Path(__file__).with_suffix(".jsx")
        source = component_path.read_text(encoding="utf-8")
        return source.replace(
            "export function ReactFlowCanvas", "function ReactFlowCanvas"
        )


react_flow_canvas = ReactFlowCanvas.create
