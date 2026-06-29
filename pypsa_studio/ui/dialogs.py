"""Dialog and editable table UI."""

import reflex as rx

from pypsa_studio.constants import EDITABLE_CSV_UPLOAD_ID
from pypsa_studio.state import State
from pypsa_studio.types import (
    CarrierVisibilityRow,
    FilePickerEntry,
    NetworkDataCell,
    NetworkDataColumn,
    NetworkDataComponentSetting,
    NetworkDataRow,
    NetworkDataTab,
    OtherTableCell,
    OtherTableRow,
    SettingField,
    SettingsTab,
    StandardTypeRow,
)


def file_picker_root_button(entry: rx.Var[FilePickerEntry]) -> rx.Component:
    """Render one root shortcut in the file picker."""
    return rx.button(
        rx.cond(
            entry["icon"] == "home",
            rx.icon("home", size=14),
            rx.icon("hard-drive", size=14),
        ),
        entry["name"],
        variant="soft",
        size="2",
        on_click=lambda: State.navigate_file_picker_to_path(entry["path"]),
    )


def file_picker_entry_row(entry: rx.Var[FilePickerEntry]) -> rx.Component:
    """Render one file picker entry row."""
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.cond(
                    entry["kind"] == "folder",
                    rx.icon("folder", size=16),
                    rx.icon("file", size=16),
                ),
                rx.cond(
                    entry["kind"] == "folder",
                    rx.button(
                        entry["name"],
                        variant="ghost",
                        size="1",
                        on_click=lambda: State.navigate_file_picker_to_path(
                            entry["path"]
                        ),
                        padding="0",
                        height="auto",
                        font_weight="500",
                    ),
                    rx.text(entry["name"], size="2", weight="medium"),
                ),
                spacing="2",
                align="center",
            )
        ),
        rx.table.cell(rx.text(entry["modified"], size="1", color_scheme="gray")),
        rx.table.cell(rx.text(entry["size"], size="1", color_scheme="gray")),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    rx.icon("folder-open", size=14),
                    aria_label="Open folder",
                    title="Open folder",
                    size="1",
                    variant="soft",
                    disabled=entry["kind"] != "folder",
                    on_click=lambda: State.navigate_file_picker_to_path(entry["path"]),
                ),
                rx.button(
                    rx.icon("check", size=14),
                    aria_label="Select",
                    title="Select",
                    size="1",
                    variant="soft",
                    disabled=rx.cond(entry["selectable"], False, True),
                    on_click=lambda: State.select_file_picker_path(entry["path"]),
                ),
                spacing="1",
                justify="end",
            )
        ),
        background=rx.cond(
            State.file_picker_selected_path == entry["path"],
            "var(--accent-3)",
            "transparent",
        ),
    )


def file_picker_parent_row() -> rx.Component:
    """Render the parent directory navigation row."""
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.icon("folder-up", size=16),
                rx.button(
                    "...",
                    variant="ghost",
                    size="1",
                    on_click=State.navigate_file_picker_parent,
                    padding="0",
                    height="auto",
                    font_weight="500",
                ),
                spacing="2",
                align="center",
            )
        ),
        rx.table.cell(""),
        rx.table.cell(""),
        rx.table.cell(""),
    )


def file_picker_save_format_select() -> rx.Component:
    """Render the file picker save format selector."""
    return rx.select.root(
        rx.select.trigger(width="180px"),
        rx.select.content(
            rx.select.item("CSV folder", value="csv"),
            rx.select.item("NetCDF (.nc)", value="netcdf"),
            rx.select.item("HDF5 (.h5)", value="hdf5"),
        ),
        value=State.file_picker_save_format,
        on_change=State.set_file_picker_save_format,
        width="180px",
    )


