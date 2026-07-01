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
