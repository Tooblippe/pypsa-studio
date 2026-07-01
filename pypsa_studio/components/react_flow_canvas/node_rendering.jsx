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
  const voltageColor = String(data.voltageColor || "");
  const symbolStyle = voltageColor
    ? { width: "100%", height: "100%", color: voltageColor, filter: "none" }
    : { width: "100%", height: "100%" };
  const shouldRotateSymbol = shouldRotateIconForBusSide(data.component, data.busSide);
  const isNegativeGenerator = hasNegativeGeneratorSign(data);
  const symbolLayerStyle = {
    width: `${symbolMeta.width}px`,
    height: `${symbolHeight}px`,
    transform: shouldRotateSymbol ? "rotate(180deg)" : "none",
  };
  const nodeStyle = {
    ...(voltageColor ? { "--voltage-color": voltageColor } : {}),
    ...(data.canvasVisible ? {} : { opacity: 0, pointerEvents: "none" }),
  };
  const selectNodeFromSymbol = useCallbackReactFlowCanvas(
    (event) => {
      if (event.button !== 0 || data.isBus || data.branchArmed) return;
      data.onSelect?.(data.nodeId);
    },
    [data.branchArmed, data.isBus, data.nodeId, data.onSelect],
  );
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
      data-negative-generator={isNegativeGenerator ? "true" : "false"}
      data-voltage-colored={voltageColor ? "true" : "false"}
      title={`${data.label} (${data.component})`}
      style={Object.keys(nodeStyle).length ? nodeStyle : undefined}
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
                  ...(voltageColor ? { background: voltageColor } : {}),
                }
              : {
                  height: `${busSymbolLength}px`,
                  ...(voltageColor ? { background: voltageColor } : {}),
                }
          }
        />
      ) : data.iconSvg ? (
        <span
          className="schematic-symbol-layer"
          onPointerDown={selectNodeFromSymbol}
          style={symbolLayerStyle}
        >
          {terminalElements}
          <span
            className="schematic-node-symbol"
            style={symbolStyle}
            dangerouslySetInnerHTML={{ __html: data.iconSvg }}
          />
        </span>
      ) : (
        <span
          className="schematic-symbol-layer"
          onPointerDown={selectNodeFromSymbol}
          style={symbolLayerStyle}
        >
          {terminalElements}
          <img className="schematic-node-symbol" src={data.iconSrc} alt="" style={symbolStyle} />
        </span>
      )}
      <span className="schematic-node-label">{data.label}</span>
    </div>
  );
}

const nodeTypes = { schematic: SchematicNode };
