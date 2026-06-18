"""Top menu and footer UI."""

from typing import Any

import reflex as rx

from pypsa_studio.state import State
from pypsa_studio.types import ExampleNetworkGroup, ExampleNetworkOption, RouterOption


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


def pypsa_example_menu_item(example: rx.Var[ExampleNetworkOption]) -> rx.Component:
    """Render one PyPSA example network submenu item."""
    return rx.menu.item(
        example["label"],
        on_select=lambda: State.request_load_pypsa_example_network(example["path"]),
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


def file_menu() -> rx.Component:
    """Render the top-level network file menu."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                "File",
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
                "New",
                on_select=State.request_new_network,
            ),
            rx.menu.item(
                "Rename",
                shortcut="Ctrl+N",
                on_select=State.open_network_name_dialog,
            ),
            rx.menu.separator(),
            rx.menu.item(
                "Load",
                shortcut="Ctrl+O",
                on_select=State.request_load_network_directory_to_canvas,
                disabled=State.is_loading_network,
            ),
            rx.menu.item(
                "Save",
                shortcut="Ctrl+S",
                on_select=State.save_canvas_network_to_loaded_folder,
                disabled=State.operation_kind == "save",
            ),
            rx.menu.item(
                "Save as",
                shortcut="Ctrl+E",
                on_select=State.choose_export_folder,
                disabled=State.operation_kind == "export",
            ),
            rx.menu.separator(),
            rx.menu.item(
                "Open in Jupyter",
                on_select=State.open_network_in_jupyter,
                disabled=State.operation_kind != "",
            ),
            rx.menu.sub(
                rx.menu.sub_trigger("Examples"),
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
            align="start",
            size="2",
            variant="soft",
        ),
    )


def sld_menu() -> rx.Component:
    """Render the top-level canvas menu."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                "SLD",
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


def network_data_menu() -> rx.Component:
    """Render the top-level data menu."""
    return rx.hstack(
        rx.menu.root(
            rx.menu.trigger(
                rx.button(
                    "Network Data",
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
        ),
        rx.tooltip(
            rx.button(
                rx.icon("recycle", size=18, color="#d8a200"),
                aria_label="Auto route",
                title="Auto route",
                on_click=State.auto_route_canvas,
                variant="ghost",
                size="1",
                padding="0px 6px",
                border_radius="9999px",
                margin_left="6px",
            ),
            content="Auto Route - Ctrl+R",
            side="bottom",
        ),
        spacing="2",
        align="center",
    )


def shortcut_actions() -> rx.Component:
    """Render hidden controls used by global keyboard shortcuts."""
    return rx.box(
        rx.button(
            "Rename",
            id="network-name-shortcut",
            on_click=State.open_network_name_dialog,
        ),
        rx.button(
            "Load",
            id="network-load-shortcut",
            on_click=State.request_load_network_directory_to_canvas,
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
        file_menu(),
        sld_menu(),
        # view_menu(),
        network_data_menu(),
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
        rx.tooltip(
            rx.box(
                width="10px",
                height="10px",
                border_radius="9999px",
                bg=rx.cond(
                    State.has_unsaved_network_changes,
                    "orange",
                    "green",
                ),
            ),
            content=rx.cond(
                State.has_unsaved_network_changes,
                "unsaved changes",
                "changes saved",
            ),
        ),
        rx.text(
            rx.cond(
                State.is_operation_dialog_open,
                State.operation_status,
                rx.cond(
                    State.has_unsaved_network_changes,
                    "unsaved changes",
                    "changes saved",
                ),
            ),
            size="2",
            color="#f8fafc",
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
