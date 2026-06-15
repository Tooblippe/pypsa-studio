import asyncio
import json
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote

import reflex as rx
import pypsa

from pypsa_network_builder_v2.network_model import (
    ComponentType,
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


NETWORK_MODEL = build_network_model()
UPLOAD_ID = "pypsa-network-upload"
FOLDER_UPLOAD_ID = "pypsa-network-folder-upload"
BUILDER_LOAD_UPLOAD_ID = "pypsa-builder-load-upload"
BUILDER_LOAD_FOLDER_UPLOAD_ID = "pypsa-builder-load-folder-upload"
NETWORK_OBJECT_DISPLAY_LIMIT = 100


def load_csv_folder_network(csv_folder: Path) -> tuple[pypsa.Network, PypsaLoadedNetwork]:
    """Load a PyPSA CSV folder and derived metadata off the Reflex event loop."""
    network = pypsa.Network()
    network.import_from_csv_folder(csv_folder)
    loaded_network = pypsa_network_to_loaded_network(
        network,
        source=str(csv_folder),
    )
    return network, loaded_network


def choose_pypsa_csv_folder() -> str:
    """Open a native directory picker and return the selected folder path."""
    return choose_local_folder("Choose a PyPSA CSV folder")


def choose_export_folder() -> str:
    """Open a native directory picker and return an export base folder path."""
    return choose_local_folder("Choose an export destination folder")


def choose_local_folder(prompt: str) -> str:
    """Open a Tk native directory picker and return the selected folder path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError(
            "Tkinter is not available in this Python installation."
        ) from exc

    root = tk.Tk()
    root.withdraw()
    root.update()
    try:
        selected_folder = filedialog.askdirectory(
            parent=root,
            title=prompt,
            mustexist=True,
        )
        return str(selected_folder or "")
    finally:
        root.destroy()


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
    is_bus_reference: bool


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


def palette_groups() -> dict[str, list[ComponentRow]]:
    """Return the component groups shown in the builder palette."""
    return model_sections(NETWORK_MODEL)


def component_defaults(component: ComponentType) -> dict[str, object]:
    """Return default static attribute values for a component type."""
    return {
        attr_name: attr.default for attr_name, attr in component.attrs.items()
    }


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


def diagram_attr_rows(component: ComponentType, attrs: dict[str, object]) -> list[DiagramAttr]:
    """Build editable attribute rows for a diagram component."""
    rows: list[DiagramAttr] = []
    for attr_name, attr in component.attrs.items():
        pypsa_type = attr.pypsa_type or "any"
        rows.append(
            {
                "name": attr_name,
                "value": attrs.get(attr_name, attr.default),
                "type": pypsa_type,
                "input_type": attr_input_type(attr.pypsa_type, attr.python_type),
                "is_time_series": bool(attr.varying)
                or "series" in str(attr.pypsa_type).lower(),
                "is_bus_reference": is_bus_reference_attr(attr_name),
            }
        )
    return rows


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
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
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


def next_import_node_id(counters: dict[str, int], component_name: str) -> str:
    """Allocate the next stable imported node id for a component type."""
    next_count = counters.get(component_name, 0) + 1
    counters[component_name] = next_count
    singular = component_name[:-1] if component_name.endswith("s") else component_name
    return f"{singular}_{next_count}"


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
    """Render a draggable palette item for visible canvas components."""
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
            custom_attrs={"data-pypsa-component": component["component"]},
            width="32px",
            height="32px",
            padding="0",
            margin="0",
            border="0",
            border_radius="2px",
            cursor="grab",
            background="transparent",
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
            on_click=lambda: State.open_other_component_dialog(
                component["pypsa_name"]
            ),
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
    item_renderer = inert_palette_item if inert else branch_palette_item if branch else palette_item
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


def primary_palette_section() -> rx.Component:
    """Render bus, component, and branch icons as one compact palette group."""
    return rx.grid(
        rx.foreach(State.palette["fundamental"], palette_item),
        rx.foreach(State.palette["primary_components"], palette_item),
        rx.foreach(State.palette["primary_branch_components"], branch_palette_item),
        rx.foreach(State.palette["delayed_components"], palette_item),
        rx.foreach(State.palette["delayed_branch_components"], branch_palette_item),
        columns="3",
        spacing="1",
        width="108px",
        padding="5px",
        border="1px solid var(--gray-6)",
        border_radius="6px",
        background="color-mix(in srgb, var(--color-panel-solid) 66%, transparent)",
    )


def palette_sidebar() -> rx.Component:
    """Render the left component palette for the builder."""
    return rx.vstack(
        primary_palette_section(),
        palette_section("Other", State.palette["other"], columns="2", inert=True),
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
            justify="between",
            width="100%",
        ),
        rx.cond(
            attr["input_type"] == "boolean",
            rx.checkbox(
                checked=attr["value"].to(bool),
                on_change=lambda value: State.update_selected_attr(
                    attr["name"], value
                ),
            ),
            rx.cond(
                attr["is_bus_reference"],
                bus_attr_select(attr),
                rx.input(
                    value=attr["value"].to(str),
                    type=rx.cond(attr["input_type"] == "number", "number", "text"),
                    on_change=lambda value: State.update_selected_attr(
                        attr["name"], value
                    ),
                    width="100%",
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
        rx.heading("Selection", size="4"),
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
            rx.text("Select a node to edit its attributes.", size="2", color_scheme="gray"),
        ),
        spacing="4",
        align="stretch",
        width="300px",
        min_width="300px",
        height="100%",
        min_height="0",
        overflow_y="auto",
        padding="12px",
        border_left="1px solid var(--gray-5)",
        class_name="inspector-sidebar",
    )


def drag_payload_script() -> rx.Component:
    """Install browser drag payload handling for palette items."""
    return rx.script(
        """
        if (!window.__pypsaBuilderDragBound) {
          window.__pypsaBuilderDragBound = true;
          document.addEventListener("pointerdown", (event) => {
            const el = event.target.closest("[data-pypsa-component]");
            if (!el) return;
            window.__pypsaBuilderActiveComponent = el.dataset.pypsaComponent;
          }, true);
          document.addEventListener("dragstart", (event) => {
            const el = event.target.closest("[data-pypsa-component]");
            if (!el || !event.dataTransfer) return;
            window.__pypsaBuilderActiveComponent = el.dataset.pypsaComponent;
            event.dataTransfer.setData(
              "application/pypsa-component",
              JSON.stringify({ component: el.dataset.pypsaComponent })
            );
            event.dataTransfer.effectAllowed = "copy";
          }, true);
          document.addEventListener("dragend", () => {
            window.__pypsaBuilderActiveComponent = "";
          }, true);
        }
        """
    )


def directory_upload_script(upload_id: str) -> rx.Component:
    """Enable directory selection on a Reflex upload file input."""
    return rx.script(
        f"""
        setTimeout(() => {{
          const input = document.querySelector("#{upload_id} input[type='file']");
          if (input) {{
            input.setAttribute("webkitdirectory", "");
            input.setAttribute("directory", "");
            input.setAttribute("mozdirectory", "");
          }}
        }}, 0);
        """
    )


def builder_tab() -> rx.Component:
    """Render the main schematic builder tab."""
    return rx.vstack(
        drag_payload_script(),
        rx.hstack(
            palette_sidebar(),
            rx.vstack(
                rx.hstack(
                    rx.input(
                        value=State.network_name,
                        on_change=State.set_network_name,
                        placeholder="Network name",
                        width="220px",
                        class_name="network-name-input",
                    ),
                    rx.button(
                        "Auto route",
                        aria_label="Auto route network",
                        title="Auto route network",
                        on_click=State.auto_route_canvas,
                        variant="soft",
                    ),
                    builder_load_network_button(),
                    export_dialog(),
                    clear_canvas_dialog(),
                    justify="start",
                    align="center",
                    width="100%",
                    padding="8px",
                    border_bottom="1px solid var(--gray-5)",
                    class_name="builder-toolbar",
                ),
                rx.box(
                    react_flow_canvas(
                        nodes=State.diagram_nodes,
                        edges=State.diagram_edges,
                        route_version=State.route_version,
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
            right_sidebar(),
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


def builder_load_network_button() -> rx.Component:
    """Render the toolbar control for uploading a PyPSA CSV folder."""
    return rx.box(
        rx.upload(
            rx.button(
                rx.cond(State.is_loading_network, "Loading network...", "Load network"),
                aria_label="Load PyPSA network directory",
                title="Choose a PyPSA CSV folder",
                disabled=State.is_loading_network,
                variant="soft",
            ),
            id=BUILDER_LOAD_FOLDER_UPLOAD_ID,
            multiple=True,
            accept={"text/csv": [".csv"]},
            on_drop=State.load_network_folder_to_canvas(
                rx.upload_files(upload_id=BUILDER_LOAD_FOLDER_UPLOAD_ID)
            ),
            border="none",
            padding="0",
            width="fit-content",
        ),
        directory_upload_script(BUILDER_LOAD_FOLDER_UPLOAD_ID),
    )


def clear_canvas_dialog() -> rx.Component:
    """Render the confirmation dialog for clearing the canvas."""
    return rx.alert_dialog.root(
        rx.alert_dialog.trigger(
            rx.button(
                "Clear",
                aria_label="Clear canvas",
                title="Clear canvas",
                variant="soft",
                color_scheme="red",
            )
        ),
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
                        on_click=State.clear_canvas,
                        color_scheme="red",
                    )
                ),
                spacing="3",
                justify="end",
                width="100%",
            ),
            max_width="460px",
        ),
    )


def export_dialog() -> rx.Component:
    """Render the export-to-folder dialog."""
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                "Export to folder",
                aria_label="Export PyPSA network to folder",
                title="Export PyPSA network to folder",
                variant="soft",
            )
        ),
        rx.dialog.content(
            rx.dialog.title("Export PyPSA network"),
            rx.dialog.description(
                "Choose the folder where the PyPSA CSV files will be written.",
                size="2",
                color_scheme="gray",
            ),
            rx.vstack(
                rx.vstack(
                    rx.text("Destination folder", size="2", weight="medium"),
                    rx.hstack(
                        rx.input(
                            value=State.export_base_folder,
                            on_change=State.set_export_base_folder,
                            placeholder="/path/to/folder",
                            width="100%",
                        ),
                        rx.button(
                            "Select folder",
                            on_click=State.choose_export_folder,
                            variant="soft",
                            min_width="118px",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    spacing="1",
                    align="stretch",
                    width="100%",
                ),
                rx.cond(
                    State.export_error != "",
                    rx.text(State.export_error, size="2", color_scheme="red"),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", variant="soft", color_scheme="gray")
                    ),
                    rx.button(
                        "Export",
                        on_click=State.export_canvas_network,
                    ),
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
                width="100%",
            ),
            max_width="520px",
        ),
        open=State.is_export_dialog_open,
        on_open_change=State.set_export_dialog_open,
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
    return rx.html(
        """
        <style>
          html,
          body {
            background:
              radial-gradient(circle at 22% 0%, color-mix(in srgb, var(--accent-3) 26%, transparent) 0, transparent 34%),
              linear-gradient(180deg, var(--gray-2), var(--gray-1) 45%, var(--gray-2));
          }
          .app-menu,
          .app-footer {
            backdrop-filter: blur(14px);
            background: color-mix(in srgb, var(--color-panel-solid) 88%, transparent) !important;
          }
          .app-menu {
            box-shadow: 0 1px 0 color-mix(in srgb, var(--gray-8) 18%, transparent);
          }
          .brand-title {
            letter-spacing: 0;
          }
          .app-content {
            background: transparent;
          }
          .app-tabs [role="tablist"] {
            width: fit-content;
            margin-bottom: 8px;
            border: 1px solid var(--gray-5);
            border-radius: 8px;
            padding: 2px;
            background: color-mix(in srgb, var(--color-panel-solid) 78%, transparent);
            box-shadow: 0 8px 22px color-mix(in srgb, var(--gray-12) 7%, transparent);
          }
          .builder-shell {
            border-color: color-mix(in srgb, var(--gray-7) 72%, transparent) !important;
            border-radius: 10px !important;
            background: var(--color-panel-solid);
            box-shadow:
              0 18px 45px color-mix(in srgb, var(--gray-12) 10%, transparent),
              0 1px 0 color-mix(in srgb, white 55%, transparent) inset;
          }
          .builder-toolbar {
            min-height: 46px;
            background: linear-gradient(180deg, var(--gray-2), var(--color-panel-solid));
          }
          .network-name-input input {
            font-weight: 600;
          }
          .palette-sidebar,
          .inspector-sidebar {
            background: color-mix(in srgb, var(--gray-2) 72%, var(--color-panel-solid));
          }
          .palette-sidebar {
            padding: 6px !important;
          }
          .inspector-sidebar {
            padding: 14px !important;
          }
          .canvas-panel {
            background: var(--gray-1);
          }
          .react-flow-shell {
            width: 100%;
            height: 680px;
            background:
              linear-gradient(var(--gray-4) 1px, transparent 1px),
              linear-gradient(90deg, var(--gray-4) 1px, transparent 1px),
              radial-gradient(circle at 50% 0%, color-mix(in srgb, var(--accent-3) 22%, transparent), transparent 42%),
              var(--gray-1);
            background-size: 28px 28px, 28px 28px, 100% 100%, 100% 100%;
          }
          .schematic-node {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            width: 100%;
            height: 100%;
            border: 1px solid transparent;
            border-radius: 6px;
            background: transparent;
            cursor: grab;
            transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
          }
          .schematic-node[data-selected="true"] {
            border-color: var(--accent-9);
            background: color-mix(in srgb, var(--accent-3) 70%, transparent);
            box-shadow: 0 0 0 2px var(--accent-5), 0 10px 24px color-mix(in srgb, var(--accent-9) 20%, transparent);
          }
          .schematic-node:hover {
            border-color: var(--accent-9);
            background: color-mix(in srgb, var(--accent-3) 70%, transparent);
            box-shadow: 0 0 0 2px var(--accent-5);
            transform: translateY(-1px);
          }
          .schematic-node[data-branch-armed="true"] {
            border-color: var(--accent-7);
            background: color-mix(in srgb, var(--accent-2) 75%, transparent);
          }
          .schematic-node[data-branch-armed="true"]:hover {
            border-color: var(--accent-10);
            background: var(--accent-3);
            box-shadow: 0 0 0 3px var(--accent-5);
          }
          .schematic-node[data-branch-start="true"] {
            border-color: var(--green-9);
            background: var(--green-3);
            box-shadow: 0 0 0 3px var(--green-5);
          }
          .schematic-node[data-branch-connected="true"] {
            border-color: #facc15;
            background: #fef9c3;
            box-shadow: 0 0 0 3px #fde047;
          }
          .schematic-node[data-hover-connected="true"] {
            border-color: #facc15;
            background: #fef9c3;
            box-shadow: 0 0 0 3px #fde047;
          }
          .schematic-node[data-connection-target="available"] {
            border-color: var(--accent-7);
            background: color-mix(in srgb, var(--accent-2) 70%, transparent);
          }
          .schematic-node[data-connection-target="hover"] {
            border-color: var(--green-9);
            background: var(--green-3);
            box-shadow: 0 0 0 3px var(--green-5);
          }
          .schematic-node-symbol {
            display: block;
            width: 100%;
            height: calc(100% - 18px);
            min-height: 0;
          }
          .schematic-node-symbol svg {
            display: block;
            width: 100%;
            height: 100%;
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
        """
    )


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


def menu_bar() -> rx.Component:
    """Render the compact application menu bar."""
    return rx.hstack(
        rx.text("PyPSA Network Builder", weight="bold", size="3", class_name="brand-title"),
        rx.spacer(),
        rx.text(State.network_name, size="2", color_scheme="gray"),
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
    """Render the placeholder dialog for unsupported sidebar components."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(State.other_component_dialog_title),
            rx.dialog.description(
                "List manger to be added",
                size="2",
                color_scheme="gray",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("OK", on_click=State.close_other_component_dialog)
                ),
                justify="end",
                width="100%",
                margin_top="16px",
            ),
            max_width="360px",
        ),
        open=State.is_other_component_dialog_open,
        on_open_change=State.set_other_component_dialog_open,
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
        attr_name == "bus"
        or (attr_name.startswith("bus") and attr_name[3:].isdigit())
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
            component_to_row(component, loaded_network) for component in branch_components
        ],
        "other": [
            component_to_row(component, loaded_network) for component in other_components
        ],
    }


