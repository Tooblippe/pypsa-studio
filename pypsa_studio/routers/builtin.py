"""Built-in Python routers."""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

from pypsa_studio.routers.base import RouterBase, RouterNetwork


class GridRouter(RouterBase):
    """Deterministic Python router that groups components around their buses."""

    name = "python-grid"
    label = "Python grid"
    description = "Place buses in a row and connected components near their bus."

    def route(self, network: RouterNetwork) -> RouterNetwork:
        """Return the network with deterministic grid-based node positions."""
        routed = copy.deepcopy(network)
        nodes = routed.get("nodes", [])
        visible_nodes = [node for node in nodes if not node.get("hidden")]
        bus_nodes = [node for node in visible_nodes if node.get("component") == "buses"]
        bus_positions: dict[str, dict[str, float]] = {}

        for index, node in enumerate(bus_nodes):
            position = {"x": 180.0 + index * 220.0, "y": 160.0}
            node["position"] = position
            attrs = node.get("attrs", {})
            bus_name = (
                str(attrs.get("name") or node.get("id", ""))
                if isinstance(attrs, dict)
                else str(node.get("id", ""))
            )
            bus_positions[bus_name] = position

        offsets_by_bus_lane: dict[tuple[str, str], int] = defaultdict(int)
        unassigned_index = 0
        for node in visible_nodes:
            component_name = str(node.get("component", ""))
            if component_name == "buses":
                continue

            attrs = node.get("attrs", {})
            bus_name = str(attrs.get("bus", "")) if isinstance(attrs, dict) else ""
            bus_position = bus_positions.get(bus_name)
            if bus_position is None:
                node["position"] = {
                    "x": 180.0 + (unassigned_index % 5) * 180.0,
                    "y": 420.0 + (unassigned_index // 5) * 120.0,
                }
                unassigned_index += 1
                continue

            if component_name in {"stores", "storage_units"}:
                lane = "top"
            elif component_name in {"generators", "loads"}:
                lane = "bottom"
            else:
                lane = "side"

            offset_index = offsets_by_bus_lane[(bus_name, lane)]
            offsets_by_bus_lane[(bus_name, lane)] += 1
            row = offset_index // 3
            column = offset_index % 3
            x_offset = (column - 1) * 88.0
            bus_side = _node_bus_side(node)

            if lane == "top":
                x_offset = 70.0 + column * 64.0
                if bus_side == "left":
                    x_offset = -150.0 - column * 64.0
                elif bus_side == "right":
                    x_offset = 70.0 + column * 64.0
                node["position"] = {
                    "x": bus_position["x"] + x_offset,
                    "y": bus_position["y"] - 120.0 - row * 72.0,
                }
                continue

            if lane == "bottom":
                if component_name == "loads":
                    x_offset = 70.0 + column * 64.0
                if bus_side == "left":
                    x_offset = -150.0 - column * 64.0
                elif bus_side == "right":
                    x_offset = 70.0 + column * 64.0
                node["position"] = {
                    "x": bus_position["x"] + x_offset,
                    "y": bus_position["y"] + 120.0 + row * 72.0,
                }
                continue

            if bus_side == "left":
                x_position = bus_position["x"] - 150.0
            else:
                x_position = bus_position["x"] + 150.0
            node["position"] = {
                "x": x_position,
                "y": bus_position["y"] + x_offset,
            }

        routed["diagram_model"] = _diagram_model_from_nodes_and_edges(
            nodes,
            routed.get("edges", []),
        )
        return routed


def _diagram_model_from_nodes_and_edges(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a diagram model matching the app's existing shape."""
    return {
        "components": [
            {
                "id": node.get("id"),
                "component": node.get("component"),
                "pypsa_name": node.get("pypsa_name"),
                "position": node.get("position"),
                "layout": node.get("layout", {}),
                "attrs": node.get("attrs", {}),
                "hidden": node.get("hidden", False),
            }
            for node in nodes
        ],
        "connections": [
            {
                "id": edge.get("id"),
                "source": edge.get("source"),
                "target": edge.get("target"),
                "sourceHandle": edge.get("sourceHandle"),
                "targetHandle": edge.get("targetHandle"),
                "type": edge.get("type"),
                "label": edge.get("label"),
                "component": edge.get("component"),
                "style": edge.get("style", {}),
                "attrs": edge.get("attrs", {}),
            }
            for edge in edges
        ],
    }


def _node_bus_side(node: dict[str, Any]) -> str:
    """Return the saved bus side for a routed component node."""
    layout = node.get("layout", {})
    if not isinstance(layout, dict):
        return ""
    bus_side = str(layout.get("bus_side", "")).strip().lower()
    return bus_side if bus_side in {"left", "right"} else ""
