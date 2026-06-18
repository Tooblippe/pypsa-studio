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
            padding: 6px !important;
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
