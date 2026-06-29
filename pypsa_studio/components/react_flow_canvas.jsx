import React, {
  useCallback as useCallbackReactFlowCanvas,
  useEffect as useEffectReactFlowCanvas,
  useMemo as useMemoReactFlowCanvas,
  useRef as useRefReactFlowCanvas,
  useState as useStateReactFlowCanvas,
} from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlowProvider,
  getSmoothStepPath,
  useReactFlow,
  useUpdateNodeInternals,
} from "reactflow";
import ReactFlow from "reactflow";
import "reactflow/dist/style.css";

const BUILDER_SYMBOL_META = {
  bus: { width: 24, height: 72 },
  generator: { width: 44, height: 44 },
  load: { width: 42, height: 48 },
  storage_unit: { width: 44, height: 52 },
  store: { width: 50, height: 52 },
  line: { width: 52, height: 28 },
  link: { width: 52, height: 28 },
};
const BUS_LABEL_HEIGHT = 20;
const BUS_MIN_HEIGHT_PX = 72;
const BUS_CONNECTION_SPACING_PX = 24;
const BUS_CONNECTION_PADDING_PX = 10;
const EDGE_LABEL_VERTICAL_THRESHOLD_PX = 8;
const EDGE_SYMBOL_SIZE_PX = 24;
const BUS_COMPONENT_HORIZONTAL_OFFSET_PX = 75;
const DEFAULT_REGION_COLOR = "#2563eb";
const REGION_COLOR_OPTIONS = [
  { color: "#2563eb", label: "Blue" },
  { color: "#16a34a", label: "Green" },
  { color: "#d97706", label: "Amber" },
  { color: "#dc2626", label: "Red" },
  { color: "#7c3aed", label: "Violet" },
  { color: "#0891b2", label: "Cyan" },
  { color: "#4b5563", label: "Gray" },
];

function componentToBuilderKind(component) {
  const key = String(component || "").toLowerCase();
  const map = {
    buses: "bus",
    bus: "bus",
    generators: "generator",
    generator: "generator",
    loads: "load",
    load: "load",
    storage_units: "storage_unit",
    storage_unit: "storage_unit",
    stores: "store",
    store: "store",
    lines: "line",
    line: "line",
    links: "link",
    link: "link",
    transformers: "transformer",
    transformer: "transformer",
    processes: "process",
    process: "process",
  };
  return map[key] || "";
}

function symbolMetaForComponent(component) {
  const kind = componentToBuilderKind(component);
  return BUILDER_SYMBOL_META[kind] || { width: 56, height: 56 };
}

function maxSideConnectionCount(handles) {
  const sideCounts = { left: 0, right: 0, top: 0, bottom: 0 };
  (handles || []).forEach((handle) => {
    sideCounts[handle.side] = (sideCounts[handle.side] || 0) + 1;
  });
  return Math.max(sideCounts.left, sideCounts.right, sideCounts.top, sideCounts.bottom);
}

function busSymbolLengthForHandles(handles) {
  const maxSideCount = maxSideConnectionCount(handles);
  const connectionSpan = Math.max(0, maxSideCount - 1) * BUS_CONNECTION_SPACING_PX;
  return Math.max(BUS_MIN_HEIGHT_PX, connectionSpan + BUS_CONNECTION_PADDING_PX * 2);
}

function iconContactPercent(component, side) {
  const kind = componentToBuilderKind(component);
  const contactPoints = {
    generator: { left: 0, right: 100 },
    load: { left: 0, right: 100 },
    store: { left: 0, right: 100 },
    storage_unit: { left: 0, right: 100 },
  };
  return contactPoints[kind]?.[side] ?? (side === "left" ? 0 : 100);
}

function hasConnectorTerminal(component) {
  return connectorTerminalSides(component).length > 0;
}

function connectorTerminalSides(component) {
  const kind = componentToBuilderKind(component);
  if (kind === "generator") return ["right"];
  if (kind === "load") return ["left"];
  if (kind === "store" || kind === "storage_unit") return ["left"];
  return [];
}

function connectorTerminalStyleForComponent(component, side, topPx) {
  const kind = componentToBuilderKind(component);
  const style = { top: `${topPx}px` };
  if (kind === "generator" && side === "right") {
    style.width = "8px";
  }
  return style;
}

function isAttachableComponent(component) {
  return Boolean(
    component &&
      !["buses", "lines", "links", "transformers"].includes(component),
  );
}

/**
 * Return whether a component should be represented by an edge, not a node.
 */
function isBranchEdgeComponent(component) {
  return [
    "lines",
    "line",
    "links",
    "link",
    "processes",
    "process",
    "transformers",
    "transformer",
  ].includes(String(component || "").toLowerCase());
}

function parseComponentPayload(payload) {
  if (!payload) return { component: "" };
  if (typeof payload === "string" && payload.trim().startsWith("{")) {
    try {
      return JSON.parse(payload);
    } catch {
      return { component: "" };
    }
  }
  return { component: payload };
}

function activePalettePayload() {
  if (typeof window === "undefined") return "";
  const payload = window.__pypsaBuilderActivePayload || {
    component: window.__pypsaBuilderActiveComponent || "",
  };
  return payload.component ? JSON.stringify(payload) : "";
}

function dragPayloadFromEvent(event) {
  return (
    event.dataTransfer?.getData("application/pypsa-component") ||
    event.dataTransfer?.getData("text/plain") ||
    activePalettePayload()
  );
}

function displayNameForNode(node) {
  return String(node?.attrs?.name || node?.id || node?.pypsa_name || "");
}

function isCanvasVisible(node) {
  return node?.layout?.visible !== false;
}

function safeHandleId(value) {
  return String(value || "edge").replace(/[^a-zA-Z0-9_-]/g, "_");
}

function layoutBusSide(node) {
  const side = String(node?.layout?.bus_side || node?.data?.layout?.bus_side || "").toLowerCase();
  return side === "left" || side === "right" ? side : "";
}

function layoutBusOrientation(node) {
  const orientation = String(node?.layout?.bus_orientation || node?.data?.layout?.bus_orientation || "").toLowerCase();
  return orientation === "horizontal" ? "horizontal" : "vertical";
}

function isHorizontalBus(node) {
  return node?.component === "buses" && layoutBusOrientation(node) === "horizontal";
}

function visualMetaForNode(node, connectionHandles = []) {
  const meta = symbolMetaForComponent(node?.component);
  if (node?.component !== "buses") return meta;
  const busLength = busSymbolLengthForHandles(connectionHandles);
  return isHorizontalBus(node)
    ? { width: busLength, height: meta.width }
    : { width: meta.width, height: busLength };
}

function defaultIconSideForComponent(component) {
  const kind = componentToBuilderKind(component);
  if (kind === "generator") return "left";
  if (kind === "load" || kind === "store" || kind === "storage_unit") return "right";
  return "";
}

function shouldRotateIconForBusSide(component, busSide) {
  const defaultSide = defaultIconSideForComponent(component);
  return Boolean(defaultSide && busSide && defaultSide !== busSide);
}

function nodeCenter(node) {
  if (!node) return null;
  const meta = visualMetaForNode(node);
  return {
    x: Number(node.position?.x || 0) + meta.width / 2,
    y: Number(node.position?.y || 0) + (meta.height + 20) / 2,
  };
}

function sideForBusConnection(busNode, otherNode, fallbackHandle) {
  const busCenter = nodeCenter(busNode);
  const otherCenter = nodeCenter(otherNode);
  const fallbackSide = String(fallbackHandle || "").split("-")[0];
  if (isHorizontalBus(busNode)) {
    if (busCenter && otherCenter) {
      const dx = otherCenter.x - busCenter.x;
      const dy = otherCenter.y - busCenter.y;
      if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 1) {
        return dy < 0 ? "top" : "bottom";
      }
    }
    const busSide = layoutBusSide(otherNode);
    if (busSide) return busSide === "left" ? "top" : "bottom";
    if (fallbackSide === "top" || fallbackSide === "bottom") return fallbackSide;
    return fallbackSide === "left" ? "top" : "bottom";
  }
  if (busCenter && otherCenter) {
    const dx = otherCenter.x - busCenter.x;
    if (Math.abs(dx) > 1) {
      return dx < 0 ? "left" : "right";
    }
  }
  if (fallbackSide === "left" || fallbackSide === "right") return fallbackSide;
  return fallbackSide === "top" ? "left" : "right";
}

function oppositeSide(side) {
  return side === "left" ? "right" : "left";
}

function handleForSide(handleId, side) {
  const handleType = String(handleId || "").endsWith("-target") ? "target" : "source";
  return `${side}-${handleType}`;
}

function busNameForNode(node) {
  return String(node?.attrs?.name || node?.data?.attrs?.name || node?.id || "");
}

function attachedBusNodeForNode(node, nodes) {
  const busName = String(node?.attrs?.bus || node?.data?.attrs?.bus || "");
  if (!busName) return null;
  return (nodes || []).find(
    (candidate) => candidate.component === "buses" && busNameForNode(candidate) === busName,
  ) || null;
}

function sideForAttachedNode(node, nodes, fallbackSide = "") {
  const busNode = attachedBusNodeForNode(node, nodes);
  if (!busNode) return "";
  return sideForBusConnection(busNode, node, fallbackSide);
}

