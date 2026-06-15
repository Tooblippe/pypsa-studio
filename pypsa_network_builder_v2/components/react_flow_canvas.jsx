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

function buildBusConnectionRouting(nodes, edges) {
  const nodeById = new Map((nodes || []).map((node) => [node.id, node]));
  const handlesByBusId = {};
  const handleGroups = new Map();

  const registerBusHandle = (edge, endpoint) => {
    const busNodeId = endpoint === "source" ? edge.source : edge.target;
    const otherNodeId = endpoint === "source" ? edge.target : edge.source;
    const busNode = nodeById.get(busNodeId);
    if (busNode?.component !== "buses") {
      return endpoint === "source" ? edge.sourceHandle : edge.targetHandle;
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

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        markerStart={markerStart}
        style={style}
      />
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="schematic-edge-label"
            data-selected={selected ? "true" : "false"}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px) rotate(${rotateLabel ? 90 : 0}deg)`,
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
  const symbolStyle = { height: `${symbolHeight}px` };

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
      {showConnectorTerminals ? (
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
      ) : null}
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
        <span
          className="schematic-node-symbol"
          style={symbolStyle}
          dangerouslySetInnerHTML={{ __html: data.iconSvg }}
        />
      ) : (
        <img className="schematic-node-symbol" src={data.iconSrc} alt="" style={symbolStyle} />
      )}
      <span className="schematic-node-label">{data.label}</span>
    </div>
  );
}

const nodeTypes = { schematic: SchematicNode };
const edgeTypes = { step: SchematicStepEdge };

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
}) {
  const flowWrapperRef = useRefReactFlowCanvas(null);
  const lastRoutedVersionRef = useRefReactFlowCanvas(0);
  const [hoverBusId, setHoverBusId] = useStateReactFlowCanvas("");
  const [dragComponent, setDragComponent] = useStateReactFlowCanvas("");
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
      nodes.filter((node) => !node.hidden).map((node) => {
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
      nodes,
      onBranchBusClick,
      onNodeSelect,
    ],
  );

  const flowEdges = useMemoReactFlowCanvas(
    () => {
      return [...edgeRouting.edges];
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

      onNodesUpdate?.(
        layout.children.map((node) => ({
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
  }, [flowEdges, flowNodes, onNodesUpdate, onRouteComplete, reactFlow, routeVersion]);

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

  useEffectReactFlowCanvas(() => {
    if (!fitViewVersion) return;
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
      reactFlow.fitView?.({ padding: 0.18 });
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
    const payload = dragPayloadFromEvent(event);
    const component = parseComponentPayload(payload);
    const componentName = component.component || "";
    if (!componentName) return;
    setDragComponent(componentName);
  }, []);

  const onDragLeave = useCallbackReactFlowCanvas((event) => {
    if (!flowWrapperRef.current?.contains(event.relatedTarget)) {
      setDragComponent("");
      setHoverBusId("");
    }
  }, []);

  const onDrop = useCallbackReactFlowCanvas(
    (event) => {
      event.preventDefault();
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
    [busIdAtPoint, flowPositionFromEvent, onNodeDrop],
  );

  const handlePaneClick = useCallbackReactFlowCanvas(
    (event) => {
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
    [armedBranchComponent, armedComponent, flowPositionFromEvent, onNodeDrop],
  );

  const handleNodeClick = useCallbackReactFlowCanvas(
    (_, node) => {
      const isBus = node?.data?.isBus;
      if (armedBranchComponent && isBus) {
        onBranchBusClick?.(node.id);
        return;
      }
      onNodeSelect?.(node.id);
    },
    [armedBranchComponent, onBranchBusClick, onNodeSelect],
  );

  const handleNodeMouseDown = useCallbackReactFlowCanvas(
    (_, node) => {
      if (!armedBranchComponent) {
        onNodeSelect?.(node.id);
      }
    },
    [armedBranchComponent, onNodeSelect],
  );

  const handleEdgeClick = useCallbackReactFlowCanvas(
    (_, edge) => {
      if (armedBranchComponent) return;
      const componentNodeId = edge?.attrs?.component_node_id;
      if (componentNodeId) {
        onEdgeSelect?.(componentNodeId);
      }
    },
    [armedBranchComponent, onEdgeSelect],
  );

  const handleNodeDrag = useCallbackReactFlowCanvas(
    (_, node) => {
      const hasBusAttr = Object.prototype.hasOwnProperty.call(node?.data?.attrs || {}, "bus");
      const isConnected = Boolean(node?.data?.attrs?.bus);
      if (!hasBusAttr || isConnected || node?.data?.isBus) {
        setHoverBusId("");
        return;
      }
      const width = Number.parseFloat(node.style?.width) || 56;
      const height = Number.parseFloat(node.style?.height) || 56;
      setHoverBusId(
        busIdAtFlowPoint(
          node.position.x + width / 2,
          node.position.y + height / 2,
          node.id,
        ),
      );
    },
    [busIdAtFlowPoint],
  );

  const handleNodeDragStop = useCallbackReactFlowCanvas(
    (_, node) => {
      const hasBusAttr = Object.prototype.hasOwnProperty.call(node?.data?.attrs || {}, "bus");
      const isConnected = Boolean(node?.data?.attrs?.bus);
      const width = Number.parseFloat(node.style?.width) || 56;
      const height = Number.parseFloat(node.style?.height) || 56;
      const busNodeId =
        hasBusAttr && !isConnected && !node?.data?.isBus
          ? busIdAtFlowPoint(
              node.position.x + width / 2,
              node.position.y + height / 2,
              node.id,
            )
          : "";
      setHoverBusId("");
      onNodesUpdate?.([
        {
          id: node.id,
          position: node.position,
          bus_node_id: busNodeId,
        },
      ]);
    },
    [busIdAtFlowPoint, onNodesUpdate],
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
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={handleNodeDragStop}
        onPaneClick={handlePaneClick}
        nodesDraggable
        fitView={nodes.length === 0}
        minZoom={0.1}
      >
        <Background />
        <Controls />
      </ReactFlow>
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