def file_picker_dialog() -> rx.Component:
    """Render the server-side network file picker dialog."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.cond(
                        State.file_picker_mode == "load",
                        "Load network",
                        rx.cond(
                            State.file_picker_mode == "save",
                            "Save network",
                            "Save network as",
                        ),
                    )
                ),
                rx.hstack(
                    rx.foreach(State.file_picker_roots, file_picker_root_button),
                    spacing="2",
                    wrap="wrap",
                ),
                rx.hstack(
                    rx.button(
                        rx.icon("arrow-up", size=15),
                        aria_label="Parent folder",
                        title="Parent folder",
                        variant="soft",
                        size="2",
                        on_click=State.navigate_file_picker_parent,
                    ),
                    rx.input(
                        value=State.file_picker_path_input,
                        on_change=State.set_file_picker_path_input,
                        placeholder="Folder path",
                        width="100%",
                    ),
                    rx.button(
                        rx.icon("corner-down-right", size=15),
                        "Go",
                        variant="soft",
                        size="2",
                        on_click=State.navigate_file_picker_from_input,
                    ),
                    width="100%",
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    State.file_picker_mode != "load",
                    rx.vstack(
                        rx.hstack(
                            rx.text("Format", size="2", weight="medium"),
                            file_picker_save_format_select(),
                            rx.cond(
                                State.file_picker_save_format == "csv",
                                rx.text(
                                    "Select a folder to write CSV files into.",
                                    size="1",
                                    color_scheme="gray",
                                ),
                                rx.input(
                                    value=State.file_picker_target_name,
                                    on_change=State.set_file_picker_target_name,
                                    placeholder="File name",
                                    width="100%",
                                ),
                            ),
                            width="100%",
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.input(
                                value=State.file_picker_new_folder_name,
                                on_change=State.set_file_picker_new_folder_name,
                                placeholder="New folder name",
                                width="100%",
                            ),
                            rx.button(
                                rx.icon("folder-plus", size=15),
                                "Create",
                                variant="soft",
                                size="2",
                                on_click=State.create_file_picker_folder,
                            ),
                            width="100%",
                            spacing="2",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                rx.hstack(
                    rx.text(
                        rx.cond(
                            State.file_picker_selected_path != "",
                            State.file_picker_selected_path,
                            "No target selected",
                        ),
                        size="1",
                        color_scheme="gray",
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap",
                    ),
                    rx.spacer(),
                    rx.checkbox(
                        "Show hidden",
                        checked=State.file_picker_show_hidden,
                        on_change=State.set_file_picker_show_hidden,
                        size="2",
                    ),
                    width="100%",
                    align="center",
                ),
                rx.cond(
                    State.file_picker_error != "",
                    rx.hstack(
                        rx.icon("triangle-alert", size=14),
                        rx.text(State.file_picker_error, size="1"),
                        color="var(--red-11)",
                        background="var(--red-3)",
                        border="1px solid var(--red-6)",
                        border_radius="6px",
                        padding="8px",
                        width="100%",
                    ),
                ),
                rx.cond(
                    State.file_picker_warning != "",
                    rx.hstack(
                        rx.icon("info", size=14),
                        rx.text(State.file_picker_warning, size="1"),
                        color="var(--amber-11)",
                        background="var(--amber-3)",
                        border="1px solid var(--amber-6)",
                        border_radius="6px",
                        padding="8px",
                        width="100%",
                    ),
                ),
                rx.scroll_area(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Name"),
                                rx.table.column_header_cell("Modified"),
                                rx.table.column_header_cell("Size"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(
                            file_picker_parent_row(),
                            rx.foreach(
                                State.file_picker_entries,
                                file_picker_entry_row,
                            ),
                        ),
                        size="1",
                        variant="surface",
                        width="100%",
                    ),
                    height="360px",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button(
                        rx.cond(
                            State.file_picker_mode == "load",
                            "Load",
                            "Save",
                        ),
                        on_click=State.confirm_file_picker,
                        disabled=State.operation_kind != "",
                    ),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="820px",
        ),
        open=State.is_file_picker_open,
        on_open_change=State.set_file_picker_open,
    )


def file_picker_overwrite_dialog() -> rx.Component:
    """Render overwrite confirmation for file picker saves."""
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Overwrite existing network?"),
            rx.alert_dialog.description(
                "The selected save target already exists. Saving will replace PyPSA data at that location.",
                size="2",
                color_scheme="gray",
            ),
            rx.flex(
                rx.alert_dialog.cancel(
                    rx.button("Cancel", variant="soft", color_scheme="gray")
                ),
                rx.alert_dialog.action(
                    rx.button(
                        "Overwrite",
                        color_scheme="red",
                        on_click=State.confirm_file_picker_overwrite,
                    )
                ),
                spacing="3",
                justify="end",
                width="100%",
            ),
            max_width="460px",
        ),
        open=State.is_file_picker_overwrite_dialog_open,
        on_open_change=State.set_file_picker_overwrite_dialog_open,
    )


def load_network_dialog() -> rx.Component:
    """Render the controlled dialog for loading a local PyPSA CSV folder."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Load network"),
                rx.dialog.description(
                    "Enter a folder path on the machine running this app.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.input(
                    value=State.network_file_path,
                    on_change=State.set_network_file_path,
                    placeholder="PyPSA CSV folder path",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button(
                        rx.cond(State.is_loading_network, "Loading...", "Load"),
                        on_click=State.load_network_directory_path_to_canvas,
                        disabled=State.is_loading_network,
                    ),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="560px",
        ),
        open=State.is_load_dialog_open,
        on_open_change=State.set_load_dialog_open,
    )


def network_name_dialog() -> rx.Component:
    """Render the controlled dialog for setting the network name."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Set network name"),
                rx.dialog.description(
                    "Enter the name used for display and exports.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.input(
                    value=State.network_name,
                    on_change=State.set_network_name,
                    placeholder="Network name",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button("Done", on_click=State.close_network_name_dialog),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="460px",
        ),
        open=State.is_network_name_dialog_open,
        on_open_change=State.set_network_name_dialog_open,
    )


def unsaved_changes_dialog() -> rx.Component:
    """Render a confirmation dialog for actions with unsaved network changes."""
    return rx.alert_dialog.root(
        rx.alert_dialog.content(
            rx.alert_dialog.title("Unsaved changes"),
            rx.alert_dialog.description(
                "You have unsaved changes. Save first, ignore, or exit this action.",
                size="2",
                color_scheme="gray",
            ),
            rx.flex(
                rx.alert_dialog.cancel(
                    rx.button("Exit", variant="soft", color_scheme="gray")
                ),
                rx.alert_dialog.action(
                    rx.button(
                        "Ignore and open",
                        on_click=State.ignore_unsaved_network_changes_and_open,
                        color_scheme="orange",
                    )
                ),
                rx.alert_dialog.action(
                    rx.button(
                        "Save and open",
                        on_click=State.save_unsaved_network_changes_and_open,
                        color_scheme="blue",
                    )
                ),
                spacing="3",
                justify="end",
                width="100%",
            ),
            max_width="460px",
        ),
        open=State.is_unsaved_changes_dialog_open,
        on_open_change=State.set_unsaved_changes_dialog_open,
    )


def clear_canvas_dialog() -> rx.Component:
    """Render the confirmation dialog for clearing the canvas."""
    return rx.alert_dialog.root(
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
                        on_click=State.confirm_clear_canvas,
                        color_scheme="red",
                    )
                ),
                spacing="3",
                justify="end",
                width="100%",
            ),
            max_width="460px",
        ),
        open=State.is_clear_canvas_dialog_open,
        on_open_change=State.set_clear_canvas_dialog_open,
    )


def export_network_dialog() -> rx.Component:
    """Render the controlled dialog for exporting the network to a folder."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.cond(
                        State.is_export_dialog_for_save
                        & (State.save_network_folder == ""),
                        "Save network",
                        "Export network",
                    )
                ),
                rx.dialog.description(
                    rx.cond(
                        State.is_export_dialog_for_save
                        & (State.save_network_folder == ""),
                        "Choose a folder path on the machine running this app to save the loaded network.",
                        "Enter a destination folder path on the machine running this app.",
                    ),
                    size="2",
                    color_scheme="gray",
                ),
                rx.input(
                    value=State.export_base_folder,
                    on_change=State.set_export_base_folder,
                    placeholder="Export folder path",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button(
                        rx.cond(
                            State.is_export_dialog_for_save,
                            rx.cond(
                                State.operation_kind == "save", "Saving...", "Save"
                            ),
                            rx.cond(
                                State.operation_kind == "export",
                                "Exporting...",
                                "Export",
                            ),
                        ),
                        on_click=State.confirm_export_dialog,
                        disabled=rx.cond(
                            State.operation_kind == "export",
                            True,
                            State.operation_kind == "save",
                        ),
                    ),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="520px",
        ),
        open=State.is_export_dialog_open,
        on_open_change=State.set_export_dialog_open,
    )


