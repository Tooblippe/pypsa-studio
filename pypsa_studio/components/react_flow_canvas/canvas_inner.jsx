/**
 * Merge new prop-derived node data into ReactFlow's live node state.
 */
function mergeLiveFlowNodes(currentNodes, nextNodes, draggingNodeId = "") {
  const currentById = new Map((currentNodes || []).map((node) => [node.id, node]));
  return (nextNodes || []).map((node) => {
    const currentNode = currentById.get(node.id);
    if (!currentNode) return node;
    const mergedNode = { ...node };
    if (currentNode.selected !== undefined) {
      mergedNode.selected = currentNode.selected;
    }
    if (currentNode.dragging !== undefined) {
      mergedNode.dragging = currentNode.dragging;
    }
    if (node.id === draggingNodeId && currentNode.position) {
      mergedNode.position = currentNode.position;
    }
    return mergedNode;
  });
}

/**
 * Return a diagram-node shaped copy of a ReactFlow node.
 */
function diagramNodeFromFlowNode(node) {
  const data = node?.data || {};
  return {
    ...(node || {}),
    component: node?.component || data.component || "",
    attrs: node?.attrs || data.attrs || {},
    layout: node?.layout || data.layout || {},
    position: node?.position || { x: 0, y: 0 },
  };
}

/**
 * Return a stable comparison key for bus voltage values.
 */
function voltageKey(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const numberValue = Number(text);
  return Number.isFinite(numberValue) ? String(numberValue) : text;
}

/**
 * Return voltage colors keyed by diagram node id.
 */
function voltageColorsByNodeId(nodes) {
  const voltageKeys = [];
  const voltageByBusName = new Map();

  (nodes || []).forEach((node) => {
    if (node?.component !== "buses") return;
    const key = voltageKey(node?.attrs?.v_nom);
    if (!key) return;
    if (!voltageKeys.includes(key)) voltageKeys.push(key);
    voltageByBusName.set(busNameForNode(node), key);
  });

  const colorByVoltage = new Map(
    voltageKeys.map((key, index) => [
      key,
      VOLTAGE_COLOR_OPTIONS[index % VOLTAGE_COLOR_OPTIONS.length].color,
    ]),
  );
  const colorByNodeId = {};

  (nodes || []).forEach((node) => {
    const component = String(node?.component || "").toLowerCase();
    if (component === "transformers" || component === "transformer") return;
    const attrs = node?.attrs || {};
    const ownVoltage = voltageKey(attrs.v_nom);
    const busVoltage = voltageByBusName.get(String(attrs.bus || ""));
    const branchVoltage = voltageByBusName.get(String(attrs.bus0 || ""));
    const voltage = ownVoltage || busVoltage || branchVoltage;
    const color = colorByVoltage.get(voltage);
    if (color) colorByNodeId[node.id] = color;
  });

  return colorByNodeId;
}

