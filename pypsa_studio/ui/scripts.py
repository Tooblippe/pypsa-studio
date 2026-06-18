"""Browser-side helper scripts for the PyPSA Studio UI."""

import reflex as rx


def drag_payload_script() -> rx.Component:
    """Install browser drag payload handling for palette items."""
    return rx.script("""
        if (!window.__pypsaBuilderDragBound) {
          window.__pypsaBuilderDragBound = true;
          document.addEventListener("pointerdown", (event) => {
            const el = event.target.closest("[data-pypsa-component]");
            if (!el) return;
            window.__pypsaBuilderActiveComponent = el.dataset.pypsaComponent;
            window.__pypsaBuilderActivePayload = {
              component: el.dataset.pypsaComponent,
              iconSrc: el.dataset.pypsaIconSrc || "",
            };
          }, true);
          document.addEventListener("dragstart", (event) => {
            const el = event.target.closest("[data-pypsa-component]");
            if (!el || !event.dataTransfer) return;
            window.__pypsaBuilderActiveComponent = el.dataset.pypsaComponent;
            const payload = {
              component: el.dataset.pypsaComponent,
              iconSrc: el.dataset.pypsaIconSrc || "",
            };
            window.__pypsaBuilderActivePayload = payload;
            event.dataTransfer.setData(
              "application/pypsa-component",
              JSON.stringify(payload)
            );
            event.dataTransfer.setData("text/plain", JSON.stringify(payload));
            event.dataTransfer.effectAllowed = "copy";
            const icon = el.querySelector("img");
            if (icon) {
              event.dataTransfer.setDragImage(icon, 16, 16);
            } else {
              const dragImage = document.createElement("canvas");
              dragImage.width = 1;
              dragImage.height = 1;
              event.dataTransfer.setDragImage(dragImage, 0, 0);
            }
          }, true);
          document.addEventListener("dragend", () => {
            window.__pypsaBuilderActiveComponent = "";
            window.__pypsaBuilderActivePayload = null;
          }, true);
        }
        """)


def inspector_resize_script() -> rx.Component:
    """Install browser resizing for the inspector sidebar."""
    return rx.script("""
        if (!window.__pypsaInspectorResizeBound) {
          window.__pypsaInspectorResizeBound = true;
          const savedWidth = localStorage.getItem("pypsaInspectorWidth");
          if (savedWidth) {
            document.documentElement.style.setProperty("--inspector-width", savedWidth);
          }
          let resizeState = null;
          const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
          document.addEventListener("pointerdown", (event) => {
            const handle = event.target.closest("[data-inspector-resize-handle]");
            if (!handle) return;
            const shell = handle.closest(".builder-shell");
            if (!shell) return;
            resizeState = {
              shell,
              pointerId: event.pointerId,
            };
            handle.setPointerCapture?.(event.pointerId);
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
            event.preventDefault();
          }, true);
          document.addEventListener("pointermove", (event) => {
            if (!resizeState) return;
            const rect = resizeState.shell.getBoundingClientRect();
            const width = clamp(rect.right - event.clientX, 220, 560);
            const cssWidth = `${width}px`;
            resizeState.shell.style.setProperty("--inspector-width", cssWidth);
            localStorage.setItem("pypsaInspectorWidth", cssWidth);
            event.preventDefault();
          }, true);
          const stopResize = () => {
            if (!resizeState) return;
            resizeState = null;
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
          };
          document.addEventListener("pointerup", stopResize, true);
          document.addEventListener("pointercancel", stopResize, true);
        }
        """)


def canvas_shortcuts_script() -> rx.Component:
    """Install application keyboard shortcuts."""
    return rx.script("""
        if (!window.__pypsaBuilderShortcutsBound) {
          window.__pypsaBuilderShortcutsBound = true;
          document.addEventListener("keydown", (event) => {
            const target = event.target;
            const tag = (target?.tagName || "").toLowerCase();
            const editable =
              target?.isContentEditable ||
              tag === "input" ||
              tag === "textarea" ||
              tag === "select";
            if (editable || event.metaKey) return;
            const key = String(event.key || "").toLowerCase();
            if (event.altKey && !event.ctrlKey && !event.shiftKey) {
              const menuTriggers = {
                n: "network-menu-trigger",
                c: "canvas-menu-trigger",
                v: "view-menu-trigger",
                d: "data-menu-trigger",
              };
              const triggerId = menuTriggers[key];
              if (triggerId) {
                event.preventDefault();
                document.getElementById(triggerId)?.click();
              }
              return;
            }
            if (!event.ctrlKey || event.altKey) return;
            const shortcutActions = {
              n: "network-name-shortcut",
              o: "network-load-shortcut",
              s: "network-save-shortcut",
              e: "network-export-shortcut",
              r: "canvas-auto-route-shortcut",
              "1": "view-builder-shortcut",
              "2": "view-debug-network-shortcut",
              "3": "view-catalog-shortcut",
            };
            if (event.shiftKey && key === "d") {
              event.preventDefault();
              document.getElementById("data-network-data-shortcut")?.click();
              return;
            }
            if (event.shiftKey && key === "backspace") {
              event.preventDefault();
              document.getElementById("canvas-clear-shortcut")?.click();
              return;
            }
            const actionId = !event.shiftKey ? shortcutActions[key] : null;
            if (actionId) {
              event.preventDefault();
              document.getElementById(actionId)?.click();
              return;
            }
            if (key === "z" && event.shiftKey) {
              event.preventDefault();
              document.getElementById("canvas-redo-button")?.click();
            } else if (key === "z") {
              event.preventDefault();
              document.getElementById("canvas-undo-button")?.click();
            }
          }, true);
        }
        """)


def directory_upload_script(upload_id: str) -> rx.Component:
    """Enable directory selection on a Reflex upload file input."""
    return rx.script(f"""
        setTimeout(() => {{
          const input = document.querySelector("#{upload_id} input[type='file']");
          if (input) {{
            input.setAttribute("webkitdirectory", "");
            input.setAttribute("directory", "");
            input.setAttribute("mozdirectory", "");
          }}
        }}, 0);
        """)
