"""Catalog and debug-network UI."""

import reflex as rx

from pypsa_studio.constants import FOLDER_UPLOAD_ID, UPLOAD_ID
from pypsa_studio.state import State
from pypsa_studio.types import (
    AttrRow,
    ComponentRow,
    NetworkObjectComponentRow,
    NetworkObjectConnectionRow,
)
from pypsa_studio.ui.scripts import directory_upload_script


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


def debug_network_tab() -> rx.Component:
    """Render the debug view for the in-memory network object."""
    return rx.vstack(
        rx.heading("Debug-Network", size="5"),
        network_object_view(),
        spacing="3",
        align="stretch",
        width="100%",
    )
