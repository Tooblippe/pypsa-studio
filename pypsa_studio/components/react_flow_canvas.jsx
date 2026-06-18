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
  const sideCounts = { left: 0, right: 0 };
  (handles || []).forEach((handle) => {
    sideCounts[handle.side] = (sideCounts[handle.side] || 0) + 1;
  });
  return Math.max(sideCounts.left, sideCounts.right);
}

function busSymbolHeightForHandles(handles) {
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

function safeHandleId(value) {
  return String(value || "edge").replace(/[^a-zA-Z0-9_-]/g, "_");
}

function layoutBusSide(node) {
  const side = String(node?.layout?.bus_side || node?.data?.layout?.bus_side || "").toLowerCase();
  return side === "left" || side === "right" ? side : "";
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
  const meta = symbolMetaForComponent(node.component);
  return {
    x: Number(node.position?.x || 0) + meta.width / 2,
    y: Number(node.position?.y || 0) + (meta.height + 20) / 2,
  };
}

function sideForBusConnection(busNode, otherNode, fallbackHandle) {
  const busCenter = nodeCenter(busNode);
  const otherCenter = nodeCenter(otherNode);
  if (busCenter && otherCenter) {
    const dx = otherCenter.x - busCenter.x;
    if (Math.abs(dx) > 1) {
      return dx < 0 ? "left" : "right";
    }
  }
  return String(fallbackHandle || "").startsWith("left") ? "left" : "right";
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
      x: Number(busNode.position?.x || 0) + (busSide === "left" ? -150 : 150),
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
      sortY: otherCenter?.y ?? 0,
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
      const yDelta = left.sortY - right.sortY;
      return Math.abs(yDelta) > 1 ? yDelta : left.sortIndex - right.sortIndex;
    });
    const count = group.length;
    const busNodeId = group[0]?.busNodeId;
    const busHeight = busSymbolHeightForHandles(handlesByBusId[busNodeId] || []);
    const groupSpan = Math.max(0, count - 1) * BUS_CONNECTION_SPACING_PX;
    const startY = count === 1 ? busHeight / 2 : (busHeight - groupSpan) / 2;
    group.forEach((handle, index) => {
      handle.offsetPx = count === 1 ? startY : startY + index * BUS_CONNECTION_SPACING_PX;
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
  const busSymbolHeight = Number(data.busSymbolHeight || BUILDER_SYMBOL_META.bus.height);
  const handleSignature = (data.connectionHandles || [])
    .map((handle) => `${handle.id}:${handle.offsetPx}`)
    .join("|");

  useEffectReactFlowCanvas(() => {
    if (data.isBus) {
      updateNodeInternals(data.nodeId);
    }
  }, [busSymbolHeight, data.isBus, data.nodeId, handleSignature, updateNodeInternals]);

  const busHandleTop = (handle) => Number(handle.offsetPx || busSymbolHeight / 2);
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
      data-selected={selected ? "true" : "false"}
      data-branch-armed={data.branchArmed && data.isBus ? "true" : "false"}
      data-connection-hover={data.connectionDrag && data.isBus && data.hoverBusId === data.nodeId ? "true" : "false"}
      data-branch-start={data.branchBus0NodeId === data.nodeId ? "true" : "false"}
      title={`${data.label} (${data.component})`}
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
          position={handle.side === "left" ? Position.Left : Position.Right}
          style={{
            top: `${busHandleTop(handle)}px`,
            left: "50%",
            transform: "translate(-50%, -50%)",
          }}
        />
      ))}
      {data.isBus ? (
        <span
          className="schematic-bus-symbol"
          style={{ height: `${busSymbolHeight}px` }}
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
    id: "delete",
    label: "Delete",
    targetKinds: ["component", "branch"],
  },
];

function canvasContextMenuItemsForTarget(contextMenu) {
  if (!contextMenu?.targetKind) return [];
  return CANVAS_CONTEXT_MENU_ITEMS.filter((item) =>
    item.targetKinds.includes(contextMenu.targetKind),
  );
}

function canvasContextTargetLabel(contextMenu) {
  if (!contextMenu?.targetKind) return "";
  return contextMenu.targetKind === "branch" ? "Branch" : "Component";
}

function CanvasContextMenu({ contextMenu, onAction }) {
  if (!contextMenu) return null;
  const menuItems = canvasContextMenuItemsForTarget(contextMenu);
  if (!menuItems.length) return null;

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
        {canvasContextTargetLabel(contextMenu)}
      </div>
      {menuItems.map((item) => (
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
          {item.label}
        </button>
      ))}
    </div>
  );
}