def carrier_visibility_row(row: rx.Var[CarrierVisibilityRow]) -> rx.Component:
    """Render one carrier visibility checkbox row."""
    return rx.hstack(
        rx.checkbox(
            checked=row["checked"].to(bool),
            on_change=lambda value: State.set_canvas_carrier_visible(
                row["carrier"],
                value,
            ),
        ),
        rx.vstack(
            rx.text(row["label"], size="2", weight="medium"),
            rx.text(
                row["component_count"].to(str),
                " components",
                size="1",
                color_scheme="gray",
            ),
            spacing="0",
            align="start",
            min_width="0",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="8px 0",
        border_bottom="1px solid var(--gray-5)",
    )


def carrier_visibility_dialog() -> rx.Component:
    """Render the carrier-based canvas visibility dialog."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Hide by carrier"),
                rx.dialog.description(
                    "Uncheck carriers from the Carriers table to hide matching canvas components.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.cond(
                    State.carrier_visibility_rows.length() > 0,
                    rx.vstack(
                        rx.foreach(
                            State.carrier_visibility_rows,
                            carrier_visibility_row,
                        ),
                        spacing="0",
                        align="stretch",
                        width="100%",
                        max_height="360px",
                        overflow_y="auto",
                    ),
                    rx.text(
                        "No carrier rows are available in the Carriers table.",
                        size="2",
                        color_scheme="gray",
                    ),
                ),
                rx.flex(
                    rx.button(
                        "Unhide all",
                        on_click=State.unhide_all_canvas_components,
                        variant="soft",
                    ),
                    rx.dialog.close(rx.button("Done")),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="460px",
        ),
        open=State.is_carrier_visibility_dialog_open,
        on_open_change=State.set_carrier_visibility_dialog_open,
    )


def mark_region_dialog() -> rx.Component:
    """Render the naming dialog for rectangle-marked regions."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Mark region"),
                rx.dialog.description(
                    "Name this selected region. Components in the rectangle will be locked in place.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.input(
                    placeholder="Region name",
                    value=State.mark_region_name,
                    on_change=State.set_mark_region_name,
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(rx.button("Cancel", variant="soft")),
                    rx.button("Create", on_click=State.confirm_mark_region),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                align="stretch",
            ),
            max_width="420px",
        ),
        open=State.is_mark_region_dialog_open,
        on_open_change=State.set_mark_region_dialog_open,
    )


def network_data_tab_trigger(tab: rx.Var[NetworkDataTab]) -> rx.Component:
    """Render one Network Data component tab trigger."""
    return rx.tabs.trigger(
        rx.hstack(
            rx.text(tab["label"], size="2"),
            rx.badge(tab["row_count"].to(str), variant="soft", size="1"),
            spacing="1",
            align="center",
        ),
        value=tab["component"],
    )


def network_data_header_cell(column: rx.Var[NetworkDataColumn]) -> rx.Component:
    """Render one Network Data table header cell."""
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(
                column["name"],
                size="2",
                weight="medium",
                color=rx.cond(column["is_time_series"], "orange", "inherit"),
            ),
            rx.badge(column["type"], size="1", variant="soft"),
            rx.cond(
                column["is_time_series"],
                rx.button(
                    rx.icon("external-link", size=14),
                    aria_label="Open full time series table",
                    title="Open full time series table",
                    on_click=lambda: State.open_network_data_time_series_attr_table(
                        column["component"],
                        column["name"],
                    ),
                    variant="soft",
                    size="1",
                    flex_shrink="0",
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="center",
        ),
        padding="4px 6px",
        white_space="nowrap",
    )


def network_data_option_item(option: rx.Var[str]) -> rx.Component:
    """Render one Network Data select option."""
    return rx.select.item(option, value=option)


def network_data_column_filter(column: rx.Var[NetworkDataColumn]) -> rx.Component:
    """Render one Network Data text column filter."""
    return rx.input(
        value=column["filter_value"].to(str),
        placeholder=column["name"],
        on_change=lambda value: State.set_network_data_column_filter(
            column["name"],
            value,
        ),
        width="140px",
        height="28px",
        size="1",
        class_name="network-data-control",
    )


def network_data_page_size_select() -> rx.Component:
    """Render the Network Data page-size selector."""
    return rx.select.root(
        rx.select.trigger(width="80px", height="28px"),
        rx.select.content(
            rx.select.item("50", value="50"),
            rx.select.item("100", value="100"),
            rx.select.item("250", value="250"),
            rx.select.item("500", value="500"),
        ),
        value=State.network_data_page_size.to(str),
        on_change=State.set_network_data_page_size,
    )