class State(rx.State):
    """Application state."""

    sections: dict[str, list[ComponentRow]] = model_sections(NETWORK_MODEL)
    palette: dict[str, list[ComponentRow]] = palette_groups()
    diagram_nodes: list[DiagramNode] = []
    diagram_edges: list[DiagramEdge] = []
    diagram_model: DiagramModel = {"components": [], "connections": []}
    network_component_rows: list[NetworkObjectComponentRow] = []
    network_connection_rows: list[NetworkObjectConnectionRow] = []
    canvas_bus_names: list[str] = []
    route_version: int = 0
    selected_node_id: str = ""
    selected_component_name: str = ""
    selected_attr_rows: list[DiagramAttr] = []
    component_counters: dict[str, int] = {}
    armed_branch_component: str = ""
    pending_branch_node_id: str = ""
    branch_bus0_node_id: str = ""
    load_message: str = "Using empty PyPSA network defaults."
    load_error: str = ""
    loaded_source: str = ""
    is_loading_network: bool = False
    network_load_status: str = ""
    network_name: str = "PyPSA Network"
    network_file_path: str = ""
    export_base_folder: str = str(Path.cwd() / "exports")
    export_message: str = ""
    export_error: str = ""
    is_export_dialog_open: bool = False
    is_operation_dialog_open: bool = False
    operation_title: str = ""
    operation_status: str = ""
    operation_kind: str = ""
    operation_is_error: bool = False
    operation_retry_load: bool = False
    is_other_component_dialog_open: bool = False
    other_component_dialog_title: str = ""

    def load_default_model(self) -> None:
        """Reset catalog metadata to the empty PyPSA network defaults."""
        self.sections = model_sections(NETWORK_MODEL)
        self.loaded_source = ""

    def open_other_component_dialog(self, title: str) -> None:
        """Open the placeholder dialog for an unsupported component."""
        self.other_component_dialog_title = str(title)
        self.is_other_component_dialog_open = True

    def close_other_component_dialog(self) -> None:
        """Close the placeholder dialog for unsupported components."""
        self.is_other_component_dialog_open = False

    def set_other_component_dialog_open(self, value: bool) -> None:
        """Update whether the unsupported component dialog is open."""
        self.is_other_component_dialog_open = value

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
            self.network_name = str(network.name or file_name)
            print(network)
            self._populate_canvas_from_network(network)
            self.load_message = f"Loaded {file_name} onto canvas."
            self.export_message = f"Loaded {file_name} onto canvas."
            self.load_error = ""
            self.export_error = ""
        except Exception as exc:
            self.export_error = f"Could not load network onto canvas: {exc}"
            self.export_message = ""

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
            async for _ in self._load_canvas_from_selected_network_directory(csv_folder):
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
            self.export_error = f"Could not load selected network folder onto canvas: {exc}"
            self.export_message = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error("Could not load network", self.export_error)
            yield

    async def _load_canvas_from_selected_network_directory(self, selected_directory: Path):
        """Load a selected CSV folder using Reflex yield updates."""
        csv_folder = selected_directory.expanduser()
        self.is_loading_network = True
        self.is_operation_dialog_open = True
        self.operation_title = "Loading network"
        self.operation_status = "Validating selected folder..."
        self.operation_kind = "load"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.network_load_status = self.operation_status
        self.export_message = ""
        self.export_error = ""
        yield

        if not is_valid_pypsa_csv_folder(csv_folder):
            message = (
                f"Selected folder is not a valid PyPSA CSV export folder: {csv_folder}. "
                "Choose a folder containing network.csv and component CSV files."
            )
            self.load_error = message
            self.export_error = message
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error(
                "Invalid network folder",
                message,
                retry_load=True,
            )
            yield
            return

        self.operation_status = f"Importing PyPSA CSV folder {csv_folder}..."
        self.network_load_status = self.operation_status
        yield

        network, loaded_network = await asyncio.to_thread(
            load_csv_folder_network,
            csv_folder,
        )

        self.sections = model_sections(NETWORK_MODEL, loaded_network)
        self.loaded_source = str(csv_folder)
        self.network_name = str(network.name or csv_folder.name)
        print(network)
        self.operation_status = "Building canvas object..."
        self.network_load_status = self.operation_status
        yield

        diagram_nodes, component_counters = await asyncio.to_thread(
            build_canvas_nodes_from_network,
            network,
        )
        self._apply_canvas_nodes(diagram_nodes, component_counters)
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

        self.operation_status = "Routing canvas..."
        self.network_load_status = self.operation_status
        self.route_version += 1
        yield

        self.load_message = f"Loaded {csv_folder} onto canvas."
        self.export_message = f"Loaded network folder {csv_folder} onto canvas."
        self.load_error = ""
        self.export_error = ""
        self.is_loading_network = False
        self.network_load_status = ""

    def add_diagram_node(self, payload: dict[str, object]) -> None:
        """Add a dropped palette component to the diagram."""
        component_name = str(payload.get("component", ""))
        bus_node_id = str(payload.get("bus_node_id", ""))
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
        self._add_diagram_node_at(str(component_name), float(x), float(y))

    def _populate_canvas_from_network(
        self,
        network: object,
        trigger_route: bool = True,
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
        self.armed_branch_component = ""
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""

        self.diagram_nodes = diagram_nodes
        self.component_counters = component_counters
        self._sync_diagram_model()

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
        singular = component_name[:-1] if component_name.endswith("s") else component_name
        return f"{singular}_{next_count}"

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
        self.armed_branch_component = ""
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""

    def reset_builder_on_load(self) -> None:
        """Reset transient builder state when the app page is loaded."""
        self.clear_canvas()
        self.load_message = "Using empty PyPSA network defaults."
        self.load_error = ""
        self.loaded_source = ""
        self.is_loading_network = False
        self.network_load_status = ""
        self.export_message = ""
        self.export_error = ""
        self.is_export_dialog_open = False
        self.is_operation_dialog_open = False
        self.operation_title = ""
        self.operation_status = ""
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False

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
            async for _ in self.choose_network_directory_and_load():
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

    async def auto_route_canvas(self):
        """Trigger one ELK auto-route pass in the React Flow canvas."""
        if not any(not node["hidden"] for node in self.diagram_nodes):
            self.export_error = "Add at least one component before routing."
            self.export_message = ""
            yield
            return

        self.is_operation_dialog_open = True
        self.operation_title = "Auto routing network"
        self.operation_status = "Running ELK orthogonal layout..."
        self.operation_kind = "route"
        self.operation_is_error = False
        self.operation_retry_load = False
        self.export_message = ""
        self.export_error = ""
        yield

        self.route_version += 1
        yield

    def finish_auto_route(self) -> None:
        """Close route-related progress dialogs after React Flow finishes."""
        if self.operation_kind not in {"route", "load"}:
            return
        completed_load = self.operation_kind == "load"
        self.operation_status = (
            "Network loaded and routed."
            if completed_load
            else "Auto routing completed."
        )
        self.is_operation_dialog_open = False
        self.operation_kind = ""
        self.operation_is_error = False
        self.operation_retry_load = False
        if not completed_load:
            self.export_message = "Auto routing completed."
        self.export_error = ""

    def set_network_name(self, value: str) -> None:
        """Update the PyPSA network name used for export."""
        self.network_name = value

    def set_network_file_path(self, value: str) -> None:
        """Store a user-entered network CSV folder path."""
        self.network_file_path = value

    async def choose_network_directory_and_load(self):
        """Open a native directory picker and load the selected CSV folder."""
        try:
            self.is_loading_network = True
            self.is_operation_dialog_open = True
            self.operation_title = "Loading network"
            self.operation_status = "Waiting for folder selection..."
            self.operation_kind = "load"
            self.operation_is_error = False
            self.operation_retry_load = False
            self.network_load_status = self.operation_status
            self.export_message = ""
            self.export_error = ""
            yield

            selected_directory = await asyncio.to_thread(choose_pypsa_csv_folder)

            if not selected_directory:
                self.is_loading_network = False
                self.is_operation_dialog_open = False
                self.operation_title = ""
                self.operation_status = ""
                self.operation_kind = ""
                self.operation_is_error = False
                self.operation_retry_load = False
                self.network_load_status = ""
                yield
                return

            self.network_file_path = selected_directory
            async for _ in self._load_canvas_from_selected_network_directory(
                Path(selected_directory)
            ):
                yield
        except Exception as exc:
            self.export_error = f"Could not choose and load network folder: {exc}"
            self.export_message = ""
            self.is_loading_network = False
            self.network_load_status = ""
            self.show_operation_error("Could not load network", self.export_error)
            yield

    def arm_branch_component(self, component_name: str) -> None:
        """Arm or disarm a branch component type for bus-to-bus creation."""
        component_name = str(component_name)
        if component_name not in NETWORK_MODEL.branch_components:
            return
        if self.armed_branch_component == component_name:
            self.armed_branch_component = ""
            self.pending_branch_node_id = ""
            self.branch_bus0_node_id = ""
            return
        self.armed_branch_component = component_name
        self.pending_branch_node_id = ""
        self.branch_bus0_node_id = ""

    def handle_branch_bus_click(self, node_id: str) -> None:
        """Advance the two-click branch creation workflow for a bus node."""
        if not self.armed_branch_component:
            self.select_node(node_id)
            return

        bus_name = self._bus_name_for_node_id(str(node_id))
        if not bus_name:
            return

        if not self.pending_branch_node_id:
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
            self.armed_branch_component = ""
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
        """Open a native folder picker and update the export destination."""
        try:
            self.is_operation_dialog_open = True
            self.operation_title = "Select export folder"
            self.operation_status = "Waiting for folder selection..."
            self.operation_kind = "export-picker"
            self.operation_is_error = False
            self.operation_retry_load = False
            self.export_error = ""
            yield

            selected_folder = await asyncio.to_thread(choose_export_folder)

            self.is_operation_dialog_open = False
            self.operation_title = ""
            self.operation_status = ""
            self.operation_kind = ""
            self.operation_is_error = False
            if selected_folder:
                self.export_base_folder = selected_folder
                self.export_message = f"Export destination set to {selected_folder}."
            yield
        except Exception as exc:
            self.export_error = f"Could not choose export folder: {exc}"
            self.export_message = ""
            self.show_operation_error("Could not choose export folder", self.export_error)
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
            export_path = await asyncio.to_thread(
                export_diagram_to_csv_folder,
                self.diagram_model,
                NETWORK_MODEL,
                self.export_base_folder,
                "",
                self.network_name,
            )
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
        if component_name != "buses" and not component.is_branch_component and not has_bus_attr(component):
            return
        if component_name in NETWORK_MODEL.branch_components:
            self.arm_branch_component(component_name)
            return

        next_count = self.component_counters.get(component_name, 0) + 1
        self.component_counters[component_name] = next_count
        singular = component_name[:-1] if component_name.endswith("s") else component_name
        node_id = f"{singular}_{next_count}"
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
        singular = component_name[:-1] if component_name.endswith("s") else component_name
        node_id = f"{singular}_{next_count}"
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

    def select_node(self, node_id: str) -> None:
        """Select a visible or hidden diagram node for editing."""
        self.selected_node_id = node_id
        for node in self.diagram_nodes:
            if node["id"] == node_id:
                self.selected_component_name = str(node["pypsa_name"])
                self.selected_attr_rows = node["attr_rows"]
                return
        self.selected_component_name = ""
        self.selected_attr_rows = []

    def update_node_positions(self, updates: list[dict[str, object]]) -> None:
        """Persist dragged node positions and optional bus-drop connections."""
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
        for node in self.diagram_nodes:
            position = positions.get(node["id"])
            if isinstance(position, dict):
                node["position"] = {
                    "x": float(position.get("x", node["position"]["x"])),
                    "y": float(position.get("y", node["position"]["y"])),
                }
            bus_node_id = bus_targets.get(node["id"])
            if bus_node_id and "bus" in node["attrs"] and not node["attrs"].get("bus"):
                bus_name = self._bus_name_for_node_id(bus_node_id)
                if bus_name:
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
                        self.selected_attr_rows = node["attr_rows"]
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
            parsed_value = self._parse_attr_value(value, attr.pypsa_type, attr.python_type)
            node["attrs"][str(attr_name)] = parsed_value
            node["attr_rows"] = diagram_attr_rows(component, node["attrs"])
            self.selected_attr_rows = node["attr_rows"]
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
            except (TypeError, ValueError):
                return value
        if "float" in type_text:
            try:
                return float(value)
            except (TypeError, ValueError):
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
        except (TypeError, ValueError):
            pass
        if hasattr(value, "item"):
            try:
                return value.item()
            except (TypeError, ValueError):
                pass
        return value


def index() -> rx.Component:
    """Render the application root page."""
    return rx.vstack(
        demo_styles(),
        rx.toast.provider(),
        operation_dialog(),
        other_component_dialog(),
        menu_bar(),
        rx.box(
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Builder", value="builder"),
                    rx.tabs.trigger("Debug-Network", value="debug-network"),
                    rx.tabs.trigger("Catalog", value="catalog"),
                    class_name="tab-list",
                ),
                rx.tabs.content(
                    builder_tab(),
                    value="builder",
                    flex="1",
                    min_height="0",
                    display="flex",
                    flex_direction="column",
                ),
                rx.tabs.content(debug_network_tab(), value="debug-network"),
                rx.tabs.content(catalog_tab(), value="catalog"),
                default_value="builder",
                width="100%",
                height="100%",
                display="flex",
                flex_direction="column",
                min_height="0",
                class_name="app-tabs",
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
    on_load=State.reset_builder_on_load,
)
