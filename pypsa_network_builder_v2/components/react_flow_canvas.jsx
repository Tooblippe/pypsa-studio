import React, {
  useCallback as useCallbackReactFlowCanvas,
  useEffect as useEffectReactFlowCanvas,
  useMemo as useMemoReactFlowCanvas,
  useRef as useRefReactFlowCanvas,
  useState as useStateReactFlowCanvas,
} from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlowProvider,
  useReactFlow,
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

function displayNameForNode(node) {
  return String(node?.attrs?.name || node?.id || node?.pypsa_name || "");
}

function SchematicNode({ data, selected }) {
  const handleSelect = (event) => {
    event.stopPropagation();
    if (data.branchArmed && data.isBus) {
      data.onBranchBusClick?.(data.nodeId);
      return;
    }
    data.onSelect?.(data.nodeId);
  };

  return (
    <div
      className="schematic-node"
      data-selected={selected ? "true" : "false"}
      data-branch-armed={data.branchArmed && data.isBus ? "true" : "false"}
      data-branch-start={data.branchBus0NodeId === data.nodeId ? "true" : "false"}
      data-branch-connected={data.branchConnected ? "true" : "false"}
      data-hover-connected={data.hoverConnected ? "true" : "false"}
      data-connection-target={
        data.connectionDrag && data.isBus
          ? data.hoverBusId === data.nodeId
            ? "hover"
            : "available"
          : "false"
      }
      title={`${data.label} (${data.component})`}
      onClick={handleSelect}
      onPointerDown={handleSelect}
    >
      <Handle className="schematic-node-handle" id="left-target" type="target" position={Position.Left} />
      <Handle className="schematic-node-handle" id="left-source" type="source" position={Position.Left} />
      <Handle className="schematic-node-handle" id="right-target" type="target" position={Position.Right} />
      <Handle className="schematic-node-handle" id="right-source" type="source" position={Position.Right} />
      {data.iconSvg ? (
        <span
          className="schematic-node-symbol"
          dangerouslySetInnerHTML={{ __html: data.iconSvg }}
        />
      ) : (
        <img className="schematic-node-symbol" src={data.iconSrc} alt="" />
      )}
      <span className="schematic-node-label">{data.label}</span>
    </div>
  );
}

const nodeTypes = { schematic: SchematicNode };