def network_data_table_controls(tab: rx.Var[NetworkDataTab]) -> rx.Component:
    """Render Network Data paging and filter controls."""
    return rx.vstack(
        rx.hstack(
            rx.input(
                value=State.network_data_row_query,
                placeholder="Search names",
                on_change=State.set_network_data_row_query,
                width="220px",
                height="28px",
                size="1",
                class_name="network-data-control",
            ),
            rx.text("Rows", size="1", color_scheme="gray"),
            network_data_page_size_select(),
            rx.spacer(),
            rx.text(
                tab["page_start"].to(str),
                "-",
                tab["page_end"].to(str),
                " of ",
                tab["filtered_row_count"].to(str),
                size="1",
                color_scheme="gray",
                white_space="nowrap",
            ),
            rx.button(
                rx.icon("chevron-left", size=14),
                aria_label="Previous page",
                title="Previous page",
                on_click=State.previous_network_data_page,
                disabled=tab["page_index"] <= 0,
                variant="soft",
                size="1",
            ),
            rx.button(
                rx.icon("chevron-right", size=14),
                aria_label="Next page",
                title="Next page",
                on_click=State.next_network_data_page,
                disabled=tab["page_index"] >= tab["page_count"] - 1,
                variant="soft",
                size="1",
            ),
            rx.button(
                "Clear",
                on_click=State.clear_network_data_filters,
                variant="ghost",
                size="1",
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        rx.box(
            rx.hstack(
                rx.foreach(tab["columns"], network_data_column_filter),
                spacing="2",
                align="center",
                width="max-content",
            ),
            width="100%",
            overflow_x="auto",
            padding_bottom="2px",
        ),
        spacing="2",
        align="stretch",
        width="100%",
        flex_shrink="0",
    )


def network_data_bus_select(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render a bus reference selector in the Network Data grid."""
    return rx.select.root(
        rx.select.trigger(
            placeholder="Select bus",
            width="100%",
            height="28px",
            class_name="network-data-control",
        ),
        rx.select.content(
            rx.select.group(
                rx.foreach(State.canvas_bus_names, network_data_option_item),
            ),
        ),
        value=cell["value"].to(str),
        on_change=lambda value: State.update_network_data_cell(
            cell["component"],
            cell["row_id"],
            cell["row_index"],
            cell["attr_name"],
            value,
        ),
        width="100%",
    )


def network_data_option_select(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render an option selector in the Network Data grid."""
    return rx.select.root(
        rx.select.trigger(
            placeholder="Select value",
            width="100%",
            height="28px",
            class_name="network-data-control",
        ),
        rx.select.content(
            rx.select.group(
                rx.foreach(cell["options"], network_data_option_item),
            ),
        ),
        value=cell["value"].to(str),
        on_change=lambda value: State.update_network_data_cell(
            cell["component"],
            cell["row_id"],
            cell["row_index"],
            cell["attr_name"],
            value,
        ),
        width="100%",
    )


def network_data_text_input(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render a text/number input in the Network Data grid."""
    return rx.input(
        value=cell["display_value"].to(str),
        type="text",
        on_change=lambda value: State.update_network_data_cell(
            cell["component"],
            cell["row_id"],
            cell["row_index"],
            cell["attr_name"],
            value,
        ),
        on_blur=lambda value: State.commit_network_data_reference(
            cell["component"],
            cell["attr_name"],
            value,
        ),
        width="100%",
        height="28px",
        size="2",
        class_name=rx.cond(
            cell["input_type"] == "number",
            "network-data-control network-data-number",
            "network-data-control",
        ),
    )


def network_data_cell_control(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render the appropriate Network Data cell editor."""
    return rx.cond(
        cell["input_type"] == "boolean",
        rx.checkbox(
            checked=cell["value"].to(bool),
            on_change=lambda value: State.update_network_data_cell(
                cell["component"],
                cell["row_id"],
                cell["row_index"],
                cell["attr_name"],
                value,
            ),
        ),
        rx.cond(
            cell["is_bus_reference"],
            network_data_bus_select(cell),
            rx.cond(
                cell["input_type"] == "select",
                network_data_option_select(cell),
                network_data_text_input(cell),
            ),
        ),
    )


def network_data_cell(cell: rx.Var[NetworkDataCell]) -> rx.Component:
    """Render one editable Network Data table cell."""
    return rx.table.cell(
        rx.hstack(
            network_data_cell_control(cell),
            rx.cond(
                cell["is_time_series"],
                rx.button(
                    rx.cond(
                        cell["has_time_series_value"],
                        rx.icon("table-2", size=14),
                        rx.text("+t", size="1", weight="bold"),
                    ),
                    aria_label=rx.cond(
                        cell["has_time_series_value"],
                        "Edit time series",
                        "Add time series",
                    ),
                    title=rx.cond(
                        cell["has_time_series_value"],
                        "Edit time series",
                        "Add time series",
                    ),
                    on_click=lambda: State.open_network_data_time_series_attr(
                        cell["component"],
                        cell["row_id"],
                        cell["row_index"],
                        cell["attr_name"],
                    ),
                    variant="soft",
                    color_scheme=rx.cond(
                        cell["has_time_series_value"],
                        "green",
                        "blue",
                    ),
                    size="1",
                    height="24px",
                    flex_shrink="0",
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="center",
            width="100%",
        ),
        padding="4px 6px",
    )


def network_data_row(row: rx.Var[NetworkDataRow]) -> rx.Component:
    """Render one Network Data table row."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.input(
                value=row["name"],
                placeholder="name",
                on_change=lambda value: State.update_network_data_row_name(
                    row["component"],
                    row["row_id"],
                    row["row_index"],
                    value,
                ),
                width="100%",
                height="28px",
                size="2",
                class_name="network-data-control",
            ),
            padding="4px 6px",
            position="sticky",
            left="0",
            background="var(--color-panel-solid)",
            z_index="1",
        ),
        rx.foreach(row["cells"], network_data_cell),
    )


def network_data_table(tab: rx.Var[NetworkDataTab]) -> rx.Component:
    """Render one Network Data component table."""
    return rx.vstack(
        network_data_table_controls(tab),
        rx.cond(
            tab["row_count"] == 0,
            rx.text(
                "No rows for this component.",
                size="2",
                color_scheme="gray",
            ),
            rx.fragment(),
        ),
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell(
                            "Name",
                            position="sticky",
                            left="0",
                            background="var(--color-panel-solid)",
                            z_index="2",
                            padding="4px 6px",
                        ),
                        rx.foreach(tab["columns"], network_data_header_cell),
                    ),
                ),
                rx.table.body(rx.foreach(tab["rows"], network_data_row)),
                variant="surface",
                size="1",
                width="max-content",
                min_width="max-content",
                class_name="network-data-grid",
            ),
            flex="1",
            min_height="0",
            height="100%",
            max_width="100%",
            overflow_x="auto",
            overflow_y="auto",
        ),
        spacing="0",
        align="stretch",
        width="100%",
        height="100%",
        min_height="0",
        flex="1",
    )


def network_data_tab_content(tab: rx.Var[NetworkDataTab]) -> rx.Component:
    """Render one Network Data tab content panel."""
    return rx.tabs.content(
        network_data_table(tab),
        value=tab["component"],
        width="100%",
        height="100%",
        min_height="0",
        flex="1",
        overflow="hidden",
    )


def network_data_tabs() -> rx.Component:
    """Render the editable whole-network data tabs."""
    return rx.tabs.root(
        rx.tabs.list(
            rx.foreach(State.network_data_tabs, network_data_tab_trigger),
            overflow_x="auto",
            width="100%",
            flex_wrap="nowrap",
            flex_shrink="0",
        ),
        rx.foreach(State.network_data_tabs, network_data_tab_content),
        value=State.network_data_active_component,
        on_change=State.set_network_data_active_component,
        width="100%",
        height="100%",
        min_height="0",
        flex="1",
        display="flex",
        flex_direction="column",
    )


def network_data_view() -> rx.Component:
    """Render the full-page editable Network Data view."""
    return rx.vstack(
        rx.hstack(
            rx.spacer(),
            rx.button(
                rx.icon("workflow", size=15),
                "Canvas",
                on_click=State.show_canvas_view,
                variant="soft",
                size="2",
            ),
            width="100%",
            align="center",
            flex_shrink="0",
        ),
        network_data_tabs(),
        spacing="2",
        align="stretch",
        width="100%",
        height="100%",
        min_height="0",
        overflow="hidden",
        background="var(--color-panel-solid)",
    )


def network_data_dialog() -> rx.Component:
    """Render the editable whole-network data dialog."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.dialog.title("Network Data"),
                rx.dialog.close(
                    rx.button(
                        rx.icon("x", size=16),
                        aria_label="Close network data",
                        title="Close",
                        variant="ghost",
                        size="2",
                    )
                ),
                justify="between",
                align="center",
                width="100%",
            ),
            network_data_tabs(),
            width="96vw",
            max_width="1800px",
        ),
        open=State.is_network_data_dialog_open,
        on_open_change=State.set_network_data_dialog_open,
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
    return rx.html("""
        <style>
          html,
          body {
            background:
              radial-gradient(circle at 22% 0%, color-mix(in srgb, var(--accent-3) 22%, transparent) 0, transparent 34%),
              linear-gradient(180deg, var(--gray-4), var(--gray-3) 45%, var(--gray-4));
          }
          .app-menu,
          .app-footer {
            backdrop-filter: blur(14px);
            background: #1f4e5f !important;
            color: #f8fafc;
          }
          .app-menu {
            box-shadow: 0 1px 0 color-mix(in srgb, #0f2f3a 48%, transparent);
          }
          .app-menu :where(button, a, [role="button"]),
          .app-footer :where(button, a, [role="button"]) {
            color: #f8fafc;
          }
          .app-content {
            background: var(--gray-4);
          }
          .builder-shell {
            border-color: color-mix(in srgb, var(--gray-7) 72%, transparent) !important;
            border-radius: 10px !important;
            background: var(--gray-3);
            box-shadow:
              0 18px 45px color-mix(in srgb, var(--gray-12) 10%, transparent),
              0 1px 0 color-mix(in srgb, white 55%, transparent) inset;
          }
          .builder-toolbar {
            min-height: 46px;
            background: linear-gradient(180deg, var(--gray-4), var(--gray-3));
          }
          .palette-sidebar,
          .inspector-sidebar {
            background: var(--gray-4);
          }
          .palette-sidebar {
            padding: 4px !important;
          }
          .inspector-sidebar {
            padding: 14px !important;
          }
          .inspector-resize-handle {
            background: color-mix(in srgb, var(--gray-6) 42%, transparent);
            border-left: 1px solid color-mix(in srgb, var(--gray-7) 60%, transparent);
            border-right: 1px solid color-mix(in srgb, var(--gray-7) 60%, transparent);
            transition: background 120ms ease;
          }
          .inspector-resize-handle:hover {
            background: var(--accent-6);
          }
          .canvas-panel {
            background: var(--gray-3);
          }
          .react-flow-shell {
            position: relative;
            width: 100%;
            height: 100%;
            min-height: 0;
            background:
              linear-gradient(var(--gray-4) 1px, transparent 1px),
              linear-gradient(90deg, var(--gray-4) 1px, transparent 1px),
              radial-gradient(circle at 50% 0%, color-mix(in srgb, var(--accent-3) 22%, transparent), transparent 42%),
              var(--gray-3);
            background-size: 28px 28px, 28px 28px, 100% 100%, 100% 100%;
          }
          .schematic-node {
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            gap: 3px;
            width: 100%;
            height: 100%;
            border: 1px solid transparent;
            border-radius: 6px;
            background: transparent;
            cursor: grab;
            overflow: visible;
            transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
          }
          .schematic-node[data-selected="true"] {
            border-color: var(--accent-9);
            background: color-mix(in srgb, var(--accent-3) 70%, transparent);
            box-shadow: 0 0 0 2px var(--accent-5), 0 10px 24px color-mix(in srgb, var(--accent-9) 20%, transparent);
          }
          .schematic-node:hover {
            border-color: #2563eb;
            background: #dbeafe;
            box-shadow: 0 0 0 3px color-mix(in srgb, #60a5fa 58%, transparent);
            transform: translateY(-1px);
          }
          .schematic-node[data-is-bus="true"]:hover {
            transform: none;
          }
          .schematic-node[data-is-bus="true"] {
            justify-content: flex-start;
          }
          .schematic-node[data-branch-armed="true"] {
            cursor: crosshair;
          }
          .schematic-node[data-connection-hover="true"] {
            border-color: transparent;
            background: transparent;
            box-shadow: none;
            transform: none;
          }
          .schematic-node[data-connection-hover="true"] .schematic-bus-symbol {
            background: #2563eb;
            box-shadow: 0 0 0 4px color-mix(in srgb, #60a5fa 72%, transparent);
          }
          .react-flow-shell[data-branch-armed="true"] .schematic-node[data-is-bus="true"]:hover {
            border-color: transparent;
            background: transparent;
            box-shadow: none;
            transform: none;
          }
          .react-flow-shell[data-branch-armed="true"] .schematic-node[data-is-bus="true"]:hover .schematic-bus-symbol {
            background: #2563eb;
            box-shadow: 0 0 0 4px color-mix(in srgb, #60a5fa 72%, transparent);
          }
          .schematic-node[data-branch-start="true"],
          .schematic-node[data-branch-start="true"]:hover {
            border-color: transparent;
            background: transparent;
            box-shadow: none;
            transform: none;
          }
          .schematic-node[data-branch-start="true"] .schematic-bus-symbol {
            background: var(--green-9);
            box-shadow: 0 0 0 4px var(--green-5);
          }
          .react-flow-shell[data-armed-component="true"] {
            cursor: crosshair;
          }
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge,
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge-path,
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge-interaction,
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge-textwrapper {
            pointer-events: none;
          }
          .schematic-symbol-layer {
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
            transform-origin: center;
            transition: transform 120ms ease;
          }
          .schematic-node-symbol {
            display: block;
            width: 100%;
            flex: 0 0 auto;
            min-height: 0;
          }
          .schematic-bus-symbol {
            display: block;
            width: 3px;
            min-height: 72px;
            border-radius: 999px;
            background: var(--gray-12);
            flex: 0 0 auto;
          }
          .schematic-terminal {
            position: absolute;
            z-index: 2;
            width: 13px;
            height: 2px;
            background: var(--gray-12);
            pointer-events: none;
            transform: translateY(-50%);
          }
          .schematic-terminal::after {
            content: "";
            position: absolute;
            top: 50%;
            width: 6px;
            height: 6px;
            border-radius: 999px;
            background: var(--gray-12);
            transform: translate(-50%, -50%);
          }
          .schematic-terminal-left {
            left: 0;
          }
          .schematic-terminal-left::after {
            left: 0;
          }
          .schematic-terminal-right {
            right: 0;
          }
          .schematic-terminal-right::after {
            left: 100%;
          }
          .schematic-node-symbol {
            display: block;
            flex: 0 0 auto;
          }
          .schematic-node-symbol svg {
            display: block;
            width: 100%;
            height: 100%;
            overflow: visible;
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
          .schematic-edge-label {
            position: absolute;
            z-index: 5;
            padding: 2px 5px;
            border-radius: 4px;
            background: var(--color-panel-solid);
            color: var(--gray-12);
            font-size: 10px;
            line-height: 14px;
            white-space: nowrap;
            pointer-events: none;
            transform-origin: center;
            box-shadow: 0 1px 3px color-mix(in srgb, var(--gray-12) 10%, transparent);
          }
          .schematic-edge-label[data-selected="true"] {
            outline: 1px solid var(--accent-8);
          }
          .schematic-edge-symbol {
            position: absolute;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            z-index: 4;
            box-sizing: content-box;
            width: var(--edge-symbol-size);
            height: var(--edge-symbol-size);
            padding: 3px;
            border-radius: 4px;
            background: transparent;
            color: var(--gray-12);
            pointer-events: none;
            transform-origin: center;
          }
          .schematic-edge-symbol img {
            flex: 0 0 auto;
            display: block;
            width: var(--edge-symbol-size) !important;
            height: var(--edge-symbol-size) !important;
            max-width: var(--edge-symbol-size) !important;
            max-height: var(--edge-symbol-size) !important;
            object-fit: contain;
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
        """)


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


def time_series_plot_controls() -> rx.Component:
    """Render plotting controls for the open time-series table."""
    return rx.hstack(
        rx.segmented_control.root(
            rx.segmented_control.item("Line", value="line"),
            rx.segmented_control.item("Bar", value="bar"),
            value=State.time_series_plot_kind,
            on_change=State.set_time_series_plot_kind,
            size="2",
        ),
        rx.button(
            rx.icon("chart-line", size=15),
            "Plot",
            on_click=State.open_time_series_plot_dialog,
            disabled=State.is_time_series_plot_loading,
            variant="soft",
        ),
        spacing="2",
        align="center",
    )


def time_series_plot_dialog() -> rx.Component:
    """Render the Plotly dialog for the selected time-series frame."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.dialog.title(State.time_series_plot_title),
                rx.dialog.close(
                    rx.button(
                        rx.icon("x", size=16),
                        aria_label="Close plot",
                        title="Close",
                        variant="ghost",
                        size="2",
                    )
                ),
                justify="between",
                align="center",
                width="100%",
            ),
            rx.cond(
                State.is_time_series_plot_loading,
                rx.hstack(
                    rx.spinner(size="3"),
                    rx.text("Preparing plot...", size="2", color_scheme="gray"),
                    spacing="3",
                    align="center",
                    min_height="420px",
                    justify="center",
                    width="100%",
                ),
                rx.cond(
                    State.time_series_plot_error != "",
                    rx.box(
                        rx.text(
                            State.time_series_plot_error,
                            size="2",
                            color_scheme="red",
                        ),
                        min_height="180px",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                    ),
                    rx.plotly(
                        data=State.time_series_plot_figure,
                        config={"responsive": True, "displaylogo": False},
                        use_resize_handler=True,
                        style={"width": "100%", "height": "560px"},
                    ),
                ),
            ),
            width="92vw",
            max_width="1200px",
        ),
        open=State.is_time_series_plot_dialog_open,
        on_open_change=State.set_time_series_plot_dialog_open,
    )


def other_component_dialog() -> rx.Component:
    """Render dialogs for non-canvas sidebar components."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(State.other_component_dialog_title),
            rx.cond(
                State.other_component_dialog_kind == "standard_type",
                standard_type_table(),
                rx.cond(
                    State.other_component_dialog_kind == "csv_table",
                    other_csv_table_editor(),
                    rx.dialog.description(
                        "List manager to be added",
                        size="2",
                        color_scheme="gray",
                    ),
                ),
            ),
            rx.cond(
                State.other_table_error != "",
                rx.text(State.other_table_error, size="2", color_scheme="red"),
                rx.fragment(),
            ),
            rx.flex(
                rx.cond(
                    State.other_component_dialog_kind == "csv_table",
                    rx.hstack(
                        rx.upload(
                            rx.button("Upload CSV", variant="soft"),
                            id=EDITABLE_CSV_UPLOAD_ID,
                            multiple=False,
                            max_files=1,
                            accept={"text/csv": [".csv"]},
                            on_drop=State.upload_editable_csv(
                                rx.upload_files(upload_id=EDITABLE_CSV_UPLOAD_ID)
                            ),
                            border="none",
                            padding="0",
                            width="fit-content",
                        ),
                        rx.cond(
                            State.time_series_dialog_key == "",
                            rx.button(
                                "Add row",
                                on_click=State.add_other_table_row,
                                variant="soft",
                            ),
                            rx.fragment(),
                        ),
                        spacing="2",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    State.time_series_dialog_key != "",
                    time_series_plot_controls(),
                    rx.fragment(),
                ),
                rx.dialog.close(
                    rx.button("OK", on_click=State.close_other_component_dialog)
                ),
                spacing="2",
                justify="end",
                width="100%",
                margin_top="16px",
            ),
            width="96vw",
            max_width="1600px",
        ),
        open=State.is_other_component_dialog_open,
        on_open_change=State.set_other_component_dialog_open,
    )


def other_csv_header_cell(column: rx.Var[str]) -> rx.Component:
    """Render one editable supplemental CSV table header."""
    return rx.table.column_header_cell(
        column,
        min_width="150px",
        white_space="nowrap",
    )


def other_csv_cell(cell: rx.Var[OtherTableCell]) -> rx.Component:
    """Render one editable supplemental CSV table value."""
    return rx.table.cell(
        rx.input(
            value=cell["value"],
            on_change=lambda value: State.update_other_table_cell(
                cell["row_index"],
                cell["column"],
                value,
            ),
            width="100%",
            min_width="150px",
        ),
        min_width="150px",
    )


def other_csv_row(row: rx.Var[OtherTableRow]) -> rx.Component:
    """Render one editable supplemental CSV table row."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.input(
                value=row["id"],
                placeholder="row id",
                on_change=lambda value: State.update_other_table_row_id(
                    row["row_index"],
                    value,
                ),
                width="100%",
                min_width="180px",
            ),
            min_width="180px",
        ),
        rx.foreach(row["cells"], other_csv_cell),
        rx.table.cell(
            rx.button(
                rx.icon("trash-2", size=16),
                aria_label="Delete row",
                title="Delete row",
                on_click=lambda: State.delete_other_table_row(row["row_index"]),
                variant="soft",
                color_scheme="red",
                size="1",
            ),
            min_width="70px",
        ),
    )


def time_series_csv_row(row: rx.Var[OtherTableRow]) -> rx.Component:
    """Render one editable time-series table row without structural controls."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.text(row["id"], size="2", white_space="nowrap"),
            min_width="180px",
        ),
        rx.foreach(row["cells"], time_series_csv_cell),
    )


def time_series_csv_cell(cell: rx.Var[OtherTableCell]) -> rx.Component:
    """Render one read-only time-series table value."""
    return rx.table.cell(
        rx.text(cell["value"], size="2", white_space="nowrap"),
        min_width="150px",
    )


def other_csv_table_editor() -> rx.Component:
    """Render an editable supplemental CSV table."""
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell(
                        "Name",
                        min_width="180px",
                        white_space="nowrap",
                    ),
                    rx.foreach(
                        State.other_table_dialog_columns,
                        other_csv_header_cell,
                    ),
                    rx.cond(
                        State.time_series_dialog_key == "",
                        rx.table.column_header_cell(""),
                        rx.fragment(),
                    ),
                ),
            ),
            rx.table.body(
                rx.cond(
                    State.time_series_dialog_key == "",
                    rx.foreach(State.other_table_dialog_rows, other_csv_row),
                    rx.foreach(State.other_table_dialog_rows, time_series_csv_row),
                )
            ),
            variant="surface",
            size="2",
            width="100%",
            min_width="max-content",
        ),
        max_height="520px",
        max_width="100%",
        overflow_x="auto",
        overflow_y="auto",
        margin_top="12px",
    )


