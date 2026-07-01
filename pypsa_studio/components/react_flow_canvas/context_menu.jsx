const CANVAS_CONTEXT_MENU_ITEMS = [
  {
    id: "select",
    label: "Select",
    targetKinds: ["component", "branch", "edge"],
  },
  {
    id: "toggle_lock",
    label: (contextMenu) =>
      contextMenu?.isLocked ? "Unlock position" : "Lock in place",
    targetKinds: ["component"],
  },
  {
    id: "rotate_bus",
    label: "Rotate 90 degrees",
    targetKinds: ["component"],
    hidden: (contextMenu) => contextMenu?.component !== "buses",
  },
  {
    id: "hide",
    label: "Hide",
    targetKinds: ["component", "branch", "edge", "selection"],
  },
  {
    id: "reset_edge_offset",
    label: "Reset edge offset",
    targetKinds: ["edge"],
    hidden: (contextMenu) => !Boolean(contextMenu?.hasEdgeOffset),
  },
  {
    id: "lock_selection",
    label: "Lock all",
    targetKinds: ["selection"],
  },
  {
    id: "mark_regions",
    label: "Mark regions",
    targetKinds: ["selection"],
  },
  {
    id: "rename_region",
    label: "Rename",
    targetKinds: ["region"],
  },
  {
    id: "open_region_color",
    label: "Colour",
    targetKinds: ["region"],
  },
  {
    id: "drag_region_marker",
    label: "Drag region marker",
    targetKinds: ["region"],
  },
  {
    id: "drag_region_with_components",
    label: "Drag region with components",
    targetKinds: ["region"],
  },
  {
    id: "resize_region_marker",
    label: "Resize",
    targetKinds: ["region"],
  },
  {
    id: "zoom_to_region",
    label: "Zoom to region",
    targetKinds: ["region"],
  },
  {
    id: "hide_region_summary",
    label: "Hide all",
    targetKinds: ["region"],
    hidden: (contextMenu) => Boolean(contextMenu?.isSummary),
  },
  {
    id: "unhide_region_summary",
    label: "Unhide everything",
    targetKinds: ["region"],
    hidden: (contextMenu) => !Boolean(contextMenu?.isSummary),
  },
  {
    id: "delete",
    label: "Delete",
    targetKinds: ["component", "branch", "edge", "region"],
  },
];

function canvasContextMenuItemsForTarget(contextMenu) {
  if (!contextMenu?.targetKind) return [];
  return CANVAS_CONTEXT_MENU_ITEMS.filter((item) =>
    item.targetKinds.includes(contextMenu.targetKind) &&
    !(typeof item.hidden === "function" && item.hidden(contextMenu)),
  );
}

function canvasContextTargetLabel(contextMenu) {
  if (!contextMenu?.targetKind) return "";
  if (contextMenu.targetKind === "selection") return "Selection";
  if (contextMenu.targetKind === "region") return "Region";
  if (contextMenu.targetKind === "edge") return "Edge";
  return contextMenu.targetKind === "branch" ? "Branch" : "Component";
}

function CanvasContextMenu({ contextMenu, onAction }) {
  if (!contextMenu) return null;
  const menuItems = canvasContextMenuItemsForTarget(contextMenu);
  if (!menuItems.length && contextMenu.mode !== "color") return null;

  return (
    <div
      className="canvas-context-menu"
      role="menu"
      aria-label={`${canvasContextTargetLabel(contextMenu)} actions`}
      style={{
        left: `${contextMenu.x}px`,
        top: `${contextMenu.y}px`,
      }}
      onClick={(event) => event.stopPropagation()}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div className="canvas-context-menu-title">
        {contextMenu.mode === "color" ? "Region colour" : canvasContextTargetLabel(contextMenu)}
      </div>
      {contextMenu.mode === "color" ? (
        <div className="canvas-region-color-menu" role="group" aria-label="Region colour presets">
          {REGION_COLOR_OPTIONS.map((option) => (
            <button
              key={option.color}
              type="button"
              className="canvas-region-color-option"
              aria-label={option.label}
              title={option.label}
              style={{ background: option.color }}
              data-selected={(contextMenu.regionColor || DEFAULT_REGION_COLOR) === option.color ? "true" : "false"}
              onClick={(event) => {
                event.stopPropagation();
                onAction("set_region_color", {
                  ...contextMenu,
                  regionColor: option.color,
                });
              }}
            />
          ))}
          <button
            type="button"
            className="canvas-context-menu-item"
            role="menuitem"
            onClick={(event) => {
              event.stopPropagation();
              onAction("show_region_menu", { ...contextMenu, mode: "" });
            }}
          >
            Back
          </button>
        </div>
      ) : (
        menuItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className="canvas-context-menu-item"
            role="menuitem"
            onClick={(event) => {
              event.stopPropagation();
              onAction(item.id, contextMenu);
            }}
          >
            {typeof item.label === "function" ? item.label(contextMenu) : item.label}
          </button>
        ))
      )}
    </div>
  );
}
