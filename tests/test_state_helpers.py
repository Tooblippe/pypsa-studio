import asyncio
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pypsa

import pypsa_studio.state as st
from pypsa_studio.routers.builtin import GridRouter


def make_state(tmp_path: Path, monkeypatch) -> st.State:
    """Return a Reflex state instance wired to temporary settings files."""
    monkeypatch.setattr(st, "SETTINGS_DIR", tmp_path / "settings")
    monkeypatch.setattr(st, "SETTINGS_FILE", tmp_path / "settings" / "settings.toml")
    monkeypatch.setattr(st, "APP_STATE_DIR", tmp_path / "app-state")
    monkeypatch.setattr(st, "APP_SETTINGS_FILE", tmp_path / "app-state" / "app.json")
    return st.State(_reflex_internal_init=True)


async def drain_async_generator(generator: Any) -> list[object]:
    """Consume an async Reflex event generator and return yielded events."""
    yielded: list[object] = []
    async for item in generator:
        yielded.append(item)
    return yielded


def test_file_picker_and_settings_helpers(tmp_path: Path, monkeypatch) -> None:
    """Exercise picker rows, settings TOML, and upload cleanup helpers."""
    state = make_state(tmp_path, monkeypatch)
    upload_dir = tmp_path / "uploads"
    (upload_dir / "nested").mkdir(parents=True)
    (upload_dir / "nested" / "old.txt").write_text("old", encoding="utf-8")
    (upload_dir / "old.nc").write_text("old", encoding="utf-8")

    st.clean_upload_staging_dir(upload_dir)

    assert list(upload_dir.iterdir()) == []
    assert st.network_save_format_for_path(tmp_path / "folder") == "csv"
    assert st.network_save_format_for_path("demo.nc") == "netcdf"
    assert st.default_save_file_name("Demo Network!", "hdf5") == "Demo-Network.h5"
    assert st.apply_save_format_extension(Path("demo"), "netcdf") == Path("demo.nc")

    (tmp_path / "visible.nc").write_text("network", encoding="utf-8")
    (tmp_path / ".hidden.nc").write_text("network", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    entries, warning, error = st.scan_file_picker_directory(tmp_path, "load", "csv")

    assert error == ""
    assert warning == ""
    assert [entry["name"] for entry in entries] == ["folder", "uploads", "visible.nc"]
    assert entries[0]["kind"] == "folder"
    assert st.file_picker_entry_for_path(tmp_path / "visible.nc", "save", "netcdf")[
        "selectable"
    ]

    state.open_settings_dialog()
    state.update_setting("Theme", "mode", "dark")
    state.set_settings_active_tab("Canvas")
    state.set_settings_dialog_open(False)
    settings_text = st.SETTINGS_FILE.read_text(encoding="utf-8")

    assert 'mode = "dark"' in settings_text
    assert state.settings_active_tab == "Canvas"

    st.write_last_network_folder(tmp_path / "folder")
    assert st.read_last_network_folder() == tmp_path / "folder"
    st.write_file_picker_last_path(tmp_path)
    assert st.read_file_picker_last_path() == tmp_path


def test_network_table_and_layout_helpers(tmp_path: Path) -> None:
    """Exercise table conversions, layout sidecars, and import positioning."""
    data_frame = pd.DataFrame(
        {"carrier": ["AC"], "x": ["1.5"]},
        index=pd.Index(["bus_a"], name="name"),
    )
    table = st.dataframe_to_other_csv_table("carriers", data_frame)

    assert table["rows"][0]["id"] == "bus_a"
    assert st.table_index_value(("a", "b")) == "a, b"
    assert st.plot_numeric_value("3.5") == 3.5
    assert st.plot_numeric_value("") is None
    assert st.format_numeric_display_value("12345.5000") == "12,345.5"
    assert st.network_data_display_value("1234", "number") == "1,234"
    assert st.attr_input_type("float", None) == "number"
    assert st.clean_numeric_text(" 1,200 ") == "1200"
    assert st.is_bus_reference_attr("bus2")
    assert st.default_other_table_columns("snapshots") == [
        "period",
        "timestep",
        "objective",
        "stores",
        "generators",
    ]

    time_series = st.dataframe_to_time_series_table(
        "generators",
        "p_set",
        pd.DataFrame({"gen_a": [1, 2]}, index=["now", "later"]),
        dirty=True,
    )

    assert time_series["file_name"] == "generators-p_set.csv"
    assert time_series["dirty"]

    csv_folder = tmp_path / "csv"
    csv_folder.mkdir()
    (csv_folder / "network.csv").write_text("attribute,value\nname,demo\n")
    (csv_folder / "buses.csv").write_text("name,v_nom\nbus_a,110\n")
    (csv_folder / "generators-p_set.csv").write_text(",gen_a\nnow,1\n")
    (csv_folder / "bad-attr.csv").write_text(",x\nnow,1\n")

    assert st.is_valid_pypsa_csv_folder(csv_folder)
    loaded_other = st.load_other_csv_tables(csv_folder)
    loaded_time_series = st.load_time_series_csv_tables(csv_folder)

    assert "carriers" in loaded_other
    assert loaded_time_series["generators:p_set"]["columns"] == ["gen_a"]

    sidecar = st.layout_sidecar_path(csv_folder)
    sidecar.write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "component": "buses",
                        "name": "bus_a",
                        "x": 10,
                        "y": 20,
                        "bus_orientation": "horizontal",
                        "locked": True,
                        "visible": False,
                        "edge_offset_x": 4,
                    },
                    {"component": "", "name": "bad", "x": "nope", "y": 0},
                ],
                "regions": [
                    {
                        "id": "",
                        "name": "",
                        "x": 1,
                        "y": 2,
                        "width": 3,
                        "height": 4,
                        "color": "#16A34A",
                        "summary": True,
                        "summary_node_ids": ["bus_1", ""],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    positions = st.load_layout_positions(csv_folder)
    regions = st.load_layout_regions(csv_folder)

    assert positions[("buses", "bus_a")]["locked"] is True
    assert regions[0]["id"] == "region-1"
    assert regions[0]["color"] == "#16a34a"
    assert st.edge_offset_from_layout(
        {"edge_offset_x": "5", "edge_offset_y": "bad"}
    ) == {
        "x": 0.0,
        "y": 0.0,
    }
    assert st.normalize_canvas_region_color("unknown") == st.DEFAULT_CANVAS_REGION_COLOR

    counters: dict[str, int] = {}
    assert st.next_import_node_id(counters, "buses") == "bus_1"
    assert st.component_id_prefix("processes") == "process"
    assert st.normalize_bus_side("LEFT") == "left"
    assert st.normalize_bus_orientation("sideways") == "vertical"
    assert st.default_bus_side_for_component("loads") == "right"

    bus_positions = {"bus_a": {"x": 100.0, "y": 200.0}}
    bus_counts: dict[str, int] = {}
    x_positions: dict[str, int] = {}
    assert st.import_position_for_component(
        "generators",
        0,
        x_positions,
        {"bus": "bus_a"},
        bus_positions,
        bus_counts,
    ) == (25.0, 52.0)


def test_network_import_export_helpers(tmp_path: Path) -> None:
    """Exercise network artifact loading and diagram export side effects."""
    network = pypsa.Network()
    network.name = "demo"
    network.add("Bus", "bus_a")
    network.add("Carrier", "wind")
    network.add("Generator", "gen_a", bus="bus_a", carrier="wind", p_nom=5)
    network.set_snapshots(["now", "later"])
    network.generators_t.p_set = pd.DataFrame(
        {"gen_a": [1.0, 2.0]},
        index=network.snapshots,
    )
    csv_folder = tmp_path / "network"
    network.export_to_csv_folder(csv_folder)

    artifacts = st.load_network_artifacts(csv_folder)

    assert artifacts["loaded_network"].component_counts["generators"] == 1
    assert len(artifacts["time_series_tables"]["generators:p_set"]["rows"]) == 2
    assert st.load_network_file(csv_folder)[1].source == str(csv_folder)

    diagram_model = {
        "components": [
            {
                "id": "bus_1",
                "component": "buses",
                "position": {"x": 10, "y": 20},
                "attrs": {"name": "bus_a"},
                "layout": {"bus_orientation": "horizontal", "locked": True},
            },
            {
                "id": "gen_1",
                "component": "generators",
                "position": {"x": 0, "y": 20},
                "attrs": {"name": "gen_a", "bus": "bus_a", "p_nom": 5},
                "layout": {"bus_side": "left", "edge_offset_y": 7},
            },
        ],
        "regions": [
            {
                "id": "region-1",
                "name": "North",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
                "color": "#2563eb",
                "summary": True,
                "summary_node_ids": ["bus_1"],
            }
        ],
    }
    export_folder = tmp_path / "export"
    exported = st.export_diagram_to_network_path(
        diagram_model,
        st.NETWORK_MODEL,
        export_folder,
        "csv",
        "demo",
        extra_csv_tables={
            "carriers.csv": {
                "columns": ["color"],
                "rows": [{"id": "wind", "values": ["blue"]}],
                "index_name": "name",
            }
        },
    )

    assert exported == export_folder
    assert (export_folder / "buses.csv").exists()
    assert (
        json.loads(st.layout_sidecar_path(export_folder).read_text(encoding="utf-8"))[
            "regions"
        ][0]["name"]
        == "North"
    )


def test_canvas_state_mutations(tmp_path: Path, monkeypatch) -> None:
    """Exercise canvas node, edge, history, region, and reference state methods."""
    state = make_state(tmp_path, monkeypatch)
    state._add_diagram_node_at("buses", 100, 100)
    state._add_diagram_node_at("generators", 20, 108, bus_node_id="bus_1")
    state.update_selected_attr("carrier", "wind")

    assert state.selected_node_id == "generator_1"
    assert state.diagram_edges[0]["id"] == "attach:generator_1:bus_1"
    assert state.canvas_bus_names == ["bus_1"]

    state.set_edge_offset("generator_1", 2.24, 0.3)
    assert state.diagram_edges[0]["edge_offset"] == {"x": 2.2, "y": 0.0}

    state.set_node_layout_locked("generator_1", True)
    state.toggle_node_layout_locked("generator_1")
    assert not state.is_node_layout_locked(state.diagram_nodes[1])

    state.rotate_bus_node("bus_1")
    assert state.diagram_nodes[0]["layout"]["bus_orientation"] == "horizontal"

    state.lock_canvas_selection(["bus_1", "generator_1"])
    assert state.is_node_layout_locked(state.diagram_nodes[0])
    state.hide_canvas_selection(["generator_1"])
    assert state.diagram_nodes[1]["layout"]["visible"] is False
    state.unhide_all_canvas_components()
    assert st.is_canvas_visible(state.diagram_nodes[1])

    state.open_mark_region_dialog(
        ["bus_1", "generator_1"],
        {"x": 0, "y": 0, "width": 200, "height": 200},
    )
    state.set_mark_region_name("North")
    state.confirm_mark_region()
    region_id = state.canvas_regions[0]["id"]
    state.rename_canvas_region(region_id, "South")
    state.set_canvas_region_color(region_id, "#dc2626")
    state.summarize_canvas_region(region_id)

    assert state.summarized_region_node_ids() == {"bus_1", "generator_1"}

    state.unhide_canvas_region_summary(region_id)
    state.move_canvas_region(
        region_id,
        {"x": 10, "y": 20, "width": 100, "height": 120},
        [{"id": "bus_1", "position": {"x": 15, "y": 25}}],
        ["bus_1"],
    )
    assert state.canvas_regions[0]["x"] == 10

    state.handle_canvas_context_menu_action(
        {
            "action_id": "set_region_color",
            "target_kind": "region",
            "region_id": region_id,
            "region_color": "#16a34a",
        }
    )
    assert state.canvas_regions[0]["color"] == "#16a34a"

    state.commit_selected_attr_reference("carrier", "wind")
    assert state._reference_options_for_attr("carrier") == ["wind"]
    extra_tables = state._extra_csv_tables_for_export()
    assert "carriers.csv" in extra_tables

    state.undo_canvas()
    assert state.can_redo_canvas
    state.redo_canvas()
    state.delete_node_by_id("bus_1")
    assert state.selected_node_id == ""


def test_network_data_state_mutations(tmp_path: Path, monkeypatch) -> None:
    """Exercise network data paging, filtering, table edits, and dirty flags."""
    state = make_state(tmp_path, monkeypatch)
    state._add_diagram_node_at("buses", 100, 100)
    state._add_diagram_node_at("generators", 20, 108, bus_node_id="bus_1")
    state.open_settings_dialog()
    state.open_network_data_dialog()

    assert state.is_network_data_dialog_open
    assert any(tab["component"] == "buses" for tab in state.network_data_tabs)

    state.set_network_data_active_component("generators")
    state.set_network_data_row_query("generator")
    assert state.network_data_tabs[0]["page_count"] >= 1
    state.set_network_data_column_filter("bus", "bus_1")
    state.clear_network_data_filters()
    state.set_network_data_page_size("250")
    state.next_network_data_page()
    state.previous_network_data_page()

    state.update_network_data_cell("generators", "generator_1", 0, "p_nom", "1,500")
    generator = next(
        node for node in state.diagram_nodes if node["id"] == "generator_1"
    )
    assert generator["attrs"]["p_nom"] == 1500.0

    state.update_network_data_row_name("buses", "bus_1", 0, "main_bus")
    assert generator["attrs"]["bus"] == "main_bus"

    state.set_network_data_active_component("carriers")
    state.update_network_data_row_name("carriers", "", 0, "wind")
    state._update_network_data_table_cell("carriers", 0, "color", "blue")
    state.commit_network_data_reference("carriers", "carrier", "wind")
    assert state.other_csv_tables["carriers"]["dirty"]

    state.open_other_component_dialog("carriers")
    state.add_other_table_row()
    state.update_other_table_row_id(1, "solar")
    state.update_other_table_cell(1, "color", "yellow")
    state.delete_other_table_row(1)
    assert state.other_table_dialog_component == "carriers"

    state._open_time_series_table_columns(
        "generators",
        "p_set",
        ["generator_1"],
        "generators.p_set",
        full_attr=False,
    )
    state.add_other_table_row()
    state.update_other_table_row_id(0, "now")
    state.update_other_table_cell(0, "generator_1", "5")
    assert state._has_time_series_value("generators", "p_set", "generator_1")

    state.open_carrier_visibility_dialog()
    assert state.carrier_visibility_initialized
    state._set_nodes_with_carrier_visible("wind", False)
    state.set_carrier_visibility_dialog_open(False)
    state._mark_network_saved()
    assert not state._has_unsaved_network_changes()


def test_branch_file_picker_and_router_state(tmp_path: Path, monkeypatch) -> None:
    """Exercise branch creation, file picker actions, and router application."""
    state = make_state(tmp_path, monkeypatch)
    state._add_diagram_node_at("buses", 100, 100)
    state._add_diagram_node_at("buses", 300, 100)

    state.arm_branch_component("lines")
    state.handle_branch_bus_click("bus_1")
    state.handle_branch_bus_click("bus_2")

    assert state.diagram_edges[0]["id"].startswith("branch:")
    assert state.selected_component_name == "Line"

    state.arm_canvas_component("loads")
    assert state.armed_component == "loads"
    state.toggle_rectangle_selection_armed()
    assert state.rectangle_selection_armed
    state.set_rectangle_selection_armed(False)

    state.open_file_picker("save_as")
    state.set_file_picker_new_folder_name("exports")
    state.create_file_picker_folder()
    state.navigate_file_picker_to_path(tmp_path / "exports")
    state.navigate_file_picker_parent()
    state.set_file_picker_save_format("netcdf")
    state.set_file_picker_target_name("network")
    save_target, save_format = state._selected_file_picker_save_target()

    assert save_target.name == "network.nc"
    assert save_format == "netcdf"

    selected_file = tmp_path / "demo.nc"
    selected_file.write_text("not a network", encoding="utf-8")
    state.select_file_picker_path(str(selected_file))
    assert state.file_picker_target_name == "demo.nc"
    state.set_file_picker_open(False)
    assert state.file_picker_selected_path == ""

    routed = state._router_network()
    routed["nodes"][0]["position"] = {"x": 500, "y": 200}
    state.set_node_layout_locked("bus_2", True)
    locked_positions = state._locked_node_positions()
    state._restore_locked_router_positions(routed, locked_positions)
    state._apply_routed_network(routed)

    assert state.diagram_nodes[0]["position"] == {"x": 500.0, "y": 200.0}

    class DummyRouter:
        """Router stub that shifts visible nodes right."""

        def route(self, router_network: st.RouterNetwork) -> st.RouterNetwork:
            """Return a minimally changed routed network."""
            for node in router_network["nodes"]:
                node["position"]["x"] = float(node["position"]["x"]) + 10
            return router_network

    monkeypatch.setitem(st.PYTHON_ROUTERS, "dummy", DummyRouter())
    state.selected_router_name = "dummy"
    asyncio.run(drain_async_generator(state.auto_route_canvas()))

    assert state.export_error == ""
    assert state.fit_view_version > 0


def test_save_export_and_pending_actions(tmp_path: Path, monkeypatch) -> None:
    """Exercise save/export async paths with a tiny fake exporter."""
    state = make_state(tmp_path, monkeypatch)
    state._add_diagram_node_at("buses", 100, 100)
    state.network_name = "demo"

    def fake_export(
        diagram_model: dict[str, object],
        network_model: st.PypsaNetworkModel,
        target_path: str | Path,
        export_format: str,
        network_name: str | None = None,
        preserve_source_folder: str | Path | None = None,
        extra_csv_tables: dict[str, dict[str, Any]] | None = None,
    ) -> Path:
        """Return a created path without invoking PyPSA IO."""
        del diagram_model, network_model, network_name, preserve_source_folder
        del extra_csv_tables
        path = Path(target_path)
        if export_format == "csv":
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("network", encoding="utf-8")
        return path

    monkeypatch.setattr(st, "export_diagram_to_network_path", fake_export)

    save_target = tmp_path / "saved"
    asyncio.run(
        drain_async_generator(state._save_canvas_network_to_path(save_target, "csv"))
    )

    assert state.save_network_path == str(save_target)
    assert not state._has_unsaved_network_changes()

    state.export_base_folder = str(tmp_path / "export")
    asyncio.run(drain_async_generator(state.export_canvas_network()))
    assert state.save_network_folder == str(tmp_path / "export")
    (tmp_path / "export" / "old.txt").write_text("old", encoding="utf-8")

    state.open_file_picker("save_as")
    state.file_picker_selected_path = str(tmp_path / "export")
    asyncio.run(drain_async_generator(state.confirm_file_picker()))
    assert state.is_file_picker_overwrite_dialog_open
    asyncio.run(drain_async_generator(state.confirm_file_picker_overwrite()))
    assert not state.is_file_picker_overwrite_dialog_open

    state.request_new_network()
    assert state.is_network_name_dialog_open
    state._mark_network_dirty()
    state.request_load_network_directory_to_canvas()
    assert state.unsaved_network_action == "load_network_directory"
    asyncio.run(drain_async_generator(state.ignore_unsaved_network_changes_and_open()))
    assert state.is_file_picker_open

    state.show_canvas_view()
    state.show_debug_network_view()
    state.show_catalog_view()
    asyncio.run(drain_async_generator(state.show_network_data_view()))
    state.finish_auto_route()
    state.show_operation_error("Failure", "message", retry_load=True)
    asyncio.run(drain_async_generator(state.close_operation_dialog()))

    assert state.active_view == "network-data"
    assert state.is_load_dialog_open


def test_load_canvas_from_selected_network_path(tmp_path: Path, monkeypatch) -> None:
    """Exercise the async local network load path."""
    state = make_state(tmp_path, monkeypatch)
    network = pypsa.Network()
    network.name = "loaded"
    network.add("Bus", "bus_a")
    network.add("Load", "load_a", bus="bus_a")
    csv_folder = tmp_path / "local-network"
    network.export_to_csv_folder(csv_folder)
    st.layout_sidecar_path(csv_folder).write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "component": "buses",
                        "name": "bus_a",
                        "x": 11,
                        "y": 22,
                        "locked": True,
                    }
                ],
                "regions": [
                    {
                        "id": "region-1",
                        "name": "Area",
                        "x": 0,
                        "y": 0,
                        "width": 50,
                        "height": 50,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    asyncio.run(
        drain_async_generator(state._load_canvas_from_selected_network_path(csv_folder))
    )

    assert state.network_name == "loaded"
    assert state.diagram_nodes[0]["position"] == {"x": 11.0, "y": 22.0}
    assert state.canvas_regions[0]["name"] == "Area"
    assert state.save_network_format == "csv"

    state.network_file_path = str(csv_folder)
    asyncio.run(drain_async_generator(state.load_network_directory_path_to_canvas()))
    assert state.export_error == ""


def test_grid_router_and_component_wrapper() -> None:
    """Exercise the pure built-in router and React component wrapper helpers."""
    network: st.RouterNetwork = {
        "nodes": [
            {
                "id": "bus_1",
                "component": "buses",
                "attrs": {"name": "bus_a"},
                "position": {"x": 0, "y": 0},
                "hidden": False,
            },
            {
                "id": "gen_1",
                "component": "generators",
                "attrs": {"bus": "bus_a"},
                "position": {"x": 0, "y": 0},
                "layout": {"bus_side": "left"},
                "hidden": False,
            },
            {
                "id": "store_1",
                "component": "stores",
                "attrs": {"bus": "bus_a"},
                "position": {"x": 0, "y": 0},
                "layout": {"bus_side": "right"},
                "hidden": False,
            },
            {
                "id": "free_1",
                "component": "loads",
                "attrs": {},
                "position": {"x": 0, "y": 0},
                "hidden": False,
            },
        ],
        "edges": [{"id": "edge_1", "source": "gen_1", "target": "bus_1"}],
        "diagram_model": {},
        "metadata": {},
    }

    routed = GridRouter().route(network)
    positions = {node["id"]: node["position"] for node in routed["nodes"]}

    assert positions["bus_1"] == {"x": 180.0, "y": 160.0}
    assert positions["gen_1"]["x"] < positions["bus_1"]["x"]
    assert positions["store_1"]["x"] > positions["bus_1"]["x"]
    assert routed["diagram_model"]["connections"][0]["id"] == "edge_1"
