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
                width="16px",
                height="16px",
                class_name="palette-symbol",
            ),
            aria_label=component["pypsa_name"],
            draggable=True,
            custom_attrs={
                "data-pypsa-component": component["component"],
                "data-pypsa-icon-src": component["icon_src"],
                "data-active": rx.cond(
                    State.armed_component == component["component"], "true", "false"
                ),
            },
            on_click=lambda: State.arm_canvas_component(component["component"]),
            width="32px",
            height="32px",
            padding="0",
            margin="0",
            cursor="grab",
            display="flex",
            align_items="center",
            justify_content="center",
            class_name="sidebar-icon palette-tool-button",
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
                width="16px",
                height="16px",
                opacity="0.55",
                class_name="palette-symbol",
            ),
            aria_label=component["pypsa_name"],
            on_click=lambda: State.open_other_component_dialog(component["component"]),
            width="32px",
            height="32px",
            padding="0",
            margin="0",
            cursor="pointer",
            display="flex",
            align_items="center",
            justify_content="center",
            class_name="sidebar-icon palette-tool-button",
            custom_attrs={"data-active": "false"},
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
                width="16px",
                height="16px",
                class_name="palette-symbol",
            ),
            aria_label=component["pypsa_name"],
            on_click=lambda: State.arm_branch_component(component["component"]),
            width="32px",
            height="32px",
            padding="0",
            margin="0",
            cursor="pointer",
            display="flex",
            align_items="center",
            justify_content="center",
            class_name="sidebar-icon palette-tool-button",
            custom_attrs={
                "data-active": rx.cond(
                    State.armed_branch_component == component["component"],
                    "true",
                    "false",
                )
            },
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
        rx.box(
            rx.grid(
                rx.foreach(components, item_renderer),
                gap="4px",
                grid_template_columns=f"repeat({columns}, 32px)",
                justify_content="center",
                width="fit-content",
            ),
            padding="4px",
            border="1px solid var(--gray-6)",
            border_radius="6px",
            background="color-mix(in srgb, var(--color-panel-solid) 66%, transparent)",
        ),
        spacing="1",
        align="center",
        width="88px",
    )


def bus_palette_section() -> rx.Component:
    """Render bus and bus-attached component icons."""
    return rx.vstack(
        rx.text("Bus", size="1", weight="medium", color_scheme="gray"),
        rx.vstack(
            rx.grid(
                rx.foreach(State.palette["fundamental"], palette_item),
            ),
            rx.grid(
                # rx.foreach(State.palette["fundamental"], palette_item),
                rx.foreach(State.palette["primary_components"], palette_item),
                rx.foreach(State.palette["delayed_components"], palette_item),
                gap="4px",
                grid_template_columns="repeat(2, 32px)",
                justify_content="center",
                width="fit-content",
            ),
            spacing="1",
            align="center",
            padding="4px",
            border="1px solid var(--gray-6)",
            border_radius="6px",
            background="color-mix(in srgb, var(--color-panel-solid) 66%, transparent)",
        ),
        spacing="1",
        align="center",
        width="88px",
    )