def standard_type_row(row: rx.Var[StandardTypeRow]) -> rx.Component:
    """Render one standard line or transformer type row."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.text(row["name"], weight="medium", white_space="nowrap"),
            min_width="220px",
        ),
        rx.foreach(row["values"], standard_type_value_cell),
    )


def standard_type_header_cell(column: rx.Var[str]) -> rx.Component:
    """Render a standard type parameter table header."""
    return rx.table.column_header_cell(
        column,
        min_width="120px",
        white_space="nowrap",
    )


def standard_type_value_cell(value: rx.Var[str]) -> rx.Component:
    """Render one standard type parameter value."""
    return rx.table.cell(
        rx.text(value, size="2", white_space="nowrap"),
        min_width="120px",
    )


def standard_type_table() -> rx.Component:
    """Render the selected standard type table."""
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.foreach(
                        State.standard_type_dialog_columns,
                        standard_type_header_cell,
                    ),
                ),
            ),
            rx.table.body(
                rx.foreach(State.standard_type_dialog_rows, standard_type_row)
            ),
            variant="surface",
            size="2",
            width="100%",
            min_width="max-content",
        ),
        max_height="520px",
        max_width="100%",
        overflow_x="auto",
        overflow_y="auto",
        margin_top="12px",
    )


def settings_field_control(field: rx.Var[SettingField]) -> rx.Component:
    """Render the appropriate Reflex control for a settings field based on its type."""
    return rx.cond(
        field["type"] == "bool",
        rx.switch(
            checked=field["value"].to(bool),
            on_change=lambda value: State.update_setting(
                field["section"],
                field["key"],
                value,
            ),
        ),
        rx.cond(
            field["options"].length() > 0,
            rx.select.root(
                rx.select.trigger(placeholder="Select value", width="100%"),
                rx.select.content(
                    rx.select.group(
                        rx.foreach(
                            field["options"],
                            lambda opt: rx.select.item(opt, value=opt),
                        ),
                    ),
                ),
                value=field["value"].to(str),
                on_change=lambda value: State.update_setting(
                    field["section"],
                    field["key"],
                    value,
                ),
                width="100%",
            ),
            rx.input(
                value=field["value"].to(str),
                type=rx.cond(
                    rx.Var.create(["int", "float"]).contains(field["type"]),
                    "number",
                    "text",
                ),
                on_change=lambda value: State.update_setting(
                    field["section"],
                    field["key"],
                    value,
                ),
                width="100%",
            ),
        ),
    )


def settings_field_row(field: rx.Var[SettingField]) -> rx.Component:
    """Render one settings field row with label and control."""
    return rx.hstack(
        rx.text(field["key"], size="2", weight="medium", width="180px"),
        rx.box(settings_field_control(field), flex="1"),
        rx.text(field["type"], size="1", color_scheme="gray", width="80px"),
        spacing="3",
        align="center",
        width="100%",
    )


def settings_tab_trigger_item(tab: rx.Var[SettingsTab]) -> rx.Component:
    """Render one settings tab trigger."""
    return rx.tabs.trigger(rx.text(tab["label"], size="2"), value=tab["label"])


def network_data_setting_row(row: rx.Var[NetworkDataComponentSetting]) -> rx.Component:
    """Render one ordered Network Data component setting row."""
    return rx.table.row(
        rx.table.row_header_cell(
            rx.vstack(
                rx.text(row["label"], size="2", weight="medium"),
                rx.text(row["component"], size="1", color_scheme="gray"),
                spacing="0",
                align="start",
            ),
            min_width="220px",
        ),
        rx.table.cell(
            rx.switch(
                checked=row["show_in_editor"].to(bool),
                on_change=lambda value: State.update_network_data_component_setting(
                    row["component"],
                    value,
                ),
            ),
            width="120px",
        ),
        rx.table.cell(
            rx.switch(
                checked=row["show_on_sld"].to(bool),
                on_change=lambda value: State.update_network_data_component_sld_setting(
                    row["component"],
                    value,
                ),
            ),
            width="120px",
        ),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    rx.icon("arrow-up", size=14),
                    aria_label="Move up",
                    title="Move up",
                    size="1",
                    variant="soft",
                    on_click=lambda: State.move_network_data_component_setting(
                        row["component"],
                        -1,
                    ),
                ),
                rx.button(
                    rx.icon("arrow-down", size=14),
                    aria_label="Move down",
                    title="Move down",
                    size="1",
                    variant="soft",
                    on_click=lambda: State.move_network_data_component_setting(
                        row["component"],
                        1,
                    ),
                ),
                spacing="1",
            ),
            width="120px",
        ),
    )


def network_data_settings_table() -> rx.Component:
    """Render ordered Network Data visibility settings."""
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Component"),
                    rx.table.column_header_cell("Data editor"),
                    rx.table.column_header_cell("SLD"),
                    rx.table.column_header_cell("Order"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    State.settings_network_data_components,
                    network_data_setting_row,
                )
            ),
            size="2",
            variant="surface",
            width="100%",
        ),
        height="100%",
        max_height="100%",
        overflow_y="auto",
        width="100%",
    )


def settings_tab_content(tab: rx.Var[SettingsTab]) -> rx.Component:
    """Render one settings tab content panel wrapped in a card."""
    return rx.tabs.content(
        rx.cond(
            tab["label"] == "network_data",
            network_data_settings_table(),
            rx.card(
                rx.vstack(
                    rx.foreach(tab["fields"], settings_field_row),
                    spacing="4",
                    align="stretch",
                    padding="12px",
                ),
                size="2",
                height="100%",
                overflow_y="auto",
            ),
        ),
        value=tab["label"],
        height="100%",
        min_height="0",
        overflow="hidden",
    )


def settings_dialog() -> rx.Component:
    """Render the settings dialog with tabbed sections."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.dialog.title("Settings"),
                rx.dialog.close(
                    rx.button(
                        rx.icon("x", size=16),
                        aria_label="Close settings",
                        title="Close",
                        variant="ghost",
                        size="2",
                    )
                ),
                justify="between",
                align="center",
                width="100%",
            ),
            rx.tabs.root(
                rx.tabs.list(
                    rx.foreach(State.settings_tabs, settings_tab_trigger_item),
                    overflow_x="auto",
                    flex_wrap="nowrap",
                    style={"align-items": "flex-start"},
                ),
                rx.foreach(State.settings_tabs, settings_tab_content),
                value=State.settings_active_tab,
                on_change=State.set_settings_active_tab,
                orientation="vertical",
                width="100%",
                height="100%",
                min_height="0",
                flex="1",
                overflow="hidden",
                margin_top="12px",
            ),
            width="900px",
            height="720px",
            max_width="96vw",
            max_height="92vh",
            display="flex",
            flex_direction="column",
        ),
        open=State.is_settings_dialog_open,
        on_open_change=State.set_settings_dialog_open,
    )