function CanvasInner({
  nodes = [],
  edges = [],
  regions = [],
  routeVersion = 0,
  fitViewVersion = 0,
  selectedNodeId = "",
  armedComponent = "",
  armedBranchComponent = "",
  branchBus0NodeId = "",
  rectangleSelectionArmed = false,
  onNodeDrop,
  onNodeSelect,
  onBranchBusClick,
  onEdgeSelect,
  onEdgeOffsetUpdate,
  onNodesUpdate,
  onRouteComplete,
  onCanvasContextMenuAction,
}) {
  const flowWrapperRef = useRefReactFlowCanvas(null);
  const lastRoutedVersionRef = useRefReactFlowCanvas(0);
  const lastHandledFitViewVersionRef = useRefReactFlowCanvas(0);
  const suppressNextPaneClickRef = useRefReactFlowCanvas(false);
  const cancelRegionRenameRef = useRefReactFlowCanvas(false);
  const draggingNodeIdRef = useRefReactFlowCanvas("");
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

  const voltageNodeColors = useMemoReactFlowCanvas(
    () => voltageColorsByNodeId(nodes),
    [nodes],
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

  const computedFlowNodes = useMemoReactFlowCanvas(
    () =>
      nodes.filter((node) => {
        const canvasVisible = isCanvasVisible(node);
        return (
          !node.hidden &&
          !isBranchEdgeComponent(node.component) &&
          (canvasVisible || summarizedRegionNodeIds.has(node.id))
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
            voltageColor: voltageNodeColors[node.id] || "",
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
      voltageNodeColors,
    ],
  );

  const [liveFlowNodes, setLiveFlowNodes] = useStateReactFlowCanvas([]);

  useEffectReactFlowCanvas(() => {
    setLiveFlowNodes((current) =>
      mergeLiveFlowNodes(current, computedFlowNodes, draggingNodeIdRef.current),
    );
  }, [computedFlowNodes]);

  const handleNodesChange = useCallbackReactFlowCanvas((changes) => {
    setLiveFlowNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const flowNodes =
    liveFlowNodes.length || !computedFlowNodes.length
      ? liveFlowNodes
      : computedFlowNodes;

  const liveDiagramNodes = useMemoReactFlowCanvas(
    () => flowNodes.map((node) => diagramNodeFromFlowNode(node)),
    [flowNodes],
  );

  const lockedPositionsById = useMemoReactFlowCanvas(() => {
    const positionsById = {};
    (nodes || []).forEach((node) => {
      if (!node?.hidden && isCanvasVisible(node) && node?.layout?.locked && node.position) {
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
      const flowNodeIds = new Set(flowNodes.map((node) => node.id));
      return edgeRouting.edges.filter(
        (edge) => flowNodeIds.has(edge.source) && flowNodeIds.has(edge.target),
      ).map((edge) => {
        const isTransformer = ["transformers", "transformer"].includes(
          String(edge.component || "").toLowerCase(),
        );
        const voltageColor = isTransformer
          ? ""
          : voltageNodeColors[edge.source] || voltageNodeColors[edge.target] || "";
        return {
          ...edge,
          selected: edge.attrs?.component_node_id === selectedNodeId,
          className: isBranchEdgeComponent(edge.component)
            ? "schematic-branch-edge"
            : "",
          style: voltageColor
            ? { ...(edge.style || {}), stroke: voltageColor }
            : edge.style,
          data: {
            ...(edge.data || {}),
            component: edge.component || "",
            componentNodeId: edge.attrs?.component_node_id || "",
            edgeOffset: edge.edge_offset || { x: 0, y: 0 },
            iconSrc: edge.icon_src || "",
            iconSvg: edge.icon_svg || "",
            voltageColor,
            onEdgeOffsetChange: onEdgeOffsetUpdate,
          },
        };
      });
    },
    [edgeRouting.edges, flowNodes, onEdgeOffsetUpdate, selectedNodeId, voltageNodeColors],
  );

  useEffectReactFlowCanvas(() => {
    const routableFlowNodes = nodes.filter((node) => {
      return (
        !node.hidden &&
        isCanvasVisible(node) &&
        !isBranchEdgeComponent(node.component)
      );
    }).map((node) => {
      const connectionHandles =
        node.component === "buses" ? edgeRouting.handlesByBusId[node.id] || [] : [];
      const visualMeta = visualMetaForNode(node, connectionHandles);
      return {
        id: node.id,
        style: {
          width: `${visualMeta.width}px`,
          height: `${visualMeta.height + BUS_LABEL_HEIGHT}px`,
        },
      };
    });
    if (!routeVersion || routableFlowNodes.length === 0) return;
    if (lastRoutedVersionRef.current === routeVersion) return;

    let cancelled = false;

    async function routeWithElk() {
      const routableFlowNodeIds = new Set(routableFlowNodes.map((node) => node.id));
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
        children: routableFlowNodes.map((node) => ({
          id: node.id,
          width: Number.parseFloat(node.style?.width) || 56,
          height: Number.parseFloat(node.style?.height) || 56,
        })),
        edges: edgeRouting.edges
          .filter(
            (edge) =>
              routableFlowNodeIds.has(edge.source) &&
              routableFlowNodeIds.has(edge.target),
          )
          .map((edge) => ({
            id: edge.id,
            sources: [edge.source],
            targets: [edge.target],
          })),
      });

      if (cancelled || !Array.isArray(layout.children)) return;

      lastRoutedVersionRef.current = routeVersion;
      const constrainedChildren = applyBusSideConstraintsToLayout(
        layout.children,
        nodes,
      );
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
      if (cancelled) return;
      console.error("ELK auto route failed", error);
      onRouteComplete?.();
    });

    return () => {
      cancelled = true;
    };
  }, [
    edgeRouting.edges,
    edgeRouting.handlesByBusId,
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
      if (!componentNodeId) return;
      const edgeOffset = edge?.data?.edgeOffset || {};
      const position = contextMenuPositionFromEvent(event);
      setContextMenu({
        targetKind: "edge",
        targetId: edge.id,
        nodeId: componentNodeId,
        hasEdgeOffset: Boolean(edgeOffset.x || edgeOffset.y),
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
      draggingNodeIdRef.current = node?.id || "";
      const hasBusAttr = Object.prototype.hasOwnProperty.call(node?.data?.attrs || {}, "bus");
      const isConnected = Boolean(node?.data?.attrs?.bus);
      if (!hasBusAttr || node?.data?.isBus) {
        setHoverBusId("");
        setDragBusSidePreview({ nodeId: "", side: "" });
        return;
      }
      const width = Number.parseFloat(node.style?.width) || 56;
      const height = Number.parseFloat(node.style?.height) || 56;
      const sourceNode = liveDiagramNodes.find((candidate) => candidate.id === node.id);
      const positionedNode = {
        ...(sourceNode || {}),
        id: node.id,
        component: sourceNode?.component || node?.data?.component || "",
        attrs: sourceNode?.attrs || node?.data?.attrs || {},
        layout: sourceNode?.layout || node?.data?.layout || {},
        position: node.position,
      };

      if (isConnected) {
        const targetBusNode = attachedBusNodeForNode(positionedNode, liveDiagramNodes);
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
    [
      busIdAtFlowPoint,
      closeContextMenu,
      liveDiagramNodes,
      rectangleSelectionArmed,
    ],
  );

  const handleNodeDragStop = useCallbackReactFlowCanvas(
    (_, node) => {
      if (rectangleSelectionArmed) return;
      draggingNodeIdRef.current = "";
      const hasBusAttr = Object.prototype.hasOwnProperty.call(node?.data?.attrs || {}, "bus");
      const isConnected = Boolean(node?.data?.attrs?.bus);
      const width = Number.parseFloat(node.style?.width) || 56;
      const height = Number.parseFloat(node.style?.height) || 56;
      const sourceNode = liveDiagramNodes.find((candidate) => candidate.id === node.id);
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
        ? liveDiagramNodes.find((candidate) => candidate.id === busNodeId)
        : attachedBusNodeForNode(positionedNode, liveDiagramNodes);
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
    [
      busIdAtFlowPoint,
      liveDiagramNodes,
      onNodesUpdate,
      rectangleSelectionArmed,
    ],
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
        onNodesChange={handleNodesChange}
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
