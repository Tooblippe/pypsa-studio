"""Inline style block for the PyPSA Studio UI."""

import reflex as rx


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
          .network-data-grid {
            border-collapse: collapse !important;
            border-spacing: 0 !important;
            table-layout: auto !important;
            width: max-content !important;
            min-width: max-content !important;
          }
          .network-data-grid :where(th, td) {
            padding: 0 !important;
            border: 1px solid var(--gray-5) !important;
            background: var(--color-panel-solid);
          }
          .network-data-grid :where(th) {
            padding: 5px 8px !important;
            background: var(--gray-2);
          }
          .network-data-grid :where(.network-data-control, input.network-data-control, button.network-data-control) {
            width: auto !important;
            min-width: 72px !important;
            max-width: none !important;
            height: 30px !important;
            min-height: 30px !important;
            margin: 0 !important;
            padding: 3px 8px !important;
            border: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            background: transparent !important;
            outline: none !important;
            field-sizing: content;
          }
          .network-data-grid :where(.network-data-control:focus, .network-data-control:focus-visible, .network-data-control[data-state="open"]) {
            box-shadow: 0 0 0 2px var(--accent-7) inset !important;
            background: var(--accent-2) !important;
          }
          .network-data-grid :where(.network-data-number) {
            text-align: right !important;
            font-variant-numeric: tabular-nums;
          }
          .network-data-grid :where(td > div) {
            gap: 0 !important;
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
          .canvas-toolbar {
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 6px !important;
            flex: 0 0 44px;
            height: 44px;
            min-height: 44px;
            padding: 5px 8px;
            box-sizing: border-box;
            border: 1px solid color-mix(in srgb, var(--gray-7) 72%, transparent);
            border-radius: 8px;
            background: linear-gradient(180deg, var(--gray-4), var(--gray-3));
          }
          .canvas-toolbar > * {
            flex: 0 0 auto !important;
          }
          .canvas-tool-button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 32px !important;
            height: 32px !important;
            min-width: 32px !important;
            min-height: 32px !important;
            padding: 0 !important;
            margin: 0 !important;
            box-sizing: border-box !important;
            border: 1px solid color-mix(in srgb, var(--gray-8) 72%, transparent) !important;
            border-radius: 6px !important;
            background: var(--gray-4) !important;
            color: var(--gray-12) !important;
            line-height: 1 !important;
            box-shadow: 0 1px 0 color-mix(in srgb, white 50%, transparent) inset;
            transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
          }
          .canvas-tool-button svg {
            display: block !important;
            width: 16px !important;
            height: 16px !important;
            flex: 0 0 auto !important;
          }
          .canvas-tool-button:hover,
          .canvas-tool-button:focus-visible {
            border-color: var(--accent-8) !important;
            background: var(--accent-4) !important;
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent-6) 50%, transparent);
            outline: none;
            transform: translateY(-1px);
          }
          .canvas-tool-button[data-active="true"] {
            border-color: var(--accent-9) !important;
            background: color-mix(in srgb, var(--accent-4) 76%, var(--color-panel-solid)) !important;
          }
          .canvas-tool-separator {
            width: 1px !important;
            height: 24px !important;
            margin: 0 2px !important;
            border-radius: 9999px !important;
            background: color-mix(in srgb, var(--gray-8) 70%, transparent);
          }
          .palette-sidebar,
          .inspector-sidebar {
            background: var(--gray-4);
          }
          .palette-sidebar {
            padding: 4px !important;
          }
          .palette-tool-button {
            --palette-tool-color: #15803d;
            box-sizing: border-box !important;
            border: 1px solid color-mix(in srgb, var(--gray-8) 72%, transparent) !important;
            border-radius: 6px !important;
            background: var(--gray-4) !important;
            color: var(--gray-12) !important;
            line-height: 1 !important;
            box-shadow: 0 1px 0 color-mix(in srgb, white 50%, transparent) inset;
            transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
          }
          .palette-tool-button .palette-symbol {
            display: block !important;
            width: 18px !important;
            height: 18px !important;
            flex: 0 0 auto !important;
            object-fit: contain;
            filter: none;
          }
          .palette-tool-button:hover,
          .palette-tool-button:focus-visible {
            border-color: var(--palette-tool-color) !important;
            background: color-mix(in srgb, var(--palette-tool-color) 12%, var(--gray-4)) !important;
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--palette-tool-color) 28%, transparent);
            outline: none;
            transform: translateY(-1px);
          }
          .palette-tool-button[data-active="true"] {
            border-color: var(--palette-tool-color) !important;
            background: color-mix(in srgb, var(--palette-tool-color) 16%, var(--color-panel-solid)) !important;
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
          .schematic-node[data-layout-locked="true"] {
            border-color: var(--amber-8);
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--amber-6) 70%, transparent);
          }
          .schematic-node[data-layout-locked="true"]::after {
            content: "";
            position: absolute;
            top: -5px;
            right: -5px;
            width: 8px;
            height: 8px;
            border: 1px solid var(--amber-9);
            border-radius: 999px;
            background: var(--amber-9);
            box-shadow: 0 0 0 2px var(--color-panel-solid);
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
          .react-flow-shell[data-rectangle-selection-armed="true"],
          .react-flow-shell[data-rectangle-selection-armed="true"] .react-flow__pane {
            cursor: crosshair !important;
          }
          .react-flow-shell[data-rectangle-selection-armed="true"] .react-flow__node,
          .react-flow-shell[data-rectangle-selection-armed="true"] .react-flow__edge,
          .react-flow-shell[data-rectangle-selection-armed="true"] .react-flow__edge-path,
          .react-flow-shell[data-rectangle-selection-armed="true"] .react-flow__edge-interaction,
          .react-flow-shell[data-rectangle-selection-armed="true"] .react-flow__edge-textwrapper {
            pointer-events: none;
          }
          .canvas-selection-rectangle {
            position: absolute;
            z-index: 24;
            pointer-events: none;
            border: 1px dashed #2563eb;
            border-radius: 3px;
            background: color-mix(in srgb, #60a5fa 18%, transparent);
            box-shadow: 0 0 0 1px color-mix(in srgb, #2563eb 18%, transparent) inset;
          }
          .canvas-region-layer {
            position: absolute;
            inset: 0;
            z-index: 22;
            pointer-events: none;
          }
          .canvas-region {
            position: absolute;
            pointer-events: auto;
            border: var(--region-border-width, 1px) solid var(--region-color, #2563eb);
            border-radius: 4px;
            background: color-mix(in srgb, var(--region-color, #2563eb) var(--region-fill-percent, 16%), transparent);
            box-shadow: 0 0 0 1px color-mix(in srgb, var(--region-color, #2563eb) 22%, transparent) inset;
            cursor: context-menu;
          }
          .canvas-region[data-armed="true"],
          .canvas-region[data-dragging="true"],
          .canvas-region[data-resize-armed="true"],
          .canvas-region[data-resizing="true"] {
            box-shadow:
              0 0 0 2px color-mix(in srgb, var(--region-color, #2563eb) 38%, transparent),
              0 0 0 1px color-mix(in srgb, var(--region-color, #2563eb) 30%, transparent) inset;
          }
          .canvas-region[data-armed="true"],
          .canvas-region[data-dragging="true"] {
            cursor: move;
          }
          .canvas-region[data-resize-armed="true"],
          .canvas-region[data-resizing="true"] {
            cursor: default;
          }
          .canvas-region-label {
            position: absolute;
            top: -24px;
            left: -1px;
            max-width: 180px;
            min-height: 22px;
            padding: 2px 7px;
            border: 1px solid var(--region-color, #2563eb);
            border-radius: 4px;
            background: color-mix(in srgb, var(--region-color, #2563eb) 12%, white);
            color: color-mix(in srgb, var(--region-color, #2563eb) 78%, black);
            font: inherit;
            font-size: 12px;
            line-height: 16px;
            text-align: left;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: context-menu;
            pointer-events: auto;
          }
          .canvas-region[data-armed="true"] .canvas-region-label,
          .canvas-region[data-dragging="true"] .canvas-region-label {
            cursor: move;
            font-weight: 600;
          }
          .canvas-region[data-resize-armed="true"] .canvas-region-label,
          .canvas-region[data-resizing="true"] .canvas-region-label {
            font-weight: 600;
          }
          .canvas-region-resize-handle {
            position: absolute;
            z-index: 2;
            width: 12px;
            height: 12px;
            padding: 0;
            border: 2px solid white;
            border-radius: 50%;
            background: var(--region-color, #2563eb);
            box-shadow: 0 0 0 1px color-mix(in srgb, var(--region-color, #2563eb) 72%, black);
            pointer-events: auto;
          }
          .canvas-region-resize-handle[data-handle="nw"] {
            top: -6px;
            left: -6px;
            cursor: nwse-resize;
          }
          .canvas-region-resize-handle[data-handle="ne"] {
            top: -6px;
            right: -6px;
            cursor: nesw-resize;
          }
          .canvas-region-resize-handle[data-handle="sw"] {
            bottom: -6px;
            left: -6px;
            cursor: nesw-resize;
          }
          .canvas-region-resize-handle[data-handle="se"] {
            right: -6px;
            bottom: -6px;
            cursor: nwse-resize;
          }
          .canvas-region-label-input {
            width: min(180px, max(92px, 100%));
            outline: none;
            cursor: text !important;
          }
          .canvas-region[data-summary="true"] .canvas-region-label {
            top: 50%;
            left: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            width: min(82%, 420px);
            max-width: none;
            min-height: 44px;
            padding: 8px 14px;
            border-width: 2px;
            background: color-mix(in srgb, var(--region-color, #2563eb) 18%, white);
            color: color-mix(in srgb, var(--region-color, #2563eb) 72%, black);
            font-size: 22px;
            font-weight: 700;
            line-height: 28px;
            text-align: center;
            white-space: normal;
            overflow-wrap: anywhere;
            transform: translate(-50%, -50%);
          }
          .canvas-region[data-summary="true"] .canvas-region-label-input {
            height: auto;
          }
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge,
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge-path,
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge-interaction,
          .react-flow-shell[data-branch-armed="true"] .react-flow__edge-textwrapper {
            pointer-events: none;
          }
          .canvas-context-menu {
            position: absolute;
            z-index: 30;
            min-width: 172px;
            padding: 5px;
            border: 1px solid color-mix(in srgb, var(--gray-8) 72%, transparent);
            border-radius: 6px;
            background: var(--color-panel-solid);
            box-shadow: 0 12px 28px color-mix(in srgb, var(--gray-12) 22%, transparent);
          }
          .canvas-context-menu-title {
            padding: 4px 8px 5px;
            color: var(--gray-10);
            font-size: 11px;
            line-height: 14px;
          }
          .canvas-context-menu-item {
            display: block;
            width: 100%;
            min-height: 30px;
            padding: 6px 8px;
            border: 0;
            border-radius: 4px;
            background: transparent;
            color: var(--gray-12);
            font: inherit;
            font-size: 13px;
            line-height: 18px;
            text-align: left;
            cursor: pointer;
          }
          .canvas-context-menu-item:hover,
          .canvas-context-menu-item:focus-visible {
            background: var(--accent-4);
            outline: none;
          }
          .canvas-region-color-menu {
            display: grid;
            grid-template-columns: repeat(4, 28px);
            gap: 6px;
            padding: 4px;
          }
          .canvas-region-color-option {
            width: 28px;
            height: 28px;
            border: 1px solid color-mix(in srgb, var(--gray-12) 28%, transparent);
            border-radius: 5px;
            cursor: pointer;
            box-shadow: 0 1px 0 color-mix(in srgb, white 45%, transparent) inset;
          }
          .canvas-region-color-option[data-selected="true"] {
            outline: 2px solid var(--gray-12);
            outline-offset: 1px;
          }
          .canvas-region-color-menu .canvas-context-menu-item {
            grid-column: 1 / -1;
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
          .react-flow__edge.schematic-branch-edge .react-flow__edge-path {
            transition: stroke 120ms ease;
          }
          .react-flow__edge.schematic-branch-edge:hover .react-flow__edge-path {
            stroke: #2563eb !important;
          }
          .schematic-branch-target-arrow {
            position: absolute;
            z-index: 4;
            width: 14px;
            height: 14px;
            overflow: visible;
            color: #9ca3af;
            pointer-events: none;
            transform-origin: center;
          }
          .schematic-branch-target-arrow path {
            fill: none;
            stroke: currentColor;
            stroke-width: 2.4;
            stroke-linecap: round;
            stroke-linejoin: round;
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
          [data-is-root-theme="dark"] .schematic-node-symbol,
          [data-theme="dark"] .schematic-node-symbol,
          .dark .schematic-node-symbol,
          [data-is-root-theme="dark"] .palette-symbol,
          [data-theme="dark"] .palette-symbol,
          .dark .palette-symbol {
            filter: invert(1) brightness(1.35) contrast(1.1);
          }
          .schematic-node[data-negative-generator="true"] .schematic-node-symbol {
            color: #dc2626;
            filter: none;
          }
          .schematic-node[data-negative-generator="true"] .schematic-terminal,
          .schematic-node[data-negative-generator="true"] .schematic-terminal::after {
            background: #dc2626;
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