function CanvasInner({
  nodes = [],
  edges = [],
  routeVersion = 0,
  fitViewVersion = 0,
  armedComponent = "",
  armedBranchComponent = "",
  branchBus0NodeId = "",
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
  const [hoverBusId, setHoverBusId] = useStateReactFlowCanvas("");
  const [dragComponent, setDragComponent] = useStateReactFlowCanvas("");
  const [dragBusSidePreview, setDragBusSidePreview] = useStateReactFlowCanvas({
    nodeId: "",
    side: "",
  });
  const [contextMenu, setContextMenu] = useStateReactFlowCanvas(null);
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

  const flowNodes = useMemoReactFlowCanvas(
    () =>
      nodes.filter((node) => !node.hidden && !isBranchEdgeComponent(node.component)).map((node) => {
        const meta = symbolMetaForComponent(node.component);
        const label = displayNameForNode(node);
        const connectionHandles = node.component === "buses" ? edgeRouting.handlesByBusId[node.id] || [] : [];
        const symbolHeight = node.component === "buses" ? busSymbolHeightForHandles(connectionHandles) : meta.height;
        return {
          id: node.id,
          type: "schematic",
          position: node.position,
          style: {
            width: `${meta.width}px`,
            height: `${symbolHeight + BUS_LABEL_HEIGHT}px`,
          },
          data: {
            nodeId: node.id,
            label,
            component: node.component,
            attrs: node.attrs || {},
            layout: node.layout || {},
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
            busSymbolHeight: symbolHeight,
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
    ],
  );

  const flowEdges = useMemoReactFlowCanvas(
    () => {
      return edgeRouting.edges.map((edge) => ({
        ...edge,
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
          position: {
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
  }, [flowEdges, flowNodes, nodes, onNodesUpdate, onRouteComplete, reactFlow, routeVersion]);

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

  const contextMenuPositionFromEvent = useCallbackReactFlowCanvas((event) => {
    const bounds = flowWrapperRef.current?.getBoundingClientRect();
    if (!bounds) {
      return { x: event.clientX, y: event.clientY };
    }
    const menuWidth = 180;
    const menuHeight = 96;
    return {
      x: Math.max(8, Math.min(event.clientX - bounds.left, bounds.width - menuWidth - 8)),
      y: Math.max(8, Math.min(event.clientY - bounds.top, bounds.height - menuHeight - 8)),
    };
  }, []);

  const closeContextMenu = useCallbackReactFlowCanvas(() => {
    setContextMenu(null);
  }, []);

  useEffectReactFlowCanvas(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        closeContextMenu();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [closeContextMenu]);

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
    [armedBranchComponent, busIdAtPoint, dragComponent],
  );

  const onDragEnter = useCallbackReactFlowCanvas((event) => {
    closeContextMenu();
    const payload = dragPayloadFromEvent(event);
    const component = parseComponentPayload(payload);
    const componentName = component.component || "";
    if (!componentName) return;
    setDragComponent(componentName);
  }, [closeContextMenu]);

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
    [busIdAtPoint, closeContextMenu, flowPositionFromEvent, onNodeDrop],
  );

  const handlePaneClick = useCallbackReactFlowCanvas(
    (event) => {
      closeContextMenu();
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
    ],
  );

  const handleNodeClick = useCallbackReactFlowCanvas(
    (_, node) => {
      closeContextMenu();
      const isBus = node?.data?.isBus;
      if (armedBranchComponent && isBus) {
        onBranchBusClick?.(node.id);
        return;
      }
      onNodeSelect?.(node.id);
    },
    [armedBranchComponent, closeContextMenu, onBranchBusClick, onNodeSelect],
  );

  const handleNodeMouseDown = useCallbackReactFlowCanvas(
    (event, node) => {
      if (event?.button === 2) return;
      closeContextMenu();
      if (!armedBranchComponent) {
        onNodeSelect?.(node.id);
      }
    },
    [armedBranchComponent, closeContextMenu, onNodeSelect],
  );

  const handleEdgeClick = useCallbackReactFlowCanvas(
    (_, edge) => {
      closeContextMenu();
      if (armedBranchComponent) return;
      const componentNodeId = edge?.attrs?.component_node_id;
      if (componentNodeId) {
        onEdgeSelect?.(componentNodeId);
      }
    },
    [armedBranchComponent, closeContextMenu, onEdgeSelect],
  );

  const handleNodeContextMenu = useCallbackReactFlowCanvas(
    (event, node) => {
      event.preventDefault();
      event.stopPropagation();
      if (!node?.id) return;
      const position = contextMenuPositionFromEvent(event);
      setContextMenu({
        targetKind: "component",
        targetId: node.id,
        nodeId: node.id,
        x: position.x,
        y: position.y,
      });
    },
    [contextMenuPositionFromEvent],
  );

  const handleEdgeContextMenu = useCallbackReactFlowCanvas(
    (event, edge) => {
      event.preventDefault();
      event.stopPropagation();
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
    [armedBranchComponent, contextMenuPositionFromEvent],
  );

  const handleContextMenuAction = useCallbackReactFlowCanvas(
    (actionId, menuContext) => {
      if (!menuContext?.nodeId) return;
      onCanvasContextMenuAction?.({
        action_id: actionId,
        target_kind: menuContext.targetKind,
        node_id: menuContext.nodeId,
      });
      closeContextMenu();
    },
    [closeContextMenu, onCanvasContextMenuAction],
  );

  const handleNodeDrag = useCallbackReactFlowCanvas(
    (_, node) => {
      closeContextMenu();
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
    [busIdAtFlowPoint, closeContextMenu, nodes],
  );

  const handleNodeDragStop = useCallbackReactFlowCanvas(
    (_, node) => {
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
    [busIdAtFlowPoint, nodes, onNodesUpdate],
  );

  return (
    <div
      className="react-flow-shell"
      data-armed-component={armedComponent && !armedBranchComponent ? "true" : "false"}
      data-branch-armed={armedBranchComponent ? "true" : "false"}
      ref={flowWrapperRef}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
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
        nodesDraggable
        minZoom={0.1}
      >
        <Background />
        <Controls />
      </ReactFlow>
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