function applyBusSideConstraintsToLayout(layoutChildren, nodes) {
  const proposedPositionsById = new Map(
    (layoutChildren || []).map((node) => [
      node.id,
      {
        x: Number(node.x || 0),
        y: Number(node.y || 0),
      },
    ]),
  );
  const proposedNodes = (nodes || []).map((node) => ({
    ...node,
    position: proposedPositionsById.get(node.id) || node.position,
  }));

  return (layoutChildren || []).map((layoutNode) => {
    const sourceNode = (nodes || []).find((node) => node.id === layoutNode.id);
    if (!sourceNode || sourceNode.component === "buses") return layoutNode;

    const busNode = attachedBusNodeForNode(sourceNode, proposedNodes);
    if (!busNode) return layoutNode;

    const busSide = layoutBusSide(sourceNode) || sideForAttachedNode(sourceNode, nodes);
    if (!busSide) return layoutNode;

    const proposedPosition = proposedPositionsById.get(layoutNode.id) || {
      x: Number(layoutNode.x || 0),
      y: Number(layoutNode.y || 0),
    };
    const proposedNode = {
      ...sourceNode,
      position: proposedPosition,
    };
    const busCenter = nodeCenter(busNode);
    const proposedCenter = nodeCenter(proposedNode);
    if (!busCenter || !proposedCenter) return layoutNode;
    const violatesSide =
      busSide === "left"
        ? proposedCenter.x >= busCenter.x
        : proposedCenter.x <= busCenter.x;
    if (!violatesSide) return layoutNode;

    return {
      ...layoutNode,
      x:
        Number(busNode.position?.x || 0) +
        (busSide === "left"
          ? -BUS_COMPONENT_HORIZONTAL_OFFSET_PX
          : BUS_COMPONENT_HORIZONTAL_OFFSET_PX),
    };
  });
}

function buildBusConnectionRouting(nodes, edges) {
  const nodeById = new Map((nodes || []).map((node) => [node.id, node]));
  const handlesByBusId = {};
  const handleGroups = new Map();

  const handleForNonBusEndpoint = (edge, endpoint) => {
    const nodeId = endpoint === "source" ? edge.source : edge.target;
    const otherNodeId = endpoint === "source" ? edge.target : edge.source;
    const node = nodeById.get(nodeId);
    const otherNode = nodeById.get(otherNodeId);
    const fallbackHandle = endpoint === "source" ? edge.sourceHandle : edge.targetHandle;
    if (!node || !otherNode || otherNode.component !== "buses") {
      return fallbackHandle;
    }
    const busSide = sideForBusConnection(otherNode, node, fallbackHandle);
    if (busSide === "top" || busSide === "bottom") {
      return fallbackHandle;
    }
    return handleForSide(fallbackHandle, oppositeSide(busSide));
  };

  const registerBusHandle = (edge, endpoint) => {
    const busNodeId = endpoint === "source" ? edge.source : edge.target;
    const otherNodeId = endpoint === "source" ? edge.target : edge.source;
    const busNode = nodeById.get(busNodeId);
    if (busNode?.component !== "buses") {
      return handleForNonBusEndpoint(edge, endpoint);
    }

    const otherNode = nodeById.get(otherNodeId);
    const handleType = endpoint === "source" ? "source" : "target";
    const fallbackHandle = endpoint === "source" ? edge.sourceHandle : edge.targetHandle;
    const side = sideForBusConnection(busNode, otherNode, fallbackHandle);
    const otherCenter = nodeCenter(otherNode);
    const handle = {
      id: `${side}-${handleType}-${safeHandleId(edge.id)}`,
      type: handleType,
      side,
      busNodeId,
      offsetPx: BUS_MIN_HEIGHT_PX / 2,
      sortAxis: side === "top" || side === "bottom" ? otherCenter?.x ?? 0 : otherCenter?.y ?? 0,
      sortIndex: handlesByBusId[busNodeId]?.length ?? 0,
    };
    handlesByBusId[busNodeId] = handlesByBusId[busNodeId] || [];
    handlesByBusId[busNodeId].push(handle);

    const groupKey = `${busNodeId}:${side}`;
    const group = handleGroups.get(groupKey) || [];
    group.push(handle);
    handleGroups.set(groupKey, group);
    return handle.id;
  };

  const routedEdges = (edges || []).map((edge) => {
    const routedEdge = { ...edge };
    routedEdge.sourceHandle = registerBusHandle(routedEdge, "source");
    routedEdge.targetHandle = registerBusHandle(routedEdge, "target");
    return routedEdge;
  });

  handleGroups.forEach((group) => {
    group.sort((left, right) => {
      const axisDelta = left.sortAxis - right.sortAxis;
      return Math.abs(axisDelta) > 1 ? axisDelta : left.sortIndex - right.sortIndex;
    });
    const count = group.length;
    const busNodeId = group[0]?.busNodeId;
    const busLength = busSymbolLengthForHandles(handlesByBusId[busNodeId] || []);
    const groupSpan = Math.max(0, count - 1) * BUS_CONNECTION_SPACING_PX;
    const startPosition = count === 1 ? busLength / 2 : (busLength - groupSpan) / 2;
    group.forEach((handle, index) => {
      handle.offsetPx = count === 1 ? startPosition : startPosition + index * BUS_CONNECTION_SPACING_PX;
    });
  });

  return {
    edges: routedEdges,
    handlesByBusId,
  };
}

function shouldRotateStepEdgeLabel(sourceY, targetY, sourcePosition, targetPosition) {
  const usesHorizontalHandles =
    (sourcePosition === Position.Left || sourcePosition === Position.Right) &&
    (targetPosition === Position.Left || targetPosition === Position.Right);
  return usesHorizontalHandles && Math.abs(sourceY - targetY) > EDGE_LABEL_VERTICAL_THRESHOLD_PX;
}

/**
 * Return a screen-space label offset that keeps text clear of the edge path.
 */
function edgeLabelOffset(rotateLabel) {
  return rotateLabel ? { x: 9, y: 0 } : { x: 0, y: -17 };
}

/**
 * Return whether an edge should render a midpoint component symbol.
 */
function shouldRenderEdgeSymbol(component) {
  return ["processes", "process", "transformers", "transformer"].includes(
    String(component || "").toLowerCase(),
  );
}

