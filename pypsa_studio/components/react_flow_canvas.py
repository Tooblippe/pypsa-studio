"""Reflex wrapper for the demo React Flow canvas."""

from pathlib import Path
from typing import Any

import reflex as rx

CUSTOM_CODE_PARTS = (
    "index.jsx",
    "constants.jsx",
    "component_meta.jsx",
    "bus_routing.jsx",
    "edge_rendering.jsx",
    "node_rendering.jsx",
    "context_menu.jsx",
    "selection.jsx",
    "geometry.jsx",
    "regions.jsx",
    "canvas_inner.jsx",
)


class ReactFlowCanvas(rx.Component):
    """A small React Flow wrapper used by the demo schematic editor."""

    library = None
    tag = "ReactFlowCanvas"
    is_default = False
    lib_dependencies = ["reactflow", "elkjs"]

    nodes: rx.Var[list[dict[str, Any]]]
    edges: rx.Var[list[dict[str, Any]]]
    regions: rx.Var[list[dict[str, Any]]]
    route_version: rx.Var[int]
    fit_view_version: rx.Var[int]
    selected_node_id: rx.Var[str]
    armed_component: rx.Var[str]
    armed_branch_component: rx.Var[str]
    branch_bus0_node_id: rx.Var[str]
    rectangle_selection_armed: rx.Var[bool]

    on_node_drop: rx.EventHandler[lambda node: [node]]
    on_node_select: rx.EventHandler[lambda node_id: [node_id]]
    on_branch_bus_click: rx.EventHandler[lambda node_id: [node_id]]
    on_edge_select: rx.EventHandler[lambda node_id: [node_id]]
    on_edge_offset_update: rx.EventHandler[lambda payload: [payload]]
    on_nodes_update: rx.EventHandler[lambda nodes: [nodes]]
    on_route_complete: rx.EventHandler[lambda: []]
    on_canvas_context_menu_action: rx.EventHandler[lambda payload: [payload]]

    def _custom_code_part_paths(self) -> tuple[Path, ...]:
        """Return the ordered JSX partials used to build the inline component."""
        component_dir = Path(__file__).with_suffix("")
        return tuple(component_dir / part for part in CUSTOM_CODE_PARTS)

    def _get_custom_code(self) -> str:
        """Inline the JSX implementation so Reflex bundles it without an import path."""
        source = "\n\n".join(
            path.read_text(encoding="utf-8") for path in self._custom_code_part_paths()
        )
        return source.replace(
            "export function ReactFlowCanvas", "function ReactFlowCanvas"
        )


react_flow_canvas = ReactFlowCanvas.create
