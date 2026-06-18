"""Builder canvas, palette, and inspector UI."""

import reflex as rx

from pypsa_studio.components import react_flow_canvas
from pypsa_studio.state import State
from pypsa_studio.types import ComponentRow, DiagramAttr
from pypsa_studio.ui.scripts import (
    canvas_shortcuts_script,
    drag_payload_script,
    inspector_resize_script,
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
            transition="background-color 140ms ease",
            _hover={
                "background": rx.cond(
                    State.armed_component == component["component"],
                    "var(--accent-3)",
                    "color-mix(in srgb, var(--yellow-6) 78%, transparent)",
                ),
            },
            display="flex",
            align_items="center",
            justify_content="center",
            class_name="sidebar-icon",
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
            transition="background-color 140ms ease",
            _hover={
                "background": "color-mix(in srgb, var(--yellow-6) 78%, transparent)",
            },
            display="flex",
            align_items="center",
            justify_content="center",
            class_name="sidebar-icon",
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
            transition="background-color 140ms ease",
            _hover={
                "background": rx.cond(
                    State.armed_branch_component == component["component"],
                    "var(--accent-3)",
                    "color-mix(in srgb, var(--yellow-6) 78%, transparent)",
                ),
            },
            display="flex",
            align_items="center",
            justify_content="center",
            class_name="sidebar-icon",
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
                class_name="sidebar-icon",
                transition="background-color 140ms ease",
                _hover={
                    "background": "color-mix(in srgb, var(--yellow-6) 78%, transparent)"
                },
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
                    rx.cond(
                        attr["has_time_series_value"],
                        rx.icon("table-2", size=14),
                        rx.text("+t", size="1", weight="bold"),
                    ),
                    aria_label=rx.cond(
                        attr["has_time_series_value"],
                        "Edit time series",
                        "Add time series",
                    ),
                    title=rx.cond(
                        attr["has_time_series_value"],
                        "Edit time series",
                        "Add time series",
                    ),
                    on_click=lambda: State.open_selected_time_series_attr(attr["name"]),
                    class_name="sidebar-icon",
                    transition="background-color 140ms ease",
                    _hover={
                        "background": "color-mix(in srgb, var(--yellow-6) 78%, transparent)"
                    },
                    variant="soft",
                    color_scheme=rx.cond(
                        attr["has_time_series_value"],
                        "green",
                        "blue",
                    ),
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
                    class_name="sidebar-icon",
                    transition="background-color 140ms ease",
                    _hover={
                        "background": "color-mix(in srgb, var(--yellow-6) 78%, transparent)"
                    },
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
                        fit_view_version=State.fit_view_version,
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