function SchematicStepEdge({
  id,
  sourceX,
  sourceY,
  sourcePosition,
  targetX,
  targetY,
  targetPosition,
  style = {},
  markerEnd,
  markerStart,
  label,
  data = {},
  selected,
}) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 0,
  });
  const rotateLabel = Boolean(label) && shouldRotateStepEdgeLabel(
    sourceY,
    targetY,
    sourcePosition,
    targetPosition,
  );
  const labelOffset = edgeLabelOffset(rotateLabel);
  const showEdgeSymbol = shouldRenderEdgeSymbol(data.component) && data.iconSrc;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        markerStart={markerStart}
        style={style}
      />
      {showEdgeSymbol ? (
        <EdgeLabelRenderer>
          <span
            className="schematic-edge-symbol"
            style={{
              "--edge-symbol-size": `${EDGE_SYMBOL_SIZE_PX}px`,
              position: "absolute",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 4,
              boxSizing: "content-box",
              width: `${EDGE_SYMBOL_SIZE_PX}px`,
              height: `${EDGE_SYMBOL_SIZE_PX}px`,
              padding: "3px",
              borderRadius: "4px",
              background: "transparent",
              color: "var(--gray-12)",
              pointerEvents: "none",
              transformOrigin: "center",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px) rotate(${rotateLabel ? 90 : 0}deg)`,
            }}
          >
            <img
              src={data.iconSrc}
              alt=""
              style={{
                flex: "0 0 auto",
                display: "block",
                width: `${EDGE_SYMBOL_SIZE_PX}px`,
                height: `${EDGE_SYMBOL_SIZE_PX}px`,
                maxWidth: `${EDGE_SYMBOL_SIZE_PX}px`,
                maxHeight: `${EDGE_SYMBOL_SIZE_PX}px`,
                objectFit: "contain",
              }}
            />
          </span>
        </EdgeLabelRenderer>
      ) : null}
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="schematic-edge-label"
            data-selected={selected ? "true" : "false"}
            style={{
              background: "transparent",
              boxShadow: "none",
              transform: `translate(-50%, -50%) translate(${labelX + labelOffset.x}px, ${labelY + labelOffset.y}px) rotate(${rotateLabel ? 90 : 0}deg)`,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

function SchematicNode({ data, selected }) {
  const updateNodeInternals = useUpdateNodeInternals();
  const symbolMeta = symbolMetaForComponent(data.component);
  const symbolHeight = Number(data.symbolHeight || symbolMeta.height);
  const busSymbolLength = Number(data.busSymbolLength || BUILDER_SYMBOL_META.bus.height);
  const busOrientation = layoutBusOrientation({ data });
  const handleSignature = (data.connectionHandles || [])
    .map((handle) => `${handle.id}:${handle.offsetPx}`)
    .join("|");

  useEffectReactFlowCanvas(() => {
    if (data.isBus) {
      updateNodeInternals(data.nodeId);
    }
  }, [busOrientation, busSymbolLength, data.isBus, data.nodeId, handleSignature, updateNodeInternals]);

  const busHandleOffset = (handle) => Number(handle.offsetPx || busSymbolLength / 2);
  const busHandlePosition = (side) => {
    if (side === "top") return Position.Top;
    if (side === "bottom") return Position.Bottom;
    return side === "left" ? Position.Left : Position.Right;
  };
  const busHandleStyle = (handle) => {
    const offsetPx = busHandleOffset(handle);
    if (handle.side === "top" || handle.side === "bottom") {
      return {
        left: `${offsetPx}px`,
        top: `${BUILDER_SYMBOL_META.bus.width / 2}px`,
        bottom: "auto",
        transform: "translate(-50%, -50%)",
      };
    }
    return {
      top: `${offsetPx}px`,
      left: "50%",
      transform: "translate(-50%, -50%)",
    };
  };
  const iconHandleTop = symbolHeight / 2;
  const leftContact = `${iconContactPercent(data.component, "left")}%`;
  const rightContact = `${iconContactPercent(data.component, "right")}%`;
  const leftHandleStyle = data.isBus
    ? undefined
    : { top: `${iconHandleTop}px`, left: leftContact, transform: "translate(-50%, -50%)" };
  const rightHandleStyle = data.isBus
    ? undefined
    : { top: `${iconHandleTop}px`, left: rightContact, right: "auto", transform: "translate(-50%, -50%)" };
  const showConnectorTerminals = !data.isBus && hasConnectorTerminal(data.component);
  const connectorSides = connectorTerminalSides(data.component);
  const symbolStyle = { width: "100%", height: "100%" };
  const shouldRotateSymbol = shouldRotateIconForBusSide(data.component, data.busSide);
  const symbolLayerStyle = {
    width: `${symbolMeta.width}px`,
    height: `${symbolHeight}px`,
    transform: shouldRotateSymbol ? "rotate(180deg)" : "none",
  };
  const terminalElements = showConnectorTerminals ? (
    <>
      {connectorSides.includes("left") ? (
        <span
          className="schematic-terminal schematic-terminal-left"
          style={connectorTerminalStyleForComponent(data.component, "left", iconHandleTop)}
        />
      ) : null}
      {connectorSides.includes("right") ? (
        <span
          className="schematic-terminal schematic-terminal-right"
          style={connectorTerminalStyleForComponent(data.component, "right", iconHandleTop)}
        />
      ) : null}
    </>
  ) : null;

  return (
    <div
      className="schematic-node"
      data-is-bus={data.isBus ? "true" : "false"}
      data-bus-orientation={data.isBus ? busOrientation : ""}
      data-selected={selected ? "true" : "false"}
      data-layout-locked={data.layoutLocked ? "true" : "false"}
      data-branch-armed={data.branchArmed && data.isBus ? "true" : "false"}
      data-connection-hover={data.connectionDrag && data.isBus && data.hoverBusId === data.nodeId ? "true" : "false"}
      data-branch-start={data.branchBus0NodeId === data.nodeId ? "true" : "false"}
      title={`${data.label} (${data.component})`}
      style={
        data.canvasVisible
          ? undefined
          : { opacity: 0, pointerEvents: "none" }
      }
    >
      <Handle className="schematic-node-handle" id="left-target" type="target" position={Position.Left} style={leftHandleStyle} />
      <Handle className="schematic-node-handle" id="left-source" type="source" position={Position.Left} style={leftHandleStyle} />
      <Handle className="schematic-node-handle" id="right-target" type="target" position={Position.Right} style={rightHandleStyle} />
      <Handle className="schematic-node-handle" id="right-source" type="source" position={Position.Right} style={rightHandleStyle} />
      {(data.connectionHandles || []).map((handle) => (
        <Handle
          className="schematic-node-handle schematic-node-bus-handle"
          id={handle.id}
          key={handle.id}
          type={handle.type}
          position={busHandlePosition(handle.side)}
          style={busHandleStyle(handle)}
        />
      ))}
      {data.isBus ? (
        <span
          className="schematic-bus-symbol"
          style={
            busOrientation === "horizontal"
              ? {
                  width: `${busSymbolLength}px`,
                  height: "3px",
                  minHeight: "3px",
                  marginTop: `${(BUILDER_SYMBOL_META.bus.width - 3) / 2}px`,
                }
              : { height: `${busSymbolLength}px` }
          }
        />
      ) : data.iconSvg ? (
        <span className="schematic-symbol-layer" style={symbolLayerStyle}>
          {terminalElements}
          <span
            className="schematic-node-symbol"
            style={symbolStyle}
            dangerouslySetInnerHTML={{ __html: data.iconSvg }}
          />
        </span>
      ) : (
        <span className="schematic-symbol-layer" style={symbolLayerStyle}>
          {terminalElements}
          <img className="schematic-node-symbol" src={data.iconSrc} alt="" style={symbolStyle} />
        </span>
      )}
      <span className="schematic-node-label">{data.label}</span>
    </div>
  );
}

const nodeTypes = { schematic: SchematicNode };
const edgeTypes = { step: SchematicStepEdge };

const CANVAS_CONTEXT_MENU_ITEMS = [
  {
    id: "select",
    label: "Select",
    targetKinds: ["component", "branch"],
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
    targetKinds: ["component", "branch", "selection"],
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
    targetKinds: ["component", "branch", "region"],
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
  return contextMenu.targetKind === "branch" ? "Branch" : "Component";
}

function normalizeSelectionRect(start, current) {
  const x = Math.min(start.x, current.x);
  const y = Math.min(start.y, current.y);
  const width = Math.abs(current.x - start.x);
  const height = Math.abs(current.y - start.y);
  return { x, y, width, height, right: x + width, bottom: y + height };
}

function rectsIntersect(left, right) {
  return !(
    left.right < right.x ||
    left.x > right.right ||
    left.bottom < right.y ||
    left.y > right.bottom
  );
}

function localPointFromMouseEvent(event, element) {
  const bounds = element?.getBoundingClientRect();
  if (!bounds) return { x: event.clientX, y: event.clientY };
  return {
    x: event.clientX - bounds.left,
    y: event.clientY - bounds.top,
  };
}

function clampContextMenuPosition(position, wrapper) {
  const bounds = wrapper?.getBoundingClientRect();
  if (!bounds) return position;
  const menuWidth = 180;
  const menuHeight = 104;
  return {
    x: Math.max(8, Math.min(position.x, bounds.width - menuWidth - 8)),
    y: Math.max(8, Math.min(position.y, bounds.height - menuHeight - 8)),
  };
}

function flowBoundsFromLocalRect(rect, reactFlow, wrapper) {
  const wrapperBounds = wrapper?.getBoundingClientRect();
  const screenPoint = (point) =>
    wrapperBounds
      ? { x: wrapperBounds.left + point.x, y: wrapperBounds.top + point.y }
      : point;
  const topLeft =
    typeof reactFlow.screenToFlowPosition === "function"
      ? reactFlow.screenToFlowPosition(screenPoint({ x: rect.x, y: rect.y }))
      : typeof reactFlow.project === "function"
        ? reactFlow.project({ x: rect.x, y: rect.y })
        : { x: rect.x, y: rect.y };
  const bottomRight =
    typeof reactFlow.screenToFlowPosition === "function"
      ? reactFlow.screenToFlowPosition(
          screenPoint({ x: rect.right, y: rect.bottom }),
        )
      : typeof reactFlow.project === "function"
        ? reactFlow.project({ x: rect.right, y: rect.bottom })
        : { x: rect.right, y: rect.bottom };
  return {
    x: Math.min(topLeft.x, bottomRight.x),
    y: Math.min(topLeft.y, bottomRight.y),
    width: Math.abs(bottomRight.x - topLeft.x),
    height: Math.abs(bottomRight.y - topLeft.y),
  };
}

function localRectFromFlowBounds(region, reactFlow, wrapper) {
  const wrapperBounds = wrapper?.getBoundingClientRect();
  const x = Number(region?.x || 0);
  const y = Number(region?.y || 0);
  const width = Number(region?.width || 0);
  const height = Number(region?.height || 0);
  const topLeft =
    typeof reactFlow.flowToScreenPosition === "function"
      ? reactFlow.flowToScreenPosition({ x, y })
      : { x, y };
  const bottomRight =
    typeof reactFlow.flowToScreenPosition === "function"
      ? reactFlow.flowToScreenPosition({ x: x + width, y: y + height })
      : { x: x + width, y: y + height };
  const offsetX = wrapperBounds ? wrapperBounds.left : 0;
  const offsetY = wrapperBounds ? wrapperBounds.top : 0;
  return {
    x: Math.min(topLeft.x, bottomRight.x) - offsetX,
    y: Math.min(topLeft.y, bottomRight.y) - offsetY,
    width: Math.abs(bottomRight.x - topLeft.x),
    height: Math.abs(bottomRight.y - topLeft.y),
  };
}

function normalizeRegionColor(color) {
  const value = String(color || "").trim().toLowerCase();
  return REGION_COLOR_OPTIONS.some((option) => option.color === value)
    ? value
    : DEFAULT_REGION_COLOR;
}

function regionStyleVars(region, active = false) {
  const color = normalizeRegionColor(region?.color);
  return {
    "--region-color": color,
    "--region-fill-percent": active ? "24%" : "16%",
    "--region-border-width": active ? "2px" : "1px",
  };
}

function offsetRegionBounds(region, delta) {
  return {
    x: Number(region?.x || 0) + Number(delta?.x || 0),
    y: Number(region?.y || 0) + Number(delta?.y || 0),
    width: Number(region?.width || 0),
    height: Number(region?.height || 0),
  };
}

function resizeRegionBounds(region, handle, point) {
  const minSize = 16;
  const left = Number(region?.x || 0);
  const top = Number(region?.y || 0);
  const right = left + Number(region?.width || 0);
  const bottom = top + Number(region?.height || 0);
  const next = { x: left, y: top, width: right - left, height: bottom - top };

  if (handle.includes("w")) {
    next.x = Math.min(point.x, right - minSize);
    next.width = right - next.x;
  }
  if (handle.includes("e")) {
    next.width = Math.max(minSize, point.x - left);
  }
  if (handle.includes("n")) {
    next.y = Math.min(point.y, bottom - minSize);
    next.height = bottom - next.y;
  }
  if (handle.includes("s")) {
    next.height = Math.max(minSize, point.y - top);
  }

  return next;
}

function flowRectForRegion(region) {
  const x = Number(region?.x || 0);
  const y = Number(region?.y || 0);
  const width = Number(region?.width || 0);
  const height = Number(region?.height || 0);
  return { x, y, width, height, right: x + width, bottom: y + height };
}

function flowNodeRect(node) {
  const width = Number.parseFloat(node.style?.width) || 56;
  const height = Number.parseFloat(node.style?.height) || 56;
  const x = Number(node?.position?.x || 0);
  const y = Number(node?.position?.y || 0);
  return { x, y, right: x + width, bottom: y + height };
}

function flowRectsIntersect(left, right) {
  return !(
    left.right < right.x ||
    left.x > right.right ||
    left.bottom < right.y ||
    left.y > right.bottom
  );
}

function zoomToRegionBounds(region, reactFlow, wrapper) {
  const bounds = {
    x: Number(region?.x || 0),
    y: Number(region?.y || 0),
    width: Number(region?.width || 0),
    height: Number(region?.height || 0),
  };
  if (bounds.width <= 0 || bounds.height <= 0) return;
  if (typeof reactFlow.fitBounds === "function") {
    reactFlow.fitBounds(bounds, { padding: 0.18, duration: 450 });
    return;
  }
  if (typeof reactFlow.setCenter !== "function") return;
  const viewportWidth = wrapper?.clientWidth || 1;
  const viewportHeight = wrapper?.clientHeight || 1;
  const paddedWidth = bounds.width * 1.36;
  const paddedHeight = bounds.height * 1.36;
  const zoom = Math.max(
    0.1,
    Math.min(
      2,
      viewportWidth / Math.max(paddedWidth, 1),
      viewportHeight / Math.max(paddedHeight, 1),
    ),
  );
  reactFlow.setCenter(
    bounds.x + bounds.width / 2,
    bounds.y + bounds.height / 2,
    { zoom, duration: 450 },
  );
}

function localNodeRect(node, reactFlow, wrapper) {
  const wrapperBounds = wrapper?.getBoundingClientRect();
  const width = Number.parseFloat(node.style?.width) || 56;
  const height = Number.parseFloat(node.style?.height) || 56;
  const screenPosition =
    typeof reactFlow.flowToScreenPosition === "function"
      ? reactFlow.flowToScreenPosition(node.position)
      : node.position;
  const x = wrapperBounds && typeof reactFlow.flowToScreenPosition === "function"
    ? screenPosition.x - wrapperBounds.left
    : screenPosition.x;
  const y = wrapperBounds && typeof reactFlow.flowToScreenPosition === "function"
    ? screenPosition.y - wrapperBounds.top
    : screenPosition.y;
  return { x, y, right: x + width, bottom: y + height };
}

function edgeElementForId(wrapper, edgeId) {
  const edgeElements = Array.from(wrapper?.querySelectorAll(".react-flow__edge") || []);
  return edgeElements.find((element) => element.getAttribute("data-id") === edgeId) || null;
}

function svgPointToLocal(svg, point, wrapperBounds) {
  if (!svg || !wrapperBounds) return null;
  const svgPoint = svg.createSVGPoint();
  svgPoint.x = point.x;
  svgPoint.y = point.y;
  const matrix = svg.getScreenCTM();
  if (!matrix) return null;
  const screenPoint = svgPoint.matrixTransform(matrix);
  return {
    x: screenPoint.x - wrapperBounds.left,
    y: screenPoint.y - wrapperBounds.top,
  };
}

function edgePathIntersectsRect(wrapper, edge, rect) {
  if (!isBranchEdgeComponent(edge.component)) return false;
  const edgeElement = edgeElementForId(wrapper, edge.id);
  const escapedId =
    typeof window !== "undefined" && window.CSS?.escape
      ? window.CSS.escape(edge.id)
      : String(edge.id).replace(/"/g, '\\"');
  const path =
    edgeElement?.querySelector(".react-flow__edge-path") ||
    wrapper?.querySelector(`path.react-flow__edge-path[id="${escapedId}"]`);
  const wrapperBounds = wrapper?.getBoundingClientRect();
  const svg = path?.ownerSVGElement;
  if (!path || !wrapperBounds || !svg || typeof path.getTotalLength !== "function") {
    return false;
  }
  let length = 0;
  try {
    length = path.getTotalLength();
  } catch {
    return false;
  }
  const sampleCount = Math.max(16, Math.ceil(length / 20));
  for (let index = 0; index <= sampleCount; index += 1) {
    const rawPoint = path.getPointAtLength((length * index) / sampleCount);
    const localPoint = svgPointToLocal(svg, rawPoint, wrapperBounds);
    if (
      localPoint &&
      localPoint.x >= rect.x &&
      localPoint.x <= rect.right &&
      localPoint.y >= rect.y &&
      localPoint.y <= rect.bottom
    ) {
      return true;
    }
  }
  const midpoint = svgPointToLocal(svg, path.getPointAtLength(length / 2), wrapperBounds);
  return Boolean(
    midpoint &&
      midpoint.x >= rect.x &&
      midpoint.x <= rect.right &&
      midpoint.y >= rect.y &&
      midpoint.y <= rect.bottom,
  );
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

function CanvasInner({
  nodes = [],
  edges = [],
  regions = [],
  routeVersion = 0,
  fitViewVersion = 0,
  armedComponent = "",
  armedBranchComponent = "",
  branchBus0NodeId = "",
  rectangleSelectionArmed = false,
  onNodeDrop,
  onNodeSelect,
  onBranchBusClick,
  onEdgeSelect,
  onNodesUpdate,
  onRouteComplete,
  onCanvasContextMenuAction,
}) {
  const flowWrapperRef = useRefReactFlowCanvas(null);
  const lastRoutedVersionRef = useRefReactFlowCanvas(0);
  const lastHandledFitViewVersionRef = useRefReactFlowCanvas(0);
  const suppressNextPaneClickRef = useRefReactFlowCanvas(false);
  const cancelRegionRenameRef = useRefReactFlowCanvas(false);
  const [hoverBusId, setHoverBusId] = useStateReactFlowCanvas("");
  const [dragComponent, setDragComponent] = useStateReactFlowCanvas("");
  const [dragBusSidePreview, setDragBusSidePreview] = useStateReactFlowCanvas({
    nodeId: "",
    side: "",
  });
  const [contextMenu, setContextMenu] = useStateReactFlowCanvas(null);
  const [selectionDrag, setSelectionDrag] = useStateReactFlowCanvas(null);
  const [armedRegionDrag, setArmedRegionDrag] = useStateReactFlowCanvas(null);
  const [regionDrag, setRegionDrag] = useStateReactFlowCanvas(null);
  const [armedRegionResize, setArmedRegionResize] = useStateReactFlowCanvas(null);
  const [regionResize, setRegionResize] = useStateReactFlowCanvas(null);
  const [editingRegionId, setEditingRegionId] = useStateReactFlowCanvas("");
  const [editingRegionName, setEditingRegionName] = useStateReactFlowCanvas("");
  const [viewportRevision, setViewportRevision] = useStateReactFlowCanvas(0);
  const reactFlow = useReactFlow();

  const isConnectionDrag = Boolean(
    isAttachableComponent(dragComponent) && !armedBranchComponent,
  );

  const edgeRouting = useMemoReactFlowCanvas(
    () => {
      const renderedEdges = (edges || []).map((edge) => ({
        ...edge,
        type: "step",
      }));
      return buildBusConnectionRouting(nodes, renderedEdges);
    },
    [
      edges,
      nodes,
    ],
  );

  const summarizedRegionNodeIds = useMemoReactFlowCanvas(() => {
    const nodeIds = new Set();
    (regions || []).forEach((region) => {
      if (!region?.summary) return;
      (region.summary_node_ids || []).forEach((nodeId) => {
        if (nodeId) nodeIds.add(String(nodeId));
      });
    });
    return nodeIds;
  }, [regions]);

  const flowNodes = useMemoReactFlowCanvas(
    () =>
      nodes.filter((node) => {
        const canvasVisible = isCanvasVisible(node);
        return (
          !node.hidden &&
          !isBranchEdgeComponent(node.component) &&
          (canvasVisible || node.component === "buses" || summarizedRegionNodeIds.has(node.id))
        );
      }).map((node) => {
        const canvasVisible = isCanvasVisible(node);
        const meta = symbolMetaForComponent(node.component);
        const label = displayNameForNode(node);
        const connectionHandles = node.component === "buses" ? edgeRouting.handlesByBusId[node.id] || [] : [];
        const visualMeta = visualMetaForNode(node, connectionHandles);
        const busSymbolLength = node.component === "buses" ? busSymbolLengthForHandles(connectionHandles) : meta.height;
        return {
          id: node.id,
          type: "schematic",
          position: node.position,
          style: {
            width: `${visualMeta.width}px`,
            height: `${visualMeta.height + BUS_LABEL_HEIGHT}px`,
          },
          data: {
            nodeId: node.id,
            label,
            component: node.component,
            attrs: node.attrs || {},
            layout: node.layout || {},
            layoutLocked: Boolean(node.layout?.locked),
            canvasVisible,
            busSide:
              dragBusSidePreview.nodeId === node.id
                ? dragBusSidePreview.side
                : layoutBusSide(node),
            isBus: node.component === "buses",
            branchArmed: Boolean(armedBranchComponent),
            connectionDrag: isConnectionDrag,
            hoverBusId: isConnectionDrag ? hoverBusId : "",
            branchBus0NodeId,
            symbolHeight: meta.height,
            busSymbolLength,
            connectionHandles,
            iconSrc: node.icon_src,
            iconSvg: node.icon_svg,
            onSelect: onNodeSelect,
            onBranchBusClick,
          },
        };
      }),
    [
      armedBranchComponent,
      branchBus0NodeId,
      edgeRouting.handlesByBusId,
      hoverBusId,
      isConnectionDrag,
      dragBusSidePreview,
      nodes,
      onBranchBusClick,
      onNodeSelect,
      summarizedRegionNodeIds,
    ],
  );

  const lockedPositionsById = useMemoReactFlowCanvas(() => {
    const positionsById = {};
    (nodes || []).forEach((node) => {
      if (!node?.hidden && node?.layout?.locked && node.position) {
        positionsById[node.id] = {
          x: Number(node.position.x || 0),
          y: Number(node.position.y || 0),
        };
      }
    });
    return positionsById;
  }, [nodes]);

  const flowEdges = useMemoReactFlowCanvas(
    () => {
      return edgeRouting.edges.map((edge) => ({
        ...edge,
        className: isBranchEdgeComponent(edge.component)
          ? "schematic-branch-edge"
          : "",
        data: {
          ...(edge.data || {}),
          component: edge.component || "",
          iconSrc: edge.icon_src || "",
          iconSvg: edge.icon_svg || "",
        },
      }));
    },
    [edgeRouting.edges],
  );

  useEffectReactFlowCanvas(() => {
    if (!routeVersion || flowNodes.length === 0) return;
    if (lastRoutedVersionRef.current === routeVersion) return;
    lastRoutedVersionRef.current = routeVersion;

    let cancelled = false;

    async function routeWithElk() {
      const elkModule = await import("elkjs/lib/elk.bundled.js");
      const ELKClass = elkModule && elkModule.default ? elkModule.default : elkModule;
      const elk = new ELKClass();
      const layout = await elk.layout({
        id: "pypsa-network",
        layoutOptions: {
          "elk.algorithm": "layered",
          "elk.direction": "RIGHT",
          "elk.edgeRouting": "ORTHOGONAL",
          "elk.spacing.nodeNode": "50",
          "elk.layered.spacing.nodeNodeBetweenLayers": "140",
          "elk.layered.spacing.edgeNodeBetweenLayers": "45",
        },
        children: flowNodes.map((node) => ({
          id: node.id,
          width: Number.parseFloat(node.style?.width) || 56,
          height: Number.parseFloat(node.style?.height) || 56,
        })),
        edges: flowEdges
          .filter((edge) => edge.source && edge.target)
          .map((edge) => ({
            id: edge.id,
            sources: [edge.source],
            targets: [edge.target],
          })),
      });

      if (cancelled || !Array.isArray(layout.children)) return;

      const constrainedChildren = applyBusSideConstraintsToLayout(layout.children, nodes);
      onNodesUpdate?.(
        constrainedChildren.map((node) => ({
          id: node.id,
          position: lockedPositionsById[node.id] || {
            x: Number(node.x || 0),
            y: Number(node.y || 0),
          },
        })),
      );

      window.setTimeout(() => reactFlow.fitView?.({ padding: 0.18 }), 100);
      window.setTimeout(() => onRouteComplete?.(), 150);
    }

    routeWithElk().catch((error) => {
      console.error("ELK auto route failed", error);
      onRouteComplete?.();
    });

    return () => {
      cancelled = true;
    };
  }, [
    flowEdges,
    flowNodes,
    lockedPositionsById,
    nodes,
    onNodesUpdate,
    onRouteComplete,
    reactFlow,
    routeVersion,
  ]);

  const flowPositionFromEvent = useCallbackReactFlowCanvas(
    (event) => {
      const bounds = flowWrapperRef.current?.getBoundingClientRect();
      const point = bounds
        ? { x: event.clientX - bounds.left, y: event.clientY - bounds.top }
        : { x: event.clientX, y: event.clientY };
      if (typeof reactFlow.project === "function") {
        return reactFlow.project(point);
      }
      if (typeof reactFlow.screenToFlowPosition === "function") {
        return reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      }
      return point;
    },
    [reactFlow],
  );

  const renderedRegions = useMemoReactFlowCanvas(
    () =>
      (regions || [])
        .filter((region) => Number(region?.width || 0) > 0 && Number(region?.height || 0) > 0)
        .map((region) => {
          const previewRegion =
            regionDrag?.regionId === region.id
              ? { ...region, ...offsetRegionBounds(regionDrag.originalRegion, regionDrag.delta) }
              : regionResize?.regionId === region.id
                ? { ...region, ...regionResize.bounds }
              : region;
          return {
            ...previewRegion,
            rect: localRectFromFlowBounds(previewRegion, reactFlow, flowWrapperRef.current),
            isArmedForDrag: armedRegionDrag?.regionId === region.id,
            isDragging: regionDrag?.regionId === region.id,
            isArmedForResize: armedRegionResize?.regionId === region.id,
            isResizing: regionResize?.regionId === region.id,
          };
        }),
    [armedRegionDrag, armedRegionResize, regions, reactFlow, regionDrag, regionResize, viewportRevision],
  );

  useEffectReactFlowCanvas(() => {
    const wrapper = flowWrapperRef.current;
    if (!wrapper) return undefined;
    const bumpViewportRevision = () =>
      setViewportRevision((current) => (current + 1) % 1000000);
    const pane = wrapper.querySelector(".react-flow__viewport");
    const observer = new MutationObserver(bumpViewportRevision);
    if (pane) {
      observer.observe(pane, { attributes: true, attributeFilter: ["style", "transform"] });
    }
    window.addEventListener("resize", bumpViewportRevision);
    bumpViewportRevision();
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", bumpViewportRevision);
    };
  }, [flowNodes.length, regions]);

  const contextMenuPositionFromEvent = useCallbackReactFlowCanvas((event) => {
    const bounds = flowWrapperRef.current?.getBoundingClientRect();
    if (!bounds) {
      return { x: event.clientX, y: event.clientY };
    }
    const menuWidth = 180;
    const menuHeight = 168;
    return {
      x: Math.max(8, Math.min(event.clientX - bounds.left, bounds.width - menuWidth - 8)),
      y: Math.max(8, Math.min(event.clientY - bounds.top, bounds.height - menuHeight - 8)),
    };
  }, []);

  const closeContextMenu = useCallbackReactFlowCanvas(() => {
    setContextMenu(null);
  }, []);

  const finishRectangleSelection = useCallbackReactFlowCanvas(() => {
    onCanvasContextMenuAction?.({
      action_id: "finish_rectangle_selection",
      target_kind: "selection",
      node_ids: [],
    });
  }, [onCanvasContextMenuAction]);

  useEffectReactFlowCanvas(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        if (editingRegionId) {
          setEditingRegionId("");
          setEditingRegionName("");
        }
        setArmedRegionDrag(null);
        setRegionDrag(null);
        setArmedRegionResize(null);
        setRegionResize(null);
        closeContextMenu();
        if (rectangleSelectionArmed || selectionDrag) {
          setSelectionDrag(null);
          finishRectangleSelection();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [
    closeContextMenu,
    editingRegionId,
    finishRectangleSelection,
    rectangleSelectionArmed,
    selectionDrag,
  ]);

  const nodeIdsInsideSelectionRect = useCallbackReactFlowCanvas(
    (rect) => {
      const wrapper = flowWrapperRef.current;
      if (!wrapper) return [];
      return flowNodes
        .filter((node) => node?.data?.canvasVisible !== false)
        .filter((node) => rectsIntersect(localNodeRect(node, reactFlow, wrapper), rect))
        .map((node) => node.id);
    },
    [flowNodes, reactFlow],
  );

  const branchNodeIdsCutBySelectionRect = useCallbackReactFlowCanvas(
    (rect) => {
      const wrapper = flowWrapperRef.current;
      if (!wrapper) return [];
      return flowEdges
        .filter((edge) => edgePathIntersectsRect(wrapper, edge, rect))
        .map((edge) => edge?.attrs?.component_node_id || "")
        .filter(Boolean);
    },
    [flowEdges],
  );

  const openSelectionContextMenu = useCallbackReactFlowCanvas(
    (rect, nodeIds) => {
      if (!nodeIds.length) return;
      const regionBounds = flowBoundsFromLocalRect(
        rect,
        reactFlow,
        flowWrapperRef.current,
      );
      const position = clampContextMenuPosition(
        { x: rect.right + 8, y: rect.bottom + 8 },
        flowWrapperRef.current,
      );
      setContextMenu({
        targetKind: "selection",
        targetId: "rectangle-selection",
        nodeIds,
        regionBounds,
        x: position.x,
        y: position.y,
      });
    },
    [reactFlow],
  );

  const handleSelectionMouseDownCapture = useCallbackReactFlowCanvas(
    (event) => {
      if (!rectangleSelectionArmed || event.button !== 0) return;
      if (event.target?.closest?.(".canvas-context-menu")) return;
      event.preventDefault();
      event.stopPropagation();
      closeContextMenu();
      const point = localPointFromMouseEvent(event, flowWrapperRef.current);
      setSelectionDrag({ start: point, current: point });
    },
    [closeContextMenu, rectangleSelectionArmed],
  );

  const handleSelectionMouseMoveCapture = useCallbackReactFlowCanvas(
    (event) => {
      if (!selectionDrag) return;
      event.preventDefault();
      event.stopPropagation();
      setSelectionDrag((current) =>
        current
          ? {
              ...current,
              current: localPointFromMouseEvent(event, flowWrapperRef.current),
            }
          : current,
      );
    },
    [selectionDrag],
  );

  const completeSelectionDrag = useCallbackReactFlowCanvas(
    (event) => {
      if (!selectionDrag) return;
      event.preventDefault();
      event.stopPropagation();
      const finalPoint = localPointFromMouseEvent(event, flowWrapperRef.current);
      const rect = normalizeSelectionRect(selectionDrag.start, finalPoint);
      setSelectionDrag(null);
      finishRectangleSelection();
      suppressNextPaneClickRef.current = true;
      if (rect.width < 4 || rect.height < 4) return;
      const selectedNodeIds = [
        ...nodeIdsInsideSelectionRect(rect),
        ...branchNodeIdsCutBySelectionRect(rect),
      ];
      const uniqueNodeIds = Array.from(new Set(selectedNodeIds));
      openSelectionContextMenu(rect, uniqueNodeIds);
    },
    [
      branchNodeIdsCutBySelectionRect,
      finishRectangleSelection,
      nodeIdsInsideSelectionRect,
      openSelectionContextMenu,
      selectionDrag,
    ],
  );

  const nodeIdsInsideFlowRegion = useCallbackReactFlowCanvas(
    (region) => {
      const regionRect = flowRectForRegion(region);
      return flowNodes
        .filter((node) => node?.data?.canvasVisible !== false)
        .filter((node) => flowRectsIntersect(flowNodeRect(node), regionRect))
        .map((node) => node.id);
    },
    [flowNodes],
  );

  const handleRegionMouseDown = useCallbackReactFlowCanvas(
    (event, region) => {
      if (event.button !== 0) return;
      if (armedRegionResize) return;
      if (!armedRegionDrag || armedRegionDrag.regionId !== region.id) return;
      event.preventDefault();
      event.stopPropagation();
      closeContextMenu();
      const startPoint = flowPositionFromEvent(event);
      const capturedNodeIds =
        armedRegionDrag.mode === "with_components"
          ? nodeIdsInsideFlowRegion(region)
          : [];
      const capturedNodePositions = {};
      flowNodes.forEach((node) => {
        if (!capturedNodeIds.includes(node.id)) return;
        capturedNodePositions[node.id] = {
          x: Number(node.position?.x || 0),
          y: Number(node.position?.y || 0),
        };
      });
      setRegionDrag({
        regionId: region.id,
        mode: armedRegionDrag.mode,
        startPoint,
        originalRegion: {
          x: Number(region.x || 0),
          y: Number(region.y || 0),
          width: Number(region.width || 0),
          height: Number(region.height || 0),
        },
        delta: { x: 0, y: 0 },
        capturedNodeIds,
        capturedNodePositions,
      });
    },
    [
      armedRegionDrag,
      armedRegionResize,
      closeContextMenu,
      flowNodes,
      flowPositionFromEvent,
      nodeIdsInsideFlowRegion,
    ],
  );

  const handleRegionDragMove = useCallbackReactFlowCanvas(
    (event) => {
      if (!regionDrag) return;
      event.preventDefault();
      event.stopPropagation();
      const point = flowPositionFromEvent(event);
      setRegionDrag((current) =>
        current
          ? {
              ...current,
              delta: {
                x: point.x - current.startPoint.x,
                y: point.y - current.startPoint.y,
              },
            }
          : current,
      );
    },
    [flowPositionFromEvent, regionDrag],
  );

  const completeRegionDrag = useCallbackReactFlowCanvas(
    (event) => {
      if (!regionDrag) return;
      event.preventDefault();
      event.stopPropagation();
      const point = flowPositionFromEvent(event);
      const delta = {
        x: point.x - regionDrag.startPoint.x,
        y: point.y - regionDrag.startPoint.y,
      };
      const nextBounds = offsetRegionBounds(regionDrag.originalRegion, delta);
      const finalRect = flowRectForRegion(nextBounds);
      const finalLockNodeIds = flowNodes
        .filter((node) => node?.data?.canvasVisible !== false)
        .filter((node) => {
          if (
            regionDrag.mode === "with_components" &&
            regionDrag.capturedNodeIds.includes(node.id)
          ) {
            const position = regionDrag.capturedNodePositions[node.id] || node.position;
            const width = Number.parseFloat(node.style?.width) || 56;
            const height = Number.parseFloat(node.style?.height) || 56;
            return flowRectsIntersect(
              {
                x: Number(position.x || 0) + delta.x,
                y: Number(position.y || 0) + delta.y,
                right: Number(position.x || 0) + delta.x + width,
                bottom: Number(position.y || 0) + delta.y + height,
              },
              finalRect,
            );
          }
          return flowRectsIntersect(flowNodeRect(node), finalRect);
        })
        .map((node) => node.id);
      const nodeUpdates =
        regionDrag.mode === "with_components"
          ? regionDrag.capturedNodeIds.map((nodeId) => {
              const position = regionDrag.capturedNodePositions[nodeId] || { x: 0, y: 0 };
              return {
                id: nodeId,
                position: {
                  x: Number(position.x || 0) + delta.x,
                  y: Number(position.y || 0) + delta.y,
                },
              };
            })
          : [];
      onCanvasContextMenuAction?.({
        action_id: "move_region",
        target_kind: "region",
        region_id: regionDrag.regionId,
        region_bounds: nextBounds,
        node_updates: nodeUpdates,
        lock_node_ids: Array.from(
          new Set([
            ...finalLockNodeIds,
            ...(regionDrag.mode === "with_components" ? regionDrag.capturedNodeIds : []),
          ]),
        ),
      });
      setRegionDrag(null);
      setArmedRegionDrag(null);
    },
    [
      flowPositionFromEvent,
      onCanvasContextMenuAction,
      regionDrag,
      flowNodes,
    ],
  );

  const handleRegionResizeMouseDown = useCallbackReactFlowCanvas(
    (event, region, handle) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      closeContextMenu();
      setArmedRegionDrag(null);
      const point = flowPositionFromEvent(event);
      const originalRegion = {
        x: Number(region.x || 0),
        y: Number(region.y || 0),
        width: Number(region.width || 0),
        height: Number(region.height || 0),
      };
      setRegionResize({
        regionId: region.id,
        handle,
        originalRegion,
        bounds: resizeRegionBounds(originalRegion, handle, point),
      });
    },
    [closeContextMenu, flowPositionFromEvent],
  );

  const handleRegionResizeMove = useCallbackReactFlowCanvas(
    (event) => {
      if (!regionResize) return;
      event.preventDefault();
      event.stopPropagation();
      const point = flowPositionFromEvent(event);
      setRegionResize((current) =>
        current
          ? {
              ...current,
              bounds: resizeRegionBounds(current.originalRegion, current.handle, point),
            }
          : current,
      );
    },
    [flowPositionFromEvent, regionResize],
  );

  const completeRegionResize = useCallbackReactFlowCanvas(
    (event) => {
      if (!regionResize) return;
      event.preventDefault();
      event.stopPropagation();
      const point = flowPositionFromEvent(event);
      const nextBounds = resizeRegionBounds(
        regionResize.originalRegion,
        regionResize.handle,
        point,
      );
      const finalRect = flowRectForRegion(nextBounds);
      const finalLockNodeIds = flowNodes
        .filter((node) => node?.data?.canvasVisible !== false)
        .filter((node) => flowRectsIntersect(flowNodeRect(node), finalRect))
        .map((node) => node.id);
      onCanvasContextMenuAction?.({
        action_id: "move_region",
        target_kind: "region",
        region_id: regionResize.regionId,
        region_bounds: nextBounds,
        node_updates: [],
        lock_node_ids: Array.from(new Set(finalLockNodeIds)),
      });
      setRegionResize(null);
      setArmedRegionResize(null);
    },
    [flowNodes, flowPositionFromEvent, onCanvasContextMenuAction, regionResize],
  );

  useEffectReactFlowCanvas(() => {
    if (!selectionDrag) return undefined;
    window.addEventListener("mousemove", handleSelectionMouseMoveCapture);
    window.addEventListener("mouseup", completeSelectionDrag);
    return () => {
      window.removeEventListener("mousemove", handleSelectionMouseMoveCapture);
      window.removeEventListener("mouseup", completeSelectionDrag);
    };
  }, [
    completeSelectionDrag,
    handleSelectionMouseMoveCapture,
    selectionDrag,
  ]);

  useEffectReactFlowCanvas(() => {
    if (!regionDrag) return undefined;
    window.addEventListener("mousemove", handleRegionDragMove);
    window.addEventListener("mouseup", completeRegionDrag);
    return () => {
      window.removeEventListener("mousemove", handleRegionDragMove);
      window.removeEventListener("mouseup", completeRegionDrag);
    };
  }, [
    completeRegionDrag,
    handleRegionDragMove,
    regionDrag,
  ]);

  useEffectReactFlowCanvas(() => {
    if (!regionResize) return undefined;
    window.addEventListener("mousemove", handleRegionResizeMove);
    window.addEventListener("mouseup", completeRegionResize);
    return () => {
      window.removeEventListener("mousemove", handleRegionResizeMove);
      window.removeEventListener("mouseup", completeRegionResize);
    };
  }, [
    completeRegionResize,
    handleRegionResizeMove,
    regionResize,
  ]);

  useEffectReactFlowCanvas(() => {
    if (!fitViewVersion) return;
    if (lastHandledFitViewVersionRef.current === fitViewVersion) return;
    if (!nodes.length) return;
    let cancelled = false;

    const hasDrawableNodes = () => {
      if (typeof reactFlow.getNodes === "function") {
        return (reactFlow.getNodes() || []).length > 0;
      }
      return flowNodes.length > 0;
    };

    const runFitView = () => {
      if (!hasDrawableNodes()) return false;
      if (typeof reactFlow.fitView !== "function") return false;
      reactFlow.fitView({ padding: 0.18 });
      lastHandledFitViewVersionRef.current = fitViewVersion;
      return true;
    };

    const timer = window.setTimeout(() => {
      const attemptFit = (retry) => {
        if (cancelled) return;
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => {
            if (cancelled) return;
            if (!runFitView() && retry < 5) {
              window.setTimeout(() => attemptFit(retry + 1), 120);
            }
          });
        });
      };
      attemptFit(0);
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [fitViewVersion, flowNodes.length, nodes.length, reactFlow]);

  const busIdAtPoint = useCallbackReactFlowCanvas(
    (clientX, clientY) => {
      const flowNode = flowNodes.find((node) => {
        if (!node?.data?.isBus) return false;
        const width = Number.parseFloat(node.style?.width) || 24;
        const height = Number.parseFloat(node.style?.height) || 92;
        const screenPosition =
          typeof reactFlow.flowToScreenPosition === "function"
            ? reactFlow.flowToScreenPosition(node.position)
            : node.position;
        return (
          clientX >= screenPosition.x &&
          clientX <= screenPosition.x + width &&
          clientY >= screenPosition.y &&
          clientY <= screenPosition.y + height
        );
      });
      return flowNode?.id || "";
    },
    [flowNodes, reactFlow],
  );

  const busIdAtFlowPoint = useCallbackReactFlowCanvas(
    (x, y, excludeNodeId = "") => {
      const hotspotPadding = 32;
      const flowNode = flowNodes.find((node) => {
        if (!node?.data?.isBus || node.id === excludeNodeId) return false;
        const width = Number.parseFloat(node.style?.width) || 24;
        const height = Number.parseFloat(node.style?.height) || 92;
        return (
          x >= node.position.x - hotspotPadding &&
          x <= node.position.x + width + hotspotPadding &&
          y >= node.position.y - hotspotPadding &&
          y <= node.position.y + height + hotspotPadding
        );
      });
      return flowNode?.id || "";
    },
    [flowNodes],
  );

  const onDragOver = useCallbackReactFlowCanvas(
    (event) => {
      event.preventDefault();
      if (rectangleSelectionArmed) return;
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "copy";
      }
      const payload = dragPayloadFromEvent(event);
      const componentName = dragComponent || parseComponentPayload(payload).component || "";
      if (componentName) {
        setDragComponent(componentName);
      }
      if (isAttachableComponent(componentName) && !armedBranchComponent) {
        setHoverBusId(busIdAtPoint(event.clientX, event.clientY));
      }
    },
    [armedBranchComponent, busIdAtPoint, dragComponent, rectangleSelectionArmed],
  );

  const onDragEnter = useCallbackReactFlowCanvas((event) => {
    closeContextMenu();
    if (rectangleSelectionArmed) return;
    const payload = dragPayloadFromEvent(event);
    const component = parseComponentPayload(payload);
    const componentName = component.component || "";
    if (!componentName) return;
    setDragComponent(componentName);
  }, [closeContextMenu, rectangleSelectionArmed]);

  const onDragLeave = useCallbackReactFlowCanvas((event) => {
    if (!flowWrapperRef.current?.contains(event.relatedTarget)) {
      setDragComponent("");
      setHoverBusId("");
    }
  }, []);

  const onDrop = useCallbackReactFlowCanvas(
    (event) => {
      event.preventDefault();
      closeContextMenu();
      if (rectangleSelectionArmed) return;
      const payload = dragPayloadFromEvent(event);
      if (!payload) return;

      const component = parseComponentPayload(payload);
      const componentName = component.component || "";
      if (!componentName) return;
      const meta = symbolMetaForComponent(componentName);
      const droppedBusId = busIdAtPoint(event.clientX, event.clientY);
      const position = flowPositionFromEvent(event);
      onNodeDrop?.({
        component: componentName,
        x: position.x - meta.width / 2,
        y: position.y - meta.height / 2,
        bus_node_id: droppedBusId,
      });
      setDragComponent("");
      setHoverBusId("");
      if (typeof window !== "undefined") {
        window.__pypsaBuilderActiveComponent = "";
        window.__pypsaBuilderActivePayload = null;
      }
    },
    [
      busIdAtPoint,
      closeContextMenu,
      flowPositionFromEvent,
      onNodeDrop,
      rectangleSelectionArmed,
    ],
  );

  const handlePaneClick = useCallbackReactFlowCanvas(
    (event) => {
      if (suppressNextPaneClickRef.current) {
        suppressNextPaneClickRef.current = false;
        return;
      }
      setArmedRegionDrag(null);
      closeContextMenu();
      if (rectangleSelectionArmed) return;
      if (!armedComponent || armedBranchComponent) return;
      const meta = symbolMetaForComponent(armedComponent);
      const position = flowPositionFromEvent(event);
      onNodeDrop?.({
        component: armedComponent,
        x: position.x - meta.width / 2,
        y: position.y - meta.height / 2,
        bus_node_id: "",
      });
    },
    [
      armedBranchComponent,
      armedComponent,
      closeContextMenu,
      flowPositionFromEvent,
      onNodeDrop,
      rectangleSelectionArmed,
    ],
  );

  const commitRegionRename = useCallbackReactFlowCanvas(
    (regionId = editingRegionId, name = editingRegionName) => {
      if (cancelRegionRenameRef.current) {
        cancelRegionRenameRef.current = false;
        setEditingRegionId("");
        setEditingRegionName("");
        return;
      }
      const nextName = String(name || "").trim();
      if (regionId && nextName) {
        onCanvasContextMenuAction?.({
          action_id: "rename_region",
          target_kind: "region",
          region_id: regionId,
          region_name: nextName,
        });
      }
      setEditingRegionId("");
      setEditingRegionName("");
    },
    [editingRegionId, editingRegionName, onCanvasContextMenuAction],
  );

  const handleNodeClick = useCallbackReactFlowCanvas(
    (_, node) => {
      closeContextMenu();
      if (rectangleSelectionArmed) return;
      const isBus = node?.data?.isBus;
      if (armedBranchComponent && isBus) {
        onBranchBusClick?.(node.id);
        return;
      }
      onNodeSelect?.(node.id);
    },
    [
      armedBranchComponent,
      closeContextMenu,
      onBranchBusClick,
      onNodeSelect,
      rectangleSelectionArmed,
    ],
  );

  const handleNodeMouseDown = useCallbackReactFlowCanvas(
    (event, node) => {
      if (event?.button === 2) return;
      closeContextMenu();
      if (rectangleSelectionArmed) return;
      if (!armedBranchComponent) {
        onNodeSelect?.(node.id);
      }
    },
    [armedBranchComponent, closeContextMenu, onNodeSelect, rectangleSelectionArmed],
  );

  const handleEdgeClick = useCallbackReactFlowCanvas(
    (_, edge) => {
      closeContextMenu();
      if (rectangleSelectionArmed) return;
      if (armedBranchComponent) return;
      const componentNodeId = edge?.attrs?.component_node_id;
      if (componentNodeId) {
        onEdgeSelect?.(componentNodeId);
      }
    },
    [armedBranchComponent, closeContextMenu, onEdgeSelect, rectangleSelectionArmed],
  );

  const handleNodeContextMenu = useCallbackReactFlowCanvas(
    (event, node) => {
      event.preventDefault();
      event.stopPropagation();
      if (rectangleSelectionArmed) return;
      if (!node?.id) return;
      const position = contextMenuPositionFromEvent(event);
      setContextMenu({
        targetKind: "component",
        targetId: node.id,
        nodeId: node.id,
        component: node?.data?.component || "",
        isLocked: Boolean(node?.data?.layoutLocked),
        x: position.x,
        y: position.y,
      });
    },
    [contextMenuPositionFromEvent, rectangleSelectionArmed],
  );

  const handleEdgeContextMenu = useCallbackReactFlowCanvas(
    (event, edge) => {
      event.preventDefault();
      event.stopPropagation();
      if (rectangleSelectionArmed) return;
      if (armedBranchComponent) return;
      const componentNodeId = edge?.attrs?.component_node_id;
      if (!isBranchEdgeComponent(edge?.component)) return;
      if (!componentNodeId) return;
      const position = contextMenuPositionFromEvent(event);
      setContextMenu({
        targetKind: "branch",
        targetId: edge.id,
        nodeId: componentNodeId,
        x: position.x,
        y: position.y,
      });
    },
    [armedBranchComponent, contextMenuPositionFromEvent, rectangleSelectionArmed],
  );

  const handleRegionContextMenu = useCallbackReactFlowCanvas(
    (event, region) => {
      event.preventDefault();
      event.stopPropagation();
      if (!region?.id) return;
      const position = contextMenuPositionFromEvent(event);
      setContextMenu({
        targetKind: "region",
        targetId: region.id,
        regionId: region.id,
        regionName: region.name || "Region",
        regionColor: normalizeRegionColor(region.color),
        regionBounds: {
          x: Number(region.x || 0),
          y: Number(region.y || 0),
          width: Number(region.width || 0),
          height: Number(region.height || 0),
        },
        isSummary: Boolean(region.summary),
        x: position.x,
        y: position.y,
      });
    },
    [contextMenuPositionFromEvent],
  );

  const handleContextMenuAction = useCallbackReactFlowCanvas(
    (actionId, menuContext) => {
      if (!menuContext) return;
      if (actionId === "show_region_menu") {
        setContextMenu({ ...menuContext, mode: "" });
        return;
      }
      if (actionId === "open_region_color") {
        setContextMenu({ ...menuContext, mode: "color" });
        return;
      }
      if (actionId === "zoom_to_region") {
        zoomToRegionBounds(menuContext.regionBounds, reactFlow, flowWrapperRef.current);
        closeContextMenu();
        return;
      }
      if (actionId === "rename_region") {
        cancelRegionRenameRef.current = false;
        setEditingRegionId(menuContext.regionId || "");
        setEditingRegionName(menuContext.regionName || "Region");
        closeContextMenu();
        return;
      }
      if (actionId === "drag_region_marker" || actionId === "drag_region_with_components") {
        setArmedRegionDrag({
          regionId: menuContext.regionId || "",
          mode: actionId === "drag_region_with_components" ? "with_components" : "marker",
        });
        setRegionDrag(null);
        setArmedRegionResize(null);
        setRegionResize(null);
        closeContextMenu();
        return;
      }
      if (actionId === "resize_region_marker") {
        setArmedRegionResize({ regionId: menuContext.regionId || "" });
        setRegionResize(null);
        setArmedRegionDrag(null);
        setRegionDrag(null);
        closeContextMenu();
        return;
      }
      onCanvasContextMenuAction?.({
        action_id:
          actionId === "drag_region_marker" || actionId === "drag_region_with_components"
            ? "move_region"
            : actionId,
        target_kind: menuContext.targetKind,
        node_id: menuContext.nodeId || "",
        node_ids: menuContext.nodeIds || [],
        region_id: menuContext.regionId || "",
        region_name: menuContext.regionName || "",
        region_color: menuContext.regionColor || "",
        region_bounds: menuContext.regionBounds || {},
        node_updates: menuContext.nodeUpdates || [],
        lock_node_ids: menuContext.lockNodeIds || [],
      });
      closeContextMenu();
    },
    [closeContextMenu, onCanvasContextMenuAction, reactFlow],
  );

  const handleNodeDrag = useCallbackReactFlowCanvas(
    (_, node) => {
      closeContextMenu();
      if (rectangleSelectionArmed) return;
      const hasBusAttr = Object.prototype.hasOwnProperty.call(node?.data?.attrs || {}, "bus");
      const isConnected = Boolean(node?.data?.attrs?.bus);
      if (!hasBusAttr || node?.data?.isBus) {
        setHoverBusId("");
        setDragBusSidePreview({ nodeId: "", side: "" });
        return;
      }
      const width = Number.parseFloat(node.style?.width) || 56;
      const height = Number.parseFloat(node.style?.height) || 56;
      const sourceNode = nodes.find((candidate) => candidate.id === node.id);
      const positionedNode = {
        ...(sourceNode || {}),
        id: node.id,
        component: sourceNode?.component || node?.data?.component || "",
        attrs: sourceNode?.attrs || node?.data?.attrs || {},
        layout: sourceNode?.layout || node?.data?.layout || {},
        position: node.position,
      };

      if (isConnected) {
        const targetBusNode = attachedBusNodeForNode(positionedNode, nodes);
        const busSide = targetBusNode
          ? sideForBusConnection(
              targetBusNode,
              positionedNode,
              layoutBusSide(positionedNode),
            )
          : "";
        setHoverBusId("");
        setDragBusSidePreview((current) =>
          current.nodeId === node.id && current.side === busSide
            ? current
            : { nodeId: node.id, side: busSide },
        );
        return;
      }

      setHoverBusId(
        busIdAtFlowPoint(
          node.position.x + width / 2,
          node.position.y + height / 2,
          node.id,
        ),
      );
      setDragBusSidePreview({ nodeId: "", side: "" });
    },
    [busIdAtFlowPoint, closeContextMenu, nodes, rectangleSelectionArmed],
  );

  const handleNodeDragStop = useCallbackReactFlowCanvas(
    (_, node) => {
      if (rectangleSelectionArmed) return;
      const hasBusAttr = Object.prototype.hasOwnProperty.call(node?.data?.attrs || {}, "bus");
      const isConnected = Boolean(node?.data?.attrs?.bus);
      const width = Number.parseFloat(node.style?.width) || 56;
      const height = Number.parseFloat(node.style?.height) || 56;
      const sourceNode = nodes.find((candidate) => candidate.id === node.id);
      const positionedNode = {
        ...(sourceNode || {}),
        id: node.id,
        component: sourceNode?.component || node?.data?.component || "",
        attrs: sourceNode?.attrs || node?.data?.attrs || {},
        layout: sourceNode?.layout || node?.data?.layout || {},
        position: node.position,
      };
      const busNodeId =
        hasBusAttr && !isConnected && !node?.data?.isBus
          ? busIdAtFlowPoint(
              node.position.x + width / 2,
              node.position.y + height / 2,
              node.id,
            )
          : "";
      const targetBusNode = busNodeId
        ? nodes.find((candidate) => candidate.id === busNodeId)
        : attachedBusNodeForNode(positionedNode, nodes);
      const busSide = targetBusNode
        ? sideForBusConnection(
            targetBusNode,
            positionedNode,
            layoutBusSide(positionedNode),
          )
        : "";
      const update = {
        id: node.id,
        position: node.position,
        bus_node_id: busNodeId,
      };
      if (busSide) {
        update.layout = {
          ...(positionedNode.layout || {}),
          bus_side: busSide,
        };
        setDragBusSidePreview({ nodeId: node.id, side: busSide });
      }
      setHoverBusId("");
      onNodesUpdate?.([update]);
      window.setTimeout(() => {
        setDragBusSidePreview((current) =>
          current.nodeId === node.id ? { nodeId: "", side: "" } : current,
        );
      }, 200);
    },
    [busIdAtFlowPoint, nodes, onNodesUpdate, rectangleSelectionArmed],
  );

  return (
    <div
      className="react-flow-shell"
      data-armed-component={armedComponent && !armedBranchComponent ? "true" : "false"}
      data-branch-armed={armedBranchComponent ? "true" : "false"}
      data-rectangle-selection-armed={rectangleSelectionArmed ? "true" : "false"}
      data-region-drag-armed={armedRegionDrag ? "true" : "false"}
      data-region-dragging={regionDrag ? "true" : "false"}
      data-region-resize-armed={armedRegionResize ? "true" : "false"}
      data-region-resizing={regionResize ? "true" : "false"}
      ref={flowWrapperRef}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onMouseDownCapture={handleSelectionMouseDownCapture}
      onMouseMoveCapture={handleSelectionMouseMoveCapture}
      onMouseUpCapture={completeSelectionDrag}
    >
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        onNodeMouseDown={handleNodeMouseDown}
        onEdgeClick={handleEdgeClick}
        onNodeContextMenu={handleNodeContextMenu}
        onEdgeContextMenu={handleEdgeContextMenu}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={handleNodeDragStop}
        onPaneClick={handlePaneClick}
        nodesDraggable={!rectangleSelectionArmed && !regionDrag && !regionResize}
        panOnDrag={!rectangleSelectionArmed && !regionDrag && !regionResize}
        elementsSelectable={!rectangleSelectionArmed && !regionDrag && !regionResize}
        minZoom={0.1}
      >
        <Background />
        <Controls />
      </ReactFlow>
      {renderedRegions.length ? (
        <div className="canvas-region-layer" aria-hidden="false">
          {renderedRegions.map((region) => (
            <div
              key={region.id}
              className="canvas-region"
              data-armed={region.isArmedForDrag ? "true" : "false"}
              data-dragging={region.isDragging ? "true" : "false"}
              data-resize-armed={region.isArmedForResize ? "true" : "false"}
              data-resizing={region.isResizing ? "true" : "false"}
              data-summary={region.summary ? "true" : "false"}
              onMouseDown={(event) => handleRegionMouseDown(event, region)}
              onContextMenu={(event) => handleRegionContextMenu(event, region)}
              title={region.name || "Region"}
              style={{
                ...regionStyleVars(
                  region,
                  region.isArmedForDrag ||
                    region.isDragging ||
                    region.isArmedForResize ||
                    region.isResizing,
                ),
                left: `${region.rect.x}px`,
                top: `${region.rect.y}px`,
                width: `${region.rect.width}px`,
                height: `${region.rect.height}px`,
              }}
            >
              {editingRegionId === region.id ? (
                <input
                  className={`canvas-region-label canvas-region-label-input${region.summary ? " canvas-region-summary-label" : ""}`}
                  value={editingRegionName}
                  autoFocus
                  onChange={(event) => setEditingRegionName(event.target.value)}
                  onBlur={() => commitRegionRename(region.id, editingRegionName)}
                  onMouseDown={(event) => event.stopPropagation()}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      commitRegionRename(region.id, editingRegionName);
                    }
                    if (event.key === "Escape") {
                      event.preventDefault();
                      cancelRegionRenameRef.current = true;
                      setEditingRegionId("");
                      setEditingRegionName("");
                    }
                  }}
                  title={region.name || "Region"}
                />
              ) : (
                <button
                  type="button"
                  className={`canvas-region-label${region.summary ? " canvas-region-summary-label" : ""}`}
                  onMouseDown={(event) => handleRegionMouseDown(event, region)}
                  onContextMenu={(event) => handleRegionContextMenu(event, region)}
                  title={region.name || "Region"}
                >
                  {region.name || "Region"}
                </button>
              )}
              {region.isArmedForResize || region.isResizing ? (
                ["nw", "ne", "sw", "se"].map((handle) => (
                  <button
                    key={handle}
                    type="button"
                    className="canvas-region-resize-handle"
                    data-handle={handle}
                    aria-label={`Resize region ${handle}`}
                    title="Resize region"
                    onMouseDown={(event) =>
                      handleRegionResizeMouseDown(event, region, handle)
                    }
                  />
                ))
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      {selectionDrag ? (
        <div
          className="canvas-selection-rectangle"
          style={{
            left: `${normalizeSelectionRect(selectionDrag.start, selectionDrag.current).x}px`,
            top: `${normalizeSelectionRect(selectionDrag.start, selectionDrag.current).y}px`,
            width: `${normalizeSelectionRect(selectionDrag.start, selectionDrag.current).width}px`,
            height: `${normalizeSelectionRect(selectionDrag.start, selectionDrag.current).height}px`,
          }}
        />
      ) : null}
      <CanvasContextMenu
        contextMenu={contextMenu}
        onAction={handleContextMenuAction}
      />
    </div>
  );
}

export function ReactFlowCanvas(props) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