def branch_palette_section() -> rx.Component:
    """Render branch component icons."""
    return rx.vstack(
        rx.text("Branch", size="1", weight="medium", color_scheme="gray"),
        rx.box(
            rx.grid(
                rx.foreach(
                    State.palette["primary_branch_components"], branch_palette_item
                ),
                rx.foreach(
                    State.palette["delayed_branch_components"], branch_palette_item
                ),
                gap="4px",
                grid_template_columns="repeat(2, 32px)",
                justify_content="center",
                width="fit-content",
            ),
            padding="4px",
            border="1px solid var(--gray-6)",
            border_radius="6px",
            background="color-mix(in srgb, var(--color-panel-solid) 66%, transparent)",
        ),
        spacing="1",
        align="center",
        width="88px",
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
        width="96px",
        min_width="96px",
        height="100%",
        min_height="0",
        # overflow_y="auto",
        padding="4px",
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
            rx.heading("Component Data", size="4"),
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
            rx.fragment(),
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


def canvas_tool_button(
    icon: str,
    label: str,
    on_click: object,
    shortcut: str = "",
    color: str = "",
    disabled: object = False,
    element_id: str = "",
    active: object = False,
) -> rx.Component:
    """Render one consistently styled canvas toolbar icon button."""
    tooltip = f"{label} ({shortcut})" if shortcut else label
    custom_attrs = {"id": element_id} if element_id else {}
    custom_attrs["data-active"] = (
        "true"
        if active is True
        else "false" if active is False else rx.cond(active, "true", "false")
    )
    return rx.tooltip(
        rx.button(
            rx.icon(icon, size=17, color=color or "currentColor"),
            aria_label=label,
            on_click=on_click,
            disabled=disabled,
            variant="ghost",
            size="1",
            class_name="canvas-tool-button",
            custom_attrs=custom_attrs,
        ),
        content=tooltip,
        side="bottom",
    )


def canvas_tool_separator() -> rx.Component:
    """Render a slim visual divider between canvas toolbar controls."""
    return rx.box(class_name="canvas-tool-separator")


def canvas_toolbar() -> rx.Component:
    """Render the compact canvas tool row above the schematic canvas."""
    return rx.hstack(
        canvas_tool_button(
            icon="route",
            label="Auto route",
            shortcut="Ctrl+R",
            on_click=State.auto_route_canvas,
            color="#d8a200",
            element_id="canvas-auto-route-toolbar-button",
        ),
        canvas_tool_separator(),
        canvas_tool_button(
            icon="eye-off",
            label="Hide by carrier",
            on_click=State.open_carrier_visibility_dialog,
            color="#7c3aed",
            element_id="canvas-hide-by-carrier-toolbar-button",
        ),
        canvas_tool_button(
            icon="eye",
            label="Unhide all",
            on_click=State.unhide_all_canvas_components,
            color="#15803d",
            element_id="canvas-unhide-all-toolbar-button",
        ),
        canvas_tool_separator(),
        canvas_tool_button(
            icon="scan",
            label="Rectangle selection",
            on_click=State.toggle_rectangle_selection_armed,
            color="#2563eb",
            element_id="canvas-rectangle-selection-toolbar-button",
            active=State.rectangle_selection_armed,
        ),
        canvas_tool_separator(),
        canvas_tool_button(
            icon="lock",
            label="Lock all in place",
            on_click=State.lock_all_canvas_components,
            color="#b45309",
            element_id="canvas-lock-all-toolbar-button",
        ),
        canvas_tool_button(
            icon="lock_open",
            label="Unlock all",
            on_click=State.unlock_all_canvas_components,
            color="#64748b",
            element_id="canvas-unlock-all-toolbar-button",
        ),
        canvas_tool_separator(),
        canvas_tool_button(
            icon="undo-2",
            label="Undo",
            shortcut="Ctrl+Z",
            on_click=State.undo_canvas,
            color="#334155",
            disabled=rx.cond(State.can_undo_canvas, False, True),
        ),
        canvas_tool_button(
            icon="redo-2",
            label="Redo",
            shortcut="Ctrl+Shift+Z",
            on_click=State.redo_canvas,
            color="#334155",
            disabled=rx.cond(State.can_redo_canvas, False, True),
        ),
        canvas_tool_separator(),
        spacing="2",
        align="center",
        width="100%",
        class_name="canvas-toolbar",
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
                canvas_toolbar(),
                rx.box(
                    react_flow_canvas(
                        nodes=State.diagram_nodes,
                        edges=State.diagram_edges,
                        regions=State.canvas_regions,
                        route_version=State.route_version,
                        fit_view_version=State.fit_view_version,
                        selected_node_id=State.selected_node_id,
                        armed_component=State.armed_component,
                        armed_branch_component=State.armed_branch_component,
                        branch_bus0_node_id=State.branch_bus0_node_id,
                        rectangle_selection_armed=State.rectangle_selection_armed,
                        on_node_drop=State.add_diagram_node,
                        on_node_select=State.select_node,
                        on_branch_bus_click=State.handle_branch_bus_click,
                        on_edge_select=State.select_node,
                        on_edge_offset_update=State.update_edge_offset,
                        on_nodes_update=State.update_node_positions,
                        on_route_complete=State.finish_auto_route,
                        on_canvas_context_menu_action=(
                            State.handle_canvas_context_menu_action
                        ),
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
