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