function CanvasInner({
  nodes = [],
  edges = [],
  routeVersion = 0,
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
  const [hoveredNodeId, setHoveredNodeId] = useStateReactFlowCanvas("");
  const [hoveredBranchEdge, setHoveredBranchEdge] = useStateReactFlowCanvas(null);
  const [dragComponent, setDragComponent] = useStateReactFlowCanvas("");
  const reactFlow = useReactFlow();

  const isConnectionDrag = Boolean(
    dragComponent &&
      !armedBranchComponent &&
      !["buses", "lines", "links", "transformers"].includes(dragComponent),
  );

  const flowNodes = useMemoReactFlowCanvas(
    () =>
      nodes.filter((node) => !node.hidden).map((node) => {
        const meta = symbolMetaForComponent(node.component);
        const label = displayNameForNode(node);
        const hoveredNodeEdges = hoveredNodeId
          ? (edges || []).filter(
              (edge) => edge.source === hoveredNodeId || edge.target === hoveredNodeId,
            )
          : [];
        const hoverConnected =
          hoveredNodeId &&
          node.id !== hoveredNodeId &&
          hoveredNodeEdges.some(
            (edge) => edge.source === node.id || edge.target === node.id,
          );
        const branchConnected =
          hoveredBranchEdge &&
          node.component === "buses" &&
          (hoveredBranchEdge.source === node.id || hoveredBranchEdge.target === node.id);
        return {
          id: node.id,
          type: "schematic",
          position: node.position,
          style: {
            width: `${meta.width}px`,
            height: `${meta.height + 20}px`,
          },
          data: {
            nodeId: node.id,
            label,
            component: node.component,
            attrs: node.attrs || {},
            isBus: node.component === "buses",
            branchArmed: Boolean(armedBranchComponent),
            branchConnected,
            hoverConnected,
            connectionDrag: isConnectionDrag,
            hoverBusId,
            branchBus0NodeId,
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
      hoverBusId,
      hoveredBranchEdge,
      hoveredNodeId,
      isConnectionDrag,
      nodes,
      edges,
      onBranchBusClick,
      onNodeSelect,
    ],
  );

  const flowEdges = useMemoReactFlowCanvas(
    () => {
      const renderedEdges = (edges || []).map((edge) => ({
        ...edge,
        type: "step",
        style:
          hoveredBranchEdge?.id === edge.id ||
          (hoveredNodeId && (edge.source === hoveredNodeId || edge.target === hoveredNodeId))
            ? {
                ...(edge.style || {}),
                stroke: "#facc15",
                strokeWidth: 5,
              }
            : edge.style,
        labelStyle:
          hoveredBranchEdge?.id === edge.id
            ? {
                fill: "#854d0e",
                fontWeight: 700,
              }
            : edge.labelStyle,
      }));
      if (armedBranchComponent && branchBus0NodeId && hoverBusId && hoverBusId !== branchBus0NodeId) {
        renderedEdges.push({
          id: `preview:${branchBus0NodeId}:${hoverBusId}`,
          source: branchBus0NodeId,
          target: hoverBusId,
          sourceHandle: "right-source",
          targetHandle: "left-target",
          type: "step",
          selectable: false,
          style: {
            strokeWidth: 2,
            strokeDasharray: "6 5",
            stroke: "var(--accent-9)",
          },
        });
      }
      return renderedEdges;
    },
    [
      armedBranchComponent,
      branchBus0NodeId,
      edges,
      hoverBusId,
      hoveredBranchEdge,
      hoveredNodeId,
    ],
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
      if (isConnectionDrag) {
        setHoverBusId(busIdAtPoint(event.clientX, event.clientY));
      }
    },
    [busIdAtPoint, isConnectionDrag],
  );

  const onDragEnter = useCallbackReactFlowCanvas((event) => {
    const payload =
      event.dataTransfer?.getData("application/pypsa-component") ||
      (typeof window !== "undefined" ? window.__pypsaBuilderActiveComponent : "");
    if (!payload) return;
    const component =
      typeof payload === "string" && payload.trim().startsWith("{")
        ? JSON.parse(payload)
        : { component: payload };
    setDragComponent(component.component || "");
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
      const payload =
        event.dataTransfer?.getData("application/pypsa-component") ||
        (typeof window !== "undefined" ? window.__pypsaBuilderActiveComponent : "");
      if (!payload) return;

      const component =
        typeof payload === "string" && payload.trim().startsWith("{")
          ? JSON.parse(payload)
          : { component: payload };
      const componentName = component.component;
      const meta = symbolMetaForComponent(componentName);
      const droppedBusId = busIdAtPoint(event.clientX, event.clientY);
      const bounds = flowWrapperRef.current?.getBoundingClientRect();
      const point = bounds
        ? { x: event.clientX - bounds.left, y: event.clientY - bounds.top }
        : { x: event.clientX, y: event.clientY };
      const position =
        typeof reactFlow.project === "function"
          ? reactFlow.project(point)
          : typeof reactFlow.screenToFlowPosition === "function"
            ? reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY })
            : point;
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
      }
    },
    [busIdAtPoint, onNodeDrop, reactFlow],
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

  const handleNodeMouseEnter = useCallbackReactFlowCanvas(
    (_, node) => {
      setHoveredNodeId(node.id);
      if (armedBranchComponent && node?.data?.isBus) {
        setHoverBusId(node.id);
      }
    },
    [armedBranchComponent],
  );

  const handleNodeMouseLeave = useCallbackReactFlowCanvas((_, node) => {
    if (node?.id === hoveredNodeId) {
      setHoveredNodeId("");
    }
    if (node?.id === hoverBusId) {
      setHoverBusId("");
    }
  }, [hoverBusId, hoveredNodeId]);

  const handleEdgeClick = useCallbackReactFlowCanvas(
    (_, edge) => {
      const componentNodeId = edge?.attrs?.component_node_id;
      if (componentNodeId) {
        onEdgeSelect?.(componentNodeId);
      }
    },
    [onEdgeSelect],
  );

  const handleEdgeMouseEnter = useCallbackReactFlowCanvas((_, edge) => {
    if (edge?.component && edge?.attrs?.bus0 && edge?.attrs?.bus1) {
      setHoveredBranchEdge({
        id: edge.id,
        source: edge.source,
        target: edge.target,
      });
    }
  }, []);

  const handleEdgeMouseLeave = useCallbackReactFlowCanvas(() => {
    setHoveredBranchEdge(null);
  }, []);

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
        onNodeClick={handleNodeClick}
        onNodeMouseDown={handleNodeMouseDown}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        onEdgeClick={handleEdgeClick}
        onEdgeMouseEnter={handleEdgeMouseEnter}
        onEdgeMouseLeave={handleEdgeMouseLeave}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={handleNodeDragStop}
        nodesDraggable
        fitView={nodes.length === 0}
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
