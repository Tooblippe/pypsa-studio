"""Application page composition for PyPSA Studio."""

import reflex as rx

from pypsa_studio.state import State
from pypsa_studio.ui.builder import builder_tab
from pypsa_studio.ui.catalog import catalog_tab, debug_network_tab
from pypsa_studio.ui.dialogs import (
    carrier_visibility_dialog,
    clear_canvas_dialog,
    export_network_dialog,
    file_picker_dialog,
    file_picker_overwrite_dialog,
    load_network_dialog,
    mark_region_dialog,
    network_data_dialog,
    network_name_dialog,
    operation_dialog,
    other_component_dialog,
    settings_dialog,
    time_series_plot_dialog,
    unsaved_changes_dialog,
)
from pypsa_studio.ui.menus import footer_bar, menu_bar
from pypsa_studio.ui.styles import demo_styles


def index() -> rx.Component:
    """Render the application root page."""
    return rx.vstack(
        demo_styles(),
        rx.toast.provider(),
        operation_dialog(),
        carrier_visibility_dialog(),
        mark_region_dialog(),
        clear_canvas_dialog(),
        network_name_dialog(),
        unsaved_changes_dialog(),
        file_picker_dialog(),
        file_picker_overwrite_dialog(),
        load_network_dialog(),
        export_network_dialog(),
        other_component_dialog(),
        time_series_plot_dialog(),
        network_data_dialog(),
        settings_dialog(),
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
