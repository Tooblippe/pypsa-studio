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

/**
 * Return the midpoint symbol size for an edge component.
 *
 * @param {string} component
 * @returns {number}
 */
function edgeSymbolSizeForComponent(component) {
  return ["transformers", "transformer"].includes(
    String(component || "").toLowerCase(),
  )
    ? EDGE_SYMBOL_SIZE_PX * 1.1
    : EDGE_SYMBOL_SIZE_PX;
}

/**
 * Return the branch flow arrow placement for the bus1 edge endpoint.
 */
function branchTargetArrowStyle(targetX, targetY, targetPosition) {
  const offsetPx = 8;
  const placement = {
    [Position.Left]: { x: targetX - offsetPx, y: targetY, rotation: 0 },
    [Position.Right]: { x: targetX + offsetPx, y: targetY, rotation: 180 },
    [Position.Top]: { x: targetX, y: targetY - offsetPx, rotation: 90 },
    [Position.Bottom]: { x: targetX, y: targetY + offsetPx, rotation: -90 },
  }[targetPosition] || { x: targetX, y: targetY, rotation: 0 };

  return {
    transform: `translate(-50%, -50%) translate(${placement.x}px, ${placement.y}px) rotate(${placement.rotation}deg)`,
  };
}

/**
 * Return a numeric edge offset from serialized edge data.
 */
function edgeOffsetFromData(data) {
  return {
    x: Number(data?.edgeOffset?.x || 0),
    y: Number(data?.edgeOffset?.y || 0),
  };
}

/**
 * Return a smooth step path shifted by the manual edge offset.
 */
function offsetSmoothStepPath(pathParams, edgeOffset) {
  const [, baseLabelX, baseLabelY] = getSmoothStepPath(pathParams);
  return getSmoothStepPath({
    ...pathParams,
    centerX: baseLabelX + Number(edgeOffset.x || 0),
    centerY: baseLabelY + Number(edgeOffset.y || 0),
  });
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
  const reactFlow = useReactFlow();
  const [dragOffset, setDragOffset] = useStateReactFlowCanvas(null);
  const pathParams = {
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 0,
  };
  const savedOffset = edgeOffsetFromData(data);
  const effectiveOffset = dragOffset || savedOffset;
  const [edgePath, labelX, labelY] = offsetSmoothStepPath(
    pathParams,
    effectiveOffset,
  );
  const rotateLabel = Boolean(label) && shouldRotateStepEdgeLabel(
    sourceY,
    targetY,
    sourcePosition,
    targetPosition,
  );
  const labelOffset = edgeLabelOffset(rotateLabel);
  const showEdgeSymbol = shouldRenderEdgeSymbol(data.component) && data.iconSrc;
  const edgeSymbolSize = edgeSymbolSizeForComponent(data.component);
  const showBranchTargetArrow = isBranchEdgeComponent(data.component);
  const handleEdgePointerDown = useCallbackReactFlowCanvas(
    (event) => {
      if (!selected || event.button !== 0 || !data.componentNodeId) return;
      event.preventDefault();
      event.stopPropagation();
      const startClient = { x: event.clientX, y: event.clientY };
      const startOffset = edgeOffsetFromData(data);
      const zoom = reactFlow.getViewport?.().zoom || 1;
      let latestOffset = startOffset;
      let moved = false;

      const handlePointerMove = (moveEvent) => {
        moveEvent.preventDefault();
        const nextOffset = {
          x: startOffset.x + (moveEvent.clientX - startClient.x) / zoom,
          y: startOffset.y + (moveEvent.clientY - startClient.y) / zoom,
        };
        moved =
          moved ||
          Math.abs(nextOffset.x - startOffset.x) > 0.5 ||
          Math.abs(nextOffset.y - startOffset.y) > 0.5;
        latestOffset = nextOffset;
        setDragOffset(nextOffset);
      };

      const handlePointerUp = () => {
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
        window.removeEventListener("pointercancel", handlePointerUp);
        setDragOffset(null);
        if (!moved) return;
        data.onEdgeOffsetChange?.({
          node_id: data.componentNodeId,
          edge_offset_x: latestOffset.x,
          edge_offset_y: latestOffset.y,
        });
      };

      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
      window.addEventListener("pointercancel", handlePointerUp);
    },
    [data, reactFlow, selected],
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
      <path
        className="schematic-edge-drag-handle"
        d={edgePath}
        data-selected={selected ? "true" : "false"}
        onPointerDown={handleEdgePointerDown}
      />
      {showBranchTargetArrow ? (
        <EdgeLabelRenderer>
          <svg
            aria-hidden="true"
            className="schematic-branch-target-arrow"
            viewBox="0 0 14 14"
            style={branchTargetArrowStyle(targetX, targetY, targetPosition)}
          >
            <path d="M4 3 L10 7 L4 11" />
          </svg>
        </EdgeLabelRenderer>
      ) : null}
      {showEdgeSymbol ? (
        <EdgeLabelRenderer>
          <span
            className="schematic-edge-symbol"
            style={{
              "--edge-symbol-size": `${edgeSymbolSize}px`,
              position: "absolute",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 4,
              boxSizing: "content-box",
              width: `${edgeSymbolSize}px`,
              height: `${edgeSymbolSize}px`,
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
                width: `${edgeSymbolSize}px`,
                height: `${edgeSymbolSize}px`,
                maxWidth: `${edgeSymbolSize}px`,
                maxHeight: `${edgeSymbolSize}px`,
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

const edgeTypes = { step: SchematicStepEdge };
