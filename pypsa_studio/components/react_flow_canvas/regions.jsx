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
